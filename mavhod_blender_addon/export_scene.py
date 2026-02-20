import bpy
import json
import os
import shutil


class MavhodExportSettings(bpy.types.Operator):
	"""Set export paths and start export"""
	bl_idname = "test_addon.export_settings"
	bl_label = "Set Export Paths"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		# Kick off the modal export operator
		bpy.ops.test_addon.export_execute('INVOKE_DEFAULT')
		return {'FINISHED'}

	def invoke(self, context, event):
		return context.window_manager.invoke_props_dialog(self)

	def draw(self, context):
		layout = self.layout
		props = context.scene.TestAddonProps
		layout.prop(props, "exportAssetPath")
		layout.prop(props, "exportScenePath")


class MavhodExportExecute(bpy.types.Operator):
	"""Modal export operator that processes one mesh per tick for visible progress"""
	bl_idname = "test_addon.export_execute"
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
				abs_lib_path = bpy.path.abspath(lib.filepath)
				source_folder = os.path.basename(os.path.dirname(abs_lib_path))
				is_linked = True
			elif bpy.data.filepath:
				abs_blend_path = bpy.path.abspath(bpy.data.filepath)
				source_folder = os.path.basename(os.path.dirname(abs_blend_path))

			# Set root directory for export
			# Linked objects -> Asset Path, Local objects -> Scene Path
			root_dir = self._export_asset_path if is_linked else self._export_scene_path
			
			if not root_dir:
				# Fallback if one path is missing but needed
				root_dir = self._export_scene_path if self._export_scene_path else self._export_asset_path

			# Construct paths
			# Local objects exported directly to root_dir, Linked objects to source_folder
			if is_linked:
				parent_folder_path = os.path.join(root_dir, source_folder)
				relative_asset_path = os.path.join(source_folder, f"{mesh_data_name}.gltf")
				dest_display = f"{source_folder}/"
			else:
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

				# Collect images and determine their new paths
				seen_ids = set()
				ordered_images = []  # list of (img_data_block, abs_src_path, final_abs_dst, relative_uri_for_gltf)
				for slot in obj.material_slots:
					if slot.material and slot.material.use_nodes:
						for node in slot.material.node_tree.nodes:
							if node.type == 'TEX_IMAGE' and node.image:
								img = node.image
								if id(img) not in seen_ids:
									seen_ids.add(id(img))
									
									src_path = bpy.path.abspath(img.filepath) if img.filepath else None
									if src_path and os.path.isfile(src_path):
										# Determine image source folder
										img_source_folder = os.path.basename(os.path.dirname(src_path))
										img_filename = os.path.basename(src_path)
										
										# Target texture folder: tex_root / source_folder / texture /
										target_tex_dir = os.path.join(tex_root, img_source_folder, "texture")
										os.makedirs(target_tex_dir, exist_ok=True)
										
										abs_dst = os.path.join(target_tex_dir, img_filename)
										
										# Calculate relative path from GLTF dir to texture file
										# parent_folder_path is the GLTF dir
										rel_uri = os.path.relpath(abs_dst, parent_folder_path)
										
										ordered_images.append((img, src_path, abs_dst, rel_uri))
									else:
										ordered_images.append((img, None, None, None))

				# Isolate object for export
				bpy.ops.object.select_all(action='DESELECT')
				obj.select_set(True)
				context.view_layer.objects.active = obj

				full_path = os.path.join(parent_folder_path, f"{mesh_data_name}.gltf")

				# Export with AUTO image format (creates temporary files we'll replace/ignore)
				bpy.ops.export_scene.gltf(
					filepath=full_path,
					use_selection=True,
					export_format='GLTF_SEPARATE',
					export_image_format='AUTO',
					export_apply=True
				)
				self._exported_meshes.add(mesh_data_name)

				# Patch GLTF and handle textures
				if os.path.isfile(full_path):
					try:
						with open(full_path, 'r', encoding='utf-8') as gf:
							gltf_data = json.load(gf)

						gltf_images = gltf_data.get('images', [])
						for i, (img, src_path, abs_dst, rel_uri) in enumerate(ordered_images):
							if i >= len(gltf_images): break
							gltf_img = gltf_images[i]
							old_uri = gltf_img.get('uri', '')
							if not old_uri or 'bufferView' in gltf_img: continue

							# Remove the default exported images adjacent to GLTF
							exported_temp_path = os.path.join(parent_folder_path, old_uri)
							if os.path.isfile(exported_temp_path):
								os.remove(exported_temp_path)

							if abs_dst:
								# Copy original texture to its shared home in Asset Path
								if src_path and os.path.isfile(src_path) and not os.path.exists(abs_dst):
									shutil.copy2(src_path, abs_dst)
								
								# Update GLTF to point to the shared Asset Path location
								gltf_img['uri'] = rel_uri.replace("\\", "/") # Ensure web-style paths

						with open(full_path, 'w', encoding='utf-8') as gf:
							json.dump(gltf_data, gf, indent=4)
					except Exception as e:
						self.report({'WARNING'}, f"Could not reorganize textures/patch GLTF: {str(e)}")

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
		props = context.scene.TestAddonProps
		self._export_scene_path = bpy.path.abspath(props.exportScenePath)
		self._export_asset_path = bpy.path.abspath(props.exportAssetPath) if props.exportAssetPath else ""

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
