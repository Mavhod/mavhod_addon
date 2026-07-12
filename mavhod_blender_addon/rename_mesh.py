import bpy

class RenameMeshToObject(bpy.types.Operator):
	"""Rename mesh data of the selected object(s) to match the object name"""
	bl_idname = "mavhod_tool.rename_mesh_to_object"
	bl_label = "Rename Mesh to Object"
	bl_description = "Rename the mesh data of selected objects to match their object names"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
		
		if not selected_objects:
			self.report({'WARNING'}, "No mesh objects selected")
			return {'CANCELLED'}
		
		renamed_count = 0
		for obj in selected_objects:
			if obj.data:
				old_name = obj.data.name
				new_name = obj.name
				if old_name != new_name:
					obj.data.name = new_name
					renamed_count += 1
					self.report({'INFO'}, f"Renamed mesh '{old_name}' in object '{new_name}'")
		
		if renamed_count == 0:
			self.report({'INFO'}, "All selected objects already have matching mesh names")
		else:
			self.report({'INFO'}, f"Renamed {renamed_count} mesh data block(s)")
			
		return {'FINISHED'}
