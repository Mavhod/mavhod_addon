import bpy
import os

class ImportGLTFFiles(bpy.types.Operator):
	bl_idname = "mavhod_tool.import_gltf_files"
	bl_label = "Import GLTF Files"
	bl_description = "Select and import multiple GLTF/GLB files"
	
	# File browser properties
	filepath: bpy.props.StringProperty(subtype="FILE_PATH")
	files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement)
	directory: bpy.props.StringProperty(subtype="DIR_PATH")
	
	# Filter for GLTF and GLB files
	filter_glob: bpy.props.StringProperty(
		default="*.gltf;*.glb",
		options={'HIDDEN'}
	)
	
	def execute(self, context):
		# Import all GLTF files into the scene
		imported_count = 0
		print("\n=== Selected GLTF Files ===")
		
		# Collect all valid files
		valid_files = []
		for file in self.files:
			if file.name.lower().endswith(('.gltf', '.glb')):
				full_path = os.path.join(self.directory, file.name)
				valid_files.append(full_path)
				print(full_path)
		
		print(f"=== Total: {len(valid_files)} file(s) ===\n")
		
		print("=== Importing GLTF Files ===")
		for filepath in valid_files:
			try:
				# Import GLTF/GLB
				bpy.ops.import_scene.gltf(filepath=filepath)
				print(f"✓ Imported: {filepath}")
				
				imported_count += 1
			except Exception as e:
				print(f"✗ Failed to import {filepath}: {str(e)}")
				import traceback
				traceback.print_exc()
		
		print(f"\n=== Successfully imported {imported_count}/{len(valid_files)} file(s) ===\n")
		
		self.report({'INFO'}, f"Imported {imported_count}/{len(valid_files)} GLTF file(s)")
		return {'FINISHED'}
				
	def invoke(self, context, event):
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}
