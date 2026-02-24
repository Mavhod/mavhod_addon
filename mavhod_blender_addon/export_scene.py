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
		
		col = layout.column(align=True)
		col.label(text="Paths:")
		col.prop(props, "asset_source_path")
		col.prop(props, "asset_dest_path")
		col.prop(props, "scene_dest_path")
		
		layout.separator()
		
		col = layout.column(align=True)
		col.label(text="Export Texture Maps:")
		flow = col.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=True)
		flow.prop(props, "export_albedo")
		flow.prop(props, "export_metallic")
		flow.prop(props, "export_roughness")
		flow.prop(props, "export_normal")
		flow.prop(props, "export_emission")
		flow.prop(props, "export_alpha")
		flow.prop(props, "export_ao")


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

	# Texture export flags
	_export_albedo = True
	_export_metallic = True
	_export_roughness = True
	_export_normal = True
	_export_emission = True
	_export_alpha = True
	_export_ao = True

	# Map FePBR/Principled input names to export flag keys
	INPUT_TO_FLAG = {
		'Albedo Map': '_export_albedo',
		'Base Color': '_export_albedo',
		'Metallic': '_export_metallic',
		'Roughness': '_export_roughness',
		'Normal Map': '_export_normal',
		'Normal': '_export_normal',
		'Emission': '_export_emission',
		'Emission Color': '_export_emission',
		'Alpha Map': '_export_alpha',
		'Alpha': '_export_alpha',
		'AO': '_export_ao'
	}

	def modal(self, context, event):
		if event.type == 'TIMER':
			# Done?
			if self._current_index >= self._total:
				return self._finish(context)

			obj = self._objects[self._current_index]
			mesh_data_name = obj.data.name

			# 1. Determine paths and linkage
			paths = self._get_export_paths(obj)
			is_linked = paths['is_linked']
			parent_folder_path = paths['parent_folder_path']
			relative_asset_path = paths['relative_asset_path']
			root_dir = paths['root_dir']

			# Update progress in header
			status_msg = f"Exporting {'(Linked)' if is_linked else '(Local)'} {self._current_index + 1}/{self._total}: {obj.name} -> {paths['dest_display']}"
			context.workspace.status_text_set(status_msg)
			
			wm = context.window_manager
			wm.progress_update(self._current_index)

			if root_dir and mesh_data_name not in self._exported_meshes:
				# Ensure asset directory exists
				os.makedirs(parent_folder_path, exist_ok=True)
				
				# Asset root for textures (always uses Asset Path if available)
				tex_root = self._export_asset_path if self._export_asset_path else self._export_scene_path

				# 2. Collect images
				ordered_images = self._collect_images(obj, tex_root, parent_folder_path)

				# 3. Export and Patch GLTF
				full_path = os.path.join(parent_folder_path, f"{mesh_data_name}.gltf")
				self._export_and_patch_gltf(context, obj, parent_folder_path, full_path, ordered_images)
				self._exported_meshes.add(mesh_data_name)

			# 4. Collect JSON data
			self._mesh_data_for_json.append(
				self._get_mesh_instance_data(obj, is_linked, relative_asset_path)
			)
			self._current_index += 1

		return {'PASS_THROUGH'}

	def _get_export_paths(self, obj):
		"""Calculates source folder, linked status, and all relevant export paths."""
		source_folder = "local"
		is_linked = False
		lib = obj.library or (obj.data.library if obj.data else None)
		
		if lib and lib.filepath:
			abs_lib_path = os.path.realpath(bpy.path.abspath(lib.filepath))
			if self._asset_source_path:
				rel_source = get_robust_relpath(os.path.dirname(abs_lib_path), self._asset_source_path)
				source_folder = "" if rel_source == "." else rel_source
			else:
				source_folder = os.path.basename(os.path.dirname(abs_lib_path))
			is_linked = True
		elif bpy.data.filepath:
			abs_blend_path = os.path.realpath(bpy.path.abspath(bpy.data.filepath))
			if self._asset_source_path:
				rel_source = get_robust_relpath(os.path.dirname(abs_blend_path), self._asset_source_path)
				source_folder = "" if rel_source == "." else rel_source
			else:
				source_folder = os.path.basename(os.path.dirname(abs_blend_path))

		# Determine root directory
		root_dir = self._export_asset_path if is_linked else self._export_scene_path
		if not root_dir:
			root_dir = self._export_scene_path if self._export_scene_path else self._export_asset_path

		# Construct paths
		if is_linked:
			parent_folder_path = os.path.join(root_dir, source_folder)
			relative_asset_path = os.path.join(source_folder, f"{obj.data.name}.gltf")
			dest_display = f"{source_folder}/"
		else:
			parent_folder_path = root_dir
			relative_asset_path = f"{obj.data.name}.gltf"
			dest_display = "scene (root)/"

		return {
			'is_linked': is_linked,
			'root_dir': root_dir,
			'parent_folder_path': parent_folder_path,
			'relative_asset_path': relative_asset_path,
			'dest_display': dest_display
		}

	def _collect_images(self, obj, tex_root, parent_folder_path):
		"""
		Gathers texture metadata from object materials.
		Returns image_metadata: dict mapping Blender Image objects to metadata.
		"""
		image_metadata = {} # img -> {should_export, abs_dst, rel_uri, src_path}

		for slot in obj.material_slots:
			if not (slot.material and slot.material.use_nodes):
				continue

			nodes = slot.material.node_tree.nodes
			for node in nodes:
				if not (node.type == 'TEX_IMAGE' and node.image):
					continue
				
				img = node.image
				if img in image_metadata:
					continue

				# Resolve original source path
				if img.library and img.library.filepath:
					lib_dir = os.path.dirname(os.path.realpath(bpy.path.abspath(img.library.filepath)))
					src_path = os.path.realpath(bpy.path.abspath(img.filepath, start=lib_dir)) if img.filepath else None
				else:
					src_path = os.path.realpath(bpy.path.abspath(img.filepath)) if img.filepath else None

				# Prepare destination info
				abs_dst = None
				rel_uri = None
				if src_path and os.path.isfile(src_path):
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

				image_metadata[img] = {
					'src_path': src_path,
					'abs_dst': abs_dst,
					'rel_uri': rel_uri
				}

		return image_metadata

	def _export_and_patch_gltf(self, context, obj, parent_folder_path, full_path, image_metadata):
		"""
		Exports GLTF and patches it using structural tracing (Socket -> GLTF).
		This ensures 100% accuracy for both naming and filtering.
		"""
		# Isolate object
		bpy.ops.object.select_all(action='DESELECT')
		obj.select_set(True)
		context.view_layer.objects.active = obj

		# 1. Export normally
		bpy.ops.export_scene.gltf(
			filepath=full_path,
			use_selection=True,
			export_format='GLTF_SEPARATE',
			export_image_format='AUTO',
			export_apply=True
		)

		if not os.path.isfile(full_path):
			return

		try:
			with open(full_path, 'r', encoding='utf-8') as gf:
				gltf_data = json.load(gf)

			gltf_images = gltf_data.get('images', [])
			gltf_textures = gltf_data.get('textures', [])
			gltf_materials = gltf_data.get('materials', [])

			# --- STEP A: Structurally map Blender Material Sockets to GLTF indices ---
			indices_to_remove = set()
			gltf_img_idx_to_blender_img = {} # i_idx -> Blender Image object
			
			for m_idx, slot in enumerate(obj.material_slots):
				if m_idx >= len(gltf_materials): break
				if not (slot.material and slot.material.use_nodes): continue
				
				g_mat = gltf_materials[m_idx]
				nodes = slot.material.node_tree.nodes
				
				# Trace sockets to find their GLTF mapping
				socket_to_image = {} # socket_name -> Image object
				target_nodes = [n for n in nodes if n.type in {'GROUP', 'BSDF_PRINCIPLED'}]
				
				for target in target_nodes:
					for sock in target.inputs:
						if not sock.is_linked: continue
						
						from_node = sock.links[0].from_node
						if from_node.type == 'NORMAL_MAP' and sock.name in {'Normal', 'Normal Map'}:
							if from_node.inputs['Color'].is_linked:
								from_node = from_node.inputs['Color'].links[0].from_node
						
						if from_node.type == 'TEX_IMAGE' and from_node.image:
							socket_to_image[sock.name] = from_node.image

				# Define GLTF attribute to Socket Name mapping
				# Note: Blender's GLTF exporter maps these specifically
				attr_map = {
					('pbrMetallicRoughness', 'baseColorTexture'): ['Base Color', 'Albedo Map'],
					('pbrMetallicRoughness', 'metallicRoughnessTexture'): ['Metallic', 'Roughness'], # ORM map case
					('normalTexture',): ['Normal', 'Normal Map'],
					('occlusionTexture',): ['AO'],
					('emissiveTexture',): ['Emission', 'Emission Color']
				}

				for gltf_path, socket_names in attr_map.items():
					# Get GLTF texture reference
					tex_ref = g_mat
					for p in gltf_path:
						if isinstance(tex_ref, dict): tex_ref = tex_ref.get(p)
					
					if not tex_ref or not isinstance(tex_ref, dict): continue
					t_idx = tex_ref.get('index')
					if t_idx is None or t_idx >= len(gltf_textures): continue
					i_idx = gltf_textures[t_idx].get('source')
					if i_idx is None: continue

					# Record mapping for URI fixing later
					for sname in socket_names:
						if sname in socket_to_image:
							gltf_img_idx_to_blender_img[i_idx] = socket_to_image[sname]
							break

					# Find if any linked socket image matches user preference
					should_export = True
					for sname in socket_names:
						flag = self.INPUT_TO_FLAG.get(sname)
						if flag and not getattr(self, flag):
							# User unchecked this specific map type
							should_export = False
							break
					
					if not should_export:
						# Remove attribute from material
						parent = g_mat
						for p in gltf_path[:-1]: parent = parent.get(p)
						if isinstance(parent, dict): del parent[gltf_path[-1]]
						indices_to_remove.add(i_idx)

			# --- STEP B: Finalize URIs and Safe Cleanup ---
			# We iterate ALL images in the GLTF to see which ones we can fix with original files
			used_img_indices = set()
			# Re-scan used images after nulling
			for g_mat in gltf_materials:
				# Recursive scan for 'index' keys that point to textures
				def find_used(data):
					if isinstance(data, dict):
						if 'index' in data and len(data) == 1: # texture ref usually
							t_idx = data['index']
							if t_idx < len(gltf_textures):
								src = gltf_textures[t_idx].get('source')
								if src is not None: used_img_indices.add(src)
						for v in data.values(): find_used(v)
					elif isinstance(data, list):
						for item in data: find_used(item)
				find_used(g_mat)

			# Build final GLTF Image list
			new_img_list = []
			old_to_new_img = {}
			
			for i, gimg in enumerate(gltf_images):
				temp_uri = gimg.get('uri', '')
				temp_path = os.path.join(parent_folder_path, temp_uri) if temp_uri else None
				
				if i not in used_img_indices:
					# This image is no longer used (stripped)
					if temp_path and os.path.isfile(temp_path): os.remove(temp_path)
					continue

				# Re-mapping URIs to original filenames using structural mapping
				blender_img = gltf_img_idx_to_blender_img.get(i)
				matched_meta = image_metadata.get(blender_img) if blender_img else None
				
				old_to_new_img[i] = len(new_img_list)
				if matched_meta and matched_meta['abs_dst']:
					# Perform the robust copy and replace
					try:
						if matched_meta['src_path'] and os.path.isfile(matched_meta['src_path']):
							if not os.path.exists(matched_meta['abs_dst']):
								shutil.copy2(matched_meta['src_path'], matched_meta['abs_dst'])
							gimg['uri'] = matched_meta['rel_uri'].replace("\\", "/")
							if temp_path and os.path.isfile(temp_path): os.remove(temp_path)
					except Exception:
						pass # Keep original Blender export if copy fails
				
				new_img_list.append(gimg)

			# Re-index Textures
			new_tex_list = []
			old_to_new_tex = {}
			for i, gtex in enumerate(gltf_textures):
				src = gtex.get('source')
				if src is not None and src in old_to_new_img:
					old_to_new_tex[i] = len(new_tex_list)
					gtex['source'] = old_to_new_img[src]
					new_tex_list.append(gtex)

			# Re-index Material references
			def update_indices(data):
				if isinstance(data, dict):
					if 'index' in data and len(data) == 1:
						if data['index'] in old_to_new_tex:
							data['index'] = old_to_new_tex[data['index']]
					for v in data.values(): update_indices(v)
				elif isinstance(data, list):
					for item in data: update_indices(item)
			update_indices(gltf_materials)

			# Save
			gltf_data['images'] = new_img_list
			gltf_data['textures'] = new_tex_list
			
			with open(full_path, 'w', encoding='utf-8') as gf:
				json.dump(gltf_data, gf, indent=4)
				
		except Exception as e:
			self.report({'WARNING'}, f"Could not patch GLTF textures: {str(e)}")

	def _get_mesh_instance_data(self, obj, is_linked, relative_asset_path):
		"""Prepares instance data for JSON output."""
		local_matrix = obj.matrix_local
		loc, rot_quat, scale = local_matrix.decompose()
		return {
			"name": obj.name,
			"mesh_data": obj.data.name,
			"is_linked": is_linked,
			"asset_path": relative_asset_path,
			"location": {"x": loc.x, "y": loc.y, "z": loc.z},
			"rotation": {"x": rot_quat.x, "y": rot_quat.y, "z": rot_quat.z, "w": rot_quat.w},
			"scale": {"x": scale.x, "y": scale.y, "z": scale.z}
		}

	def invoke(self, context, event):
		props = context.scene.MavhodToolProps
		self._export_scene_path = bpy.path.abspath(props.scene_dest_path)
		self._export_asset_path = bpy.path.abspath(props.asset_dest_path) if props.asset_dest_path else ""
		self._asset_source_path = bpy.path.abspath(props.asset_source_path) if props.asset_source_path else ""
		
		# Capture texture export flags
		self._export_albedo = props.export_albedo
		self._export_metallic = props.export_metallic
		self._export_roughness = props.export_roughness
		self._export_normal = props.export_normal
		self._export_emission = props.export_emission
		self._export_alpha = props.export_alpha
		self._export_ao = props.export_ao

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
		json_path = os.path.join(self._export_scene_path, "scene_export.json")
		try:
			with open(json_path, 'w', encoding='utf-8') as f:
				json.dump({"instances": self._mesh_data_for_json}, f, indent=4)
		except Exception as e:
			self.report({'ERROR'}, f"Failed to write JSON: {str(e)}")
			return {'CANCELLED'}

		self.report(
			{'INFO'},
			f"Done! {self._total} instances, {len(self._exported_meshes)} unique GLTFs exported."
		)
		return {'FINISHED'}
