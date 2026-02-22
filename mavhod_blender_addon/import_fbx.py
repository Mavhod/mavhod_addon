import bpy
import os

class ImportFBXFiles(bpy.types.Operator):
	bl_idname = "mavhod_tool.import_fbx_files"
	bl_label = "Import FBX Files"
	bl_description = "Select and import multiple FBX files"
	
	# File browser properties
	filepath: bpy.props.StringProperty(subtype="FILE_PATH")
	files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement)
	directory: bpy.props.StringProperty(subtype="DIR_PATH")
	
	def get_texture_paths_from_object(self, obj):
		"""Extract texture paths from an object's materials"""
		texture_paths = []
		
		if obj.type != 'MESH' or not obj.data.materials:
			return texture_paths
		
		for mat in obj.data.materials:
			if mat is None:
				continue
			
			# Check if material uses nodes
			if mat.use_nodes:
				for node in mat.node_tree.nodes:
					# Look for Image Texture nodes
					if node.type == 'TEX_IMAGE' and node.image:
						if node.image.filepath:
							# Get absolute path
							img_path = bpy.path.abspath(node.image.filepath)
							texture_paths.append({
								'material': mat.name,
								'node': node.name,
								'path': img_path,
								'image_name': node.image.name
							})
		
		return texture_paths
	
	def execute(self, context):
		# Clear existing files
		context.scene.MavhodToolProps.fbx_files.clear()
		
		# Add selected files to the collection and print full path
		print("\n=== Selected FBX Files ===")
		for file in self.files:
			if file.name.lower().endswith('.fbx'):
				item = context.scene.MavhodToolProps.fbx_files.add()
				full_path = os.path.join(self.directory, file.name)
				item.filepath = full_path
				print(full_path)
		print(f"=== Total: {len(context.scene.MavhodToolProps.fbx_files)} file(s) ===\n")
		
		# Import all FBX files into the scene
		imported_count = 0
		print("=== Importing FBX Files ===")
		for item in context.scene.MavhodToolProps.fbx_files:
			try:
				# Get objects before import
				objects_before = set(context.scene.objects)
				
				# Import FBX
				bpy.ops.import_scene.fbx(filepath=item.filepath)
				print(f"✓ Imported: {item.filepath}")
				
				# Get newly imported objects
				objects_after = set(context.scene.objects)
				new_objects = objects_after - objects_before
				
				# Extract texture paths from new objects
				print(f"  📁 Textures found:")
				texture_found = False
				for obj in new_objects:
					textures = self.get_texture_paths_from_object(obj)
					for tex in textures:
						print(f"    • Material: {tex['material']}")
						print(f"      Image: {tex['image_name']}")
						print(f"      Path: {tex['path']}")
						texture_found = True
				
				if not texture_found:
					print(f"    (No textures found)")
				
				imported_count += 1
			except Exception as e:
				print(f"✗ Failed to import {item.filepath}: {str(e)}")
		
		print(f"\n=== Successfully imported {imported_count}/{len(context.scene.MavhodToolProps.fbx_files)} file(s) ===\n")
		
		self.report({'INFO'}, f"Imported {imported_count}/{len(context.scene.MavhodToolProps.fbx_files)} FBX file(s)")
		return {'FINISHED'}
	
	def invoke(self, context, event):
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}
