import bpy
import mathutils
import re
import json
import os
import shutil
import hashlib
import subprocess
from .export_utils import copy_and_hash_images, rebind_materials_to_hashed_images
from bpy_extras.io_utils import ExportHelper

def get_robust_relpath(target_path, base_path):
	"""
	Calculate relative path from base_path to target_path.
	Ensures both paths are absolute and resolves symlinks before calculation.
	"""
	if not target_path or not base_path: return target_path
	# Convert paths to resolved absolute paths
	abs_target = os.path.realpath(bpy.path.abspath(target_path))
	abs_base = os.path.realpath(bpy.path.abspath(base_path))
	#
	try:
		# Attempt to find relative path
		return os.path.relpath(abs_target, abs_base)
	except (ValueError, Exception):
		# If paths are on different drives (Windows) or other error occurs, return original absolute path
		return abs_target

class MavhodExportSettings(bpy.types.Operator, ExportHelper):
	bl_idname = "mavhod_tool.export_settings"
	bl_label = "Export Scene"
	bl_options = {'REGISTER', 'UNDO'}

	filename_ext = ".json"
	filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'}, maxlen=255,)

	def invoke(self, context, event):
		props = context.scene.MavhodToolProps
		ext = props.scene_extension
		if not ext.startswith("."):
			ext = "." + ext
		self.filename_ext = ext
		self.filter_glob = "*" + ext
		return super().invoke(context, event)

	def execute(self, context):
		bpy.ops.mavhod_tool.export_execute('INVOKE_DEFAULT', filepath=self.filepath)
		return {'FINISHED'}

class MavhodExportExecute(bpy.types.Operator):
	"""Main export operator that processes each Mesh to show a progress bar"""
	bl_idname = "mavhod_tool.export_execute"
	bl_label = "Exporting..."
	bl_options = set()

	filepath: bpy.props.StringProperty(options={'HIDDEN'})
	_timer = None
	_current_index = 0
	_objects = []
	_exported_meshes = set()
	_original_selected = []
	_original_active = None
	_path_pairs = []
	
	# src_path e.g. '/d/wander/leftway2/model/buildingNurseOffice/nurseOffice.gltf'
	# dst_path e.g. '/d/wander/leftway2/level/New Folder/model/buildingNurseOffice/nurseOffice.gltf',
	def _get_dst_path(self, src_path):
		for pair in self.path_pairs:
			if pair['source_path'] in src_path:
				rel_source = get_robust_relpath(src_path, pair['source_path'])
				dest_path = pair['dest_path']
				# Resolve Blender-relative paths or ensure absolute paths are clean
				if dest_path.startswith("//") or dest_path.startswith("/"):
					dest_path = bpy.path.abspath(dest_path)
				return os.path.realpath(os.path.join(self._export_scene_path, dest_path, rel_source))
		return None

	def _get_export_path(self, obj):
		"""Calculate source folder, link status, and all relevant export paths"""
		props = bpy.context.scene.MavhodToolProps
		is_linked = False
		# Check if object is linked from a library file
		lib = obj.library or (obj.data.library if obj.data else None)
		if lib and lib.filepath: # Linked Object case
			is_linked = True
			# filepath e.g. "/d/wander/leftway2/model/buildingNurseOffice/nurseOffice.gltf"
			blend_filepath = os.path.realpath(bpy.path.abspath(lib.filepath))
			filepath = os.path.dirname(blend_filepath) + "/" + obj.data.name + ".gltf"
			dst_path = self._get_dst_path(filepath)
		else:
			blend_filepath = os.path.realpath(bpy.data.filepath)
			dst_path = f"{self._export_scene_path}/{self._blend_filename}/{obj.data.name}.gltf"
		#	
		return {
			'is_linked': is_linked,
			'blend_filepath': blend_filepath, # e.g. "/d/wander/leftway2/model/buildingNurseOffice/buildingNurseOffice.blend"
			'dst_path': dst_path
		}

	def _collect_images(self, obj):
		"""
		Collect texture metadata from object materials.
		Returns image_metadata: dict mapping sha256 hash to metadata.
		"""
		image_metadata = {} # hash sha256 -> {src_path, dst_path}
		for slot in obj.material_slots:
			if not (slot.material and slot.material.use_nodes): continue
			nodes = slot.material.node_tree.nodes
			for node in nodes:
				if not (node.type == 'TEX_IMAGE' and node.image): continue
				img = node.image
				if img in image_metadata: continue
				# Resolve original source path
				if img.library and img.library.filepath:
					lib_dir = os.path.dirname(os.path.realpath(bpy.path.abspath(img.library.filepath)))
					src_path = os.path.realpath(bpy.path.abspath(img.filepath, start=lib_dir)) if img.filepath else None
				else:
					src_path = os.path.realpath(bpy.path.abspath(img.filepath)) if img.filepath else None
				# Create SHA256 Hash
				hash_obj = hashlib.sha256(src_path.encode('utf-8'))
				hash_name = hash_obj.hexdigest()
				#
				image_metadata[hash_name] = {
					'src_path': src_path,
					'dst_path': self._get_dst_path(src_path),
				}
		return image_metadata

	def _export_and_patch_gltf(self, context, obj, path_info, image_metadata):
		"""
		Export GLTF and patch the file using utility functions.
		"""
		dst_path = path_info['dst_path']
		props = bpy.context.scene.MavhodToolProps
		object_ext = props.object_extension
		if not object_ext.startswith("."):
			object_ext = "." + object_ext
			
		# Ensure destination directory exists
		dst_dir = os.path.dirname(dst_path)
		os.makedirs(dst_dir, exist_ok=True)
		
		if path_info['is_linked']:
			# Use subprocess to export linked mesh data
			blender_bin = bpy.app.binary_path
			script_path = os.path.join(os.path.dirname(__file__), "export_bg.py")
			blend_file = path_info['blend_filepath']
			mesh_name = obj.data.name
			
			cmd = [
				blender_bin,
				"--factory-startup",
				"-b", blend_file,
				"-P", script_path,
				"--",
				"--output", dst_path,
				"--mesh", mesh_name,
				"--object_ext", object_ext
			]
			# Pass metadata flags
			if props.export_metadata_node: cmd.append("--metadata_node")
			if props.export_metadata_mesh: cmd.append("--metadata_mesh")
			if props.export_metadata_material: cmd.append("--metadata_material")
			if props.export_metadata_scene: cmd.append("--metadata_scene")
			
			print(f"Running subprocess: {' '.join(cmd)}")
			try:
				subprocess.run(cmd, check=True)
			except subprocess.CalledProcessError as e:
				self.report({'ERROR'}, f"Subprocess failed for {obj.name}")
				return
		else:
			# Local object export
			# Isolate Object
			bpy.ops.object.select_all(action='DESELECT')
			obj.select_set(True)
			context.view_layer.objects.active = obj
			
			# 1. Copy and Hash Image + Re-bind Material for Local Object
			output_dir = os.path.dirname(dst_path)
			image_mapping = copy_and_hash_images(output_dir)
			
			# Keep original materials to restore after export
			original_materials = list(obj.data.materials)
			try:
				# Re-bind materials to use hashed image paths before export
				rebind_materials_to_hashed_images(image_mapping)
				
				# Export extras if any glTF-related metadata is enabled
				use_extras = props.export_metadata_node or props.export_metadata_mesh or \
							 props.export_metadata_material or props.export_metadata_scene
				
				bpy.ops.export_scene.gltf(
					filepath=dst_path,
					use_selection=True,
					export_format='GLTF_SEPARATE',
					export_image_format='AUTO',
					export_apply=True,
					export_extras=use_extras
				)
			finally:
				# Restore original materials to object
				for i, mat in enumerate(original_materials):
					obj.data.materials[i] = mat
			
		# 2. Patch and Filter output using utility (for both Local and Linked)
		from .export_utils import patch_gltf_output
		metadata_settings = {
			'node': props.export_metadata_node,
			'mesh': props.export_metadata_mesh,
			'material': props.export_metadata_material,
			'scene': props.export_metadata_scene
		}
		patch_gltf_output(dst_path, metadata_settings, image_metadata, object_ext)


	def _get_mesh_instance_data(self, obj, path_info):
		"""Prepare instance data for writing to the final JSON result file"""
		props = bpy.context.scene.MavhodToolProps
		object_ext = props.object_extension
		if not object_ext.startswith("."):
			object_ext = "." + object_ext
			
		# Determine the final path with the correct extension
		final_path = os.path.splitext(path_info['dst_path'])[0] + object_ext
		
		world_matrix = obj.matrix_world
		loc, rot_quat, scale = world_matrix.decompose()
		
		# Proper conversion from Z-up to Y-up
		# M maps Godot basis to Blender basis:
		# X_B = X_G
		# Y_B = -Z_G
		# Z_B = Y_G
		M = mathutils.Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
		M_inv = M.inverted()

		# Transform Location
		loc_G = M_inv.to_3x3() @ loc
		
		# Transform Rotation
		R_B = rot_quat.to_matrix().to_4x4()
		R_G = M_inv @ R_B @ M
		rot_quat_G = R_G.to_quaternion()
		
		# Transform Scale
		scale_G = mathutils.Vector((scale.x, scale.z, scale.y))
		
		data = {
			"name": obj.name,
			"asset_path": get_robust_relpath(final_path, self._export_scene_path),
			"location": {"x": loc_G.x, "y": loc_G.y, "z": loc_G.z},
			"rotation": {"x": rot_quat_G.x, "y": rot_quat_G.y, "z": rot_quat_G.z, "w": rot_quat_G.w},
			"scale": {"x": scale_G.x, "y": scale_G.y, "z": scale_G.z}
		}
		
		if props.export_metadata_instance:
			extras = {}
			for key in obj.keys():
				if key == "_RNA_UI": continue
				val = obj[key]
				if hasattr(val, "to_list"):
					val = val.to_list()
				extras[key] = val
			if extras:
				data["metadata"] = extras
				
		return data

	def modal(self, context, event):
		if event.type != 'TIMER': return {'PASS_THROUGH'};
		if self._current_index >= len(self._objects): return self._finish(context);
		current_index = self._current_index
		self._current_index += 1
		obj = self._objects[current_index]
		# 1. Calculate export paths and check link status (Linked Data)
		path_info = self._get_export_path(obj)
		if path_info['dst_path'] == None: return {'PASS_THROUGH'};
		is_linked = path_info['is_linked']
		# Update status message in Blender header
		status_msg = f"Exporting {'(Linked)' if is_linked else '(Local)'} {current_index + 1}/{len(self._objects)}: {obj.name}"
		context.workspace.status_text_set(status_msg)
		# Update progress bar
		wm = context.window_manager
		wm.progress_update(current_index)
		# Check if this model has already been exported (to avoid duplicate export if Mesh is reused)
		export_key = f"{path_info['blend_filepath']}|{obj.data.name}" # e.g. "/d/wander/leftway2/level/theme1.blend:Cube.049"
		if export_key not in self._exported_meshes:
			# 2. Collect image data (Textures) used in Material
			image_metadata = self._collect_images(obj)
			# 3. Export model as GLTF and Patch file to fix image paths and Filters
			self._export_and_patch_gltf(context, obj, path_info, image_metadata)
			self._exported_meshes.add(export_key)

		# 4. Record instance data for the final scene aggregate JSON file (for every instance!)
		self._mesh_data_for_json.append(self._get_mesh_instance_data(obj, path_info))

		return {'PASS_THROUGH'}
		
	def invoke(self, context, event):
		# Initial function when export process starts
		props = context.scene.MavhodToolProps
		# Initialize status for Modal processing
		self._exported_meshes = set()
		self._current_index = 0
		self._mesh_data_for_json = []
		# Store original selection to restore after work completion
		self._original_selected = list(context.selected_objects)
		self._original_active = context.view_layer.objects.active
		#
		if not self.filepath:
			self.report({'WARNING'}, "Export filepath not defined!")
			return {'CANCELLED'}
		#
		self._export_scene_path = os.path.realpath(os.path.dirname(self.filepath)) # e.g. "/d/wander/leftway2/level/New Folder"
		self._blend_filename = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
		#
		self.path_pairs = []
		for pair in props.path_pairs:
			if not (pair.source_path and pair.dest_path): continue
			source_path = os.path.normpath(bpy.path.abspath("//" + pair.source_path))
			if not os.path.exists(source_path): continue
			dest_path = pair.dest_path
			self.path_pairs.append({'source_path': source_path, 'dest_path': dest_path})
		# Sort self.path_pairs by source_path in reverse (Z-A)
		self.path_pairs.sort(key=lambda x: x['source_path'], reverse=True)
		# Collect only selected Mesh objects
		self._objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
		if not self._objects:
			self.report({'WARNING'}, "No Mesh or models selected!")
			return {'CANCELLED'}
		# Start Progress Bar and Timer
		wm = context.window_manager
		wm.progress_begin(0, len(self._objects))
		self._timer = wm.event_timer_add(0.01, window=context.window)
		wm.modal_handler_add(self)
		#
		return {'RUNNING_MODAL'}

	def _finish(self, context):
		"""Cleanup and summary after all processing is complete"""
		wm = context.window_manager
		wm.event_timer_remove(self._timer)
		wm.progress_end()
		# Clear status message in Header
		context.workspace.status_text_set(None)
		# Restore original selection
		bpy.ops.object.select_all(action='DESELECT')
		for obj in self._original_selected:
			obj.select_set(True)
		context.view_layer.objects.active = self._original_active
		# Save all scene aggregate data to JSON
		try:
			# Create Save folder if it doesn't exist
			os.makedirs(self._export_scene_path, exist_ok=True)
			
			scene_data = {"instances": self._mesh_data_for_json}
			
			props = context.scene.MavhodToolProps
			if props.export_metadata_level:
				level_extras = {}
				for key in bpy.context.scene.keys():
					if key == "_RNA_UI": continue
					val = bpy.context.scene[key]
					if hasattr(val, "to_list"):
						val = val.to_list()
					level_extras[key] = val
				if level_extras:
					scene_data["metadata"] = level_extras
			
			with open(self.filepath, 'w', encoding='utf-8') as f:
				json.dump(scene_data, f, indent=4)
		except Exception as e:
			self.report({'ERROR'}, f"Could not save JSON file: {str(e)}")
			return {'CANCELLED'}

		print("_finish")
		self.report(
			{'INFO'},
			f"Completed! Exported {len(self._objects)} items, with {len(self._exported_meshes)} unique GLTF model files"
		)
		return {'FINISHED'}
