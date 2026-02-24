import bpy
import json
import os
import shutil


def get_robust_relpath(target_path, base_path):
	"""
	Calculates the relative path from base_path to target_path.
	Ensures both paths are absolute and symlinks are resolved before calculation.
	"""
	if not target_path or not base_path:
		return target_path
	
	abs_target = os.path.realpath(bpy.path.abspath(target_path))
	abs_base = os.path.realpath(bpy.path.abspath(base_path))
	
	try:
		return os.path.relpath(abs_target, abs_base)
	except (ValueError, Exception):
		# Fallback if paths are on different drives (Windows) or other errors
		return abs_target


class MavhodExportSettings(bpy.types.Operator):
	"""Open dialog to export the current scene"""
	bl_idname = "mavhod_tool.export_settings"
	bl_label = "Export Scene"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		# Kick off the modal export operator
		bpy.ops.mavhod_tool.export_execute('INVOKE_DEFAULT')
		return {'FINISHED'}

	def invoke(self, context, event):
		return context.window_manager.invoke_props_dialog(self)

	def draw(self, context):
		layout = self.layout
		props = context.scene.MavhodToolProps
		layout.prop(props, "asset_source_path")
		layout.prop(props, "asset_dest_path")
		layout.prop(props, "scene_dest_path")


class MavhodExportExecute(bpy.types.Operator):
	"""Modal export operator that processes one mesh per tick for visible progress"""
	bl_idname = "mavhod_tool.export_execute"
	bl_label = "Exporting..."
	bl_options = set()

	_timer = None
	_objects = []
	_exported_meshes = set()
	_original_selected = []
	_original_active = None
	_current_index = 0
	_total = 0
	_export_asset_path = ""
	_export_scene_path = ""
	_asset_source_path = ""
	_mesh_data_for_json = []

	def modal(self, context, event):
		if event.type == 'TIMER':
			# Done?
			if self._current_index >= self._total:
				return self._finish(context)

			obj = self._objects[self._current_index]
			mesh_data_name = obj.data.name

			# Determine source folder name:
			source_folder = "local"
			is_linked = False
			lib = obj.library or (obj.data.library if obj.data else None)
			if lib and lib.filepath:
				abs_lib_path = os.path.realpath(bpy.path.abspath(lib.filepath))
				
				# If asset source path is set, use it to determine the relative source folder
				if self._asset_source_path:
					rel_source = get_robust_relpath(os.path.dirname(abs_lib_path), self._asset_source_path)
					if rel_source == ".":
						source_folder = ""
					else:
						source_folder = rel_source
				else:
					source_folder = os.path.basename(os.path.dirname(abs_lib_path))
				is_linked = True
			elif bpy.data.filepath:
				abs_blend_path = os.path.realpath(bpy.path.abspath(bpy.data.filepath))
				
				# If asset source path is set, use it to determine the relative source folder
				if self._asset_source_path:
					rel_source = get_robust_relpath(os.path.dirname(abs_blend_path), self._asset_source_path)
					source_folder = "" if rel_source == "." else rel_source
				else:
					source_folder = os.path.basename(os.path.dirname(abs_blend_path))

			# Set root directory for export
			# Linked objects -> Asset Path, Local objects -> Scene Path
			root_dir = self._export_asset_path if is_linked else self._export_scene_path
			
			if not root_dir:
				# Fallback if one path is missing but needed
				root_dir = self._export_scene_path if self._export_scene_path else self._export_asset_path

			# Construct paths
			if is_linked:
				# Linked objects: both GLTF and textures follow the source folder structure
				parent_folder_path = os.path.join(root_dir, source_folder)
				relative_asset_path = os.path.join(source_folder, f"{mesh_data_name}.gltf")
				dest_display = f"{source_folder}/"
			else:
				# Local objects: GLTF stays in the root, but textures will still follow source_folder (handled below)
				parent_folder_path = root_dir
				relative_asset_path = f"{mesh_data_name}.gltf"
				dest_display = "scene (root)/"

			# Update progress in header
			status_msg = f"Exporting {'(Linked)' if is_linked else '(Local)'} {self._current_index + 1}/{self._total}: {obj.name} -> {dest_display}"
			context.workspace.status_text_set(status_msg)
			
			wm = context.window_manager
			wm.progress_update(self._current_index)

			if root_dir and mesh_data_name not in self._exported_meshes:
				# Ensure asset directory exists
				os.makedirs(parent_folder_path, exist_ok=True)
				
				# Asset root for textures (always uses Asset Path if available)
				tex_root = self._export_asset_path if self._export_asset_path else self._export_scene_path

				# Collect images in iteration order (to match GLTF images array order by index)
				ordered_images = []  # list of (img, src_path, abs_dst, rel_uri)
				seen_names = set()
				for slot in obj.material_slots:
					if slot.material and slot.material.use_nodes:
						for node in slot.material.node_tree.nodes:
							if node.type == 'TEX_IMAGE' and node.image:
								img = node.image
								if img.name in seen_names:
									continue
								seen_names.add(img.name)

								# Resolve source path
								# For linked images: resolve relative to their library file
								# For local images: resolve relative to the current blend file
								if img.library and img.library.filepath:
									lib_dir = os.path.dirname(os.path.realpath(bpy.path.abspath(img.library.filepath)))
									src_path = os.path.realpath(bpy.path.abspath(img.filepath, start=lib_dir)) if img.filepath else None
								else:
									src_path = os.path.realpath(bpy.path.abspath(img.filepath)) if img.filepath else None

								if src_path and os.path.isfile(src_path):
									# Determine destination subfolder using get_robust_relpath
									if self._asset_source_path:
										rel_source = get_robust_relpath(os.path.dirname(src_path), self._asset_source_path)
										img_source_folder = "" if rel_source == "." else rel_source
									else:
										img_source_folder = os.path.basename(os.path.dirname(src_path))

									img_filename = os.path.basename(src_path)
									target_tex_dir = os.path.join(tex_root, img_source_folder)
									os.makedirs(target_tex_dir, exist_ok=True)
									abs_dst = os.path.join(target_tex_dir, img_filename)
									rel_uri = get_robust_relpath(abs_dst, parent_folder_path)
									ordered_images.append((img, src_path, abs_dst, rel_uri))
								else:
									ordered_images.append((img, None, None, None))

				# Isolate object for export
				bpy.ops.object.select_all(action='DESELECT')
				obj.select_set(True)
				context.view_layer.objects.active = obj

				full_path = os.path.join(parent_folder_path, f"{mesh_data_name}.gltf")

				# Export – Blender writes temp image files next to the GLTF
				bpy.ops.export_scene.gltf(
					filepath=full_path,
					use_selection=True,
					export_format='GLTF_SEPARATE',
					export_image_format='AUTO',
					export_apply=True
				)
				self._exported_meshes.add(mesh_data_name)

				# Patch GLTF: for each image entry match by index, copy original, fix URI
				if os.path.isfile(full_path):
					try:
						with open(full_path, 'r', encoding='utf-8') as gf:
							gltf_data = json.load(gf)

						gltf_images = gltf_data.get('images', [])
						for i, (img, src_path, abs_dst, rel_uri) in enumerate(ordered_images):
							if i >= len(gltf_images):
								break
							gltf_img = gltf_images[i]
							old_uri = gltf_img.get('uri', '')
							if not old_uri or 'bufferView' in gltf_img:
								continue

							exported_temp_path = os.path.join(parent_folder_path, old_uri)

							if abs_dst:
								# Copy original texture to the correct destination
								if src_path and os.path.isfile(src_path) and not os.path.exists(abs_dst):
									shutil.copy2(src_path, abs_dst)
								# Remove Blender's temp exported image
								if os.path.isfile(exported_temp_path):
									os.remove(exported_temp_path)
								# Update GLTF URI to point to real texture location
								gltf_img['uri'] = rel_uri.replace("\\", "/")
							# else: no original on disk → leave Blender's exported image and URI as-is

						with open(full_path, 'w', encoding='utf-8') as gf:
							json.dump(gltf_data, gf, indent=4)
					except Exception as e:
						self.report({'WARNING'}, f"Could not patch GLTF textures: {str(e)}")

			# Collect JSON data
			local_matrix = obj.matrix_local
			loc, rot_quat, scale = local_matrix.decompose()
			self._mesh_data_for_json.append({
				"name": obj.name,
				"mesh_data": obj.data.name,
				"is_linked": is_linked,
				"asset_path": relative_asset_path,
				"location": {"x": loc.x, "y": loc.y, "z": loc.z},
				"rotation": {"x": rot_quat.x, "y": rot_quat.y, "z": rot_quat.z, "w": rot_quat.w},
				"scale": {"x": scale.x, "y": scale.y, "z": scale.z}
			})
			self._current_index += 1

		return {'PASS_THROUGH'}

	def invoke(self, context, event):
		props = context.scene.MavhodToolProps
		self._export_scene_path = bpy.path.abspath(props.scene_dest_path)
		self._export_asset_path = bpy.path.abspath(props.asset_dest_path) if props.asset_dest_path else ""
		self._asset_source_path = bpy.path.abspath(props.asset_source_path) if props.asset_source_path else ""

		if not self._export_scene_path:
			self.report({'WARNING'}, "Export Scene Path is not set!")
			return {'CANCELLED'}

		os.makedirs(self._export_scene_path, exist_ok=True)
		if self._export_asset_path:
			os.makedirs(self._export_asset_path, exist_ok=True)

		self._objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
		if not self._objects:
			self.report({'WARNING'}, "No mesh objects selected!")
			return {'CANCELLED'}

		self._exported_meshes = set()
		self._current_index = 0
		self._total = len(self._objects)
		self._mesh_data_for_json = []
		self._original_selected = list(context.selected_objects)
		self._original_active = context.view_layer.objects.active

		wm = context.window_manager
		wm.progress_begin(0, self._total)
		self._timer = wm.event_timer_add(0.01, window=context.window)
		wm.modal_handler_add(self)
		return {'RUNNING_MODAL'}

	def _finish(self, context):
		wm = context.window_manager
		wm.event_timer_remove(self._timer)
		wm.progress_end()
		context.workspace.status_text_set(None)

		# Restore original selection
		bpy.ops.object.select_all(action='DESELECT')
		for obj in self._original_selected:
			obj.select_set(True)
		context.view_layer.objects.active = self._original_active

		# Save JSON
		json_path = os.path.join(self._export_scene_path, "selected_meshes.json")
		try:
			with open(json_path, 'w', encoding='utf-8') as f:
				json.dump({"selected_meshes": self._mesh_data_for_json}, f, indent=4)
		except Exception as e:
			self.report({'ERROR'}, f"Failed to write JSON: {str(e)}")
			return {'CANCELLED'}

		self.report(
			{'INFO'},
			f"Done! {self._total} instances, {len(self._exported_meshes)} unique GLTFs exported."
		)
		return {'FINISHED'}
