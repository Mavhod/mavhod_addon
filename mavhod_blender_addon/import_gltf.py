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
	
	def replace_with_fepbr(self, material, template_material):
		"""Replace Principled BSDF with FePBR node group, preserving inputs"""
		if not material.use_nodes:
			return

		nodes = material.node_tree.nodes
		links = material.node_tree.links
		
		# Find Principled BSDF and Material Output
		principled = None
		material_output = None
		gltf_output = None
		
		for node in nodes:
			if node.type == 'BSDF_PRINCIPLED':
				principled = node
			elif node.type == 'OUTPUT_MATERIAL':
				if not material_output: # Take the first one
					material_output = node
			elif node.type == 'GROUP' and "glTF Material Output" in node.node_tree.name:
				gltf_output = node
		
		if not principled:
			print(f"Warning: Principled BSDF not found in {material.name}")
			return
		
		# Get FePBR Node Tree from template
		fepbr_tree = None
		for node in template_material.node_tree.nodes:
			if node.type == 'GROUP' and "FePBR" in node.node_tree.name:
				fepbr_tree = node.node_tree
				break
				
		if not fepbr_tree:
			print("Warning: FePBR node group not found in template material")
			return
			
		# Create FePBR Group Node
		fepbr_node = nodes.new('ShaderNodeGroup')
		fepbr_node.node_tree = fepbr_tree
		fepbr_node.location = principled.location
		fepbr_node.width = 300
		
		# Move connections
		# Map Principled inputs to FePBR inputs
		# Principled Input Name -> FePBR Input Name
		input_map = {
			'Base Color': 'Albedo Map',
			'Metallic': 'Metallic',
			'Roughness': 'Roughness',
			'Normal': 'Normal Map',
			'Emission': 'Emission',
			'Alpha': 'Alpha Map',
		}
		
		for principled_socket, fepbr_socket_name in input_map.items():
			if principled_socket in principled.inputs and fepbr_socket_name in fepbr_node.inputs:
				socket = principled.inputs[principled_socket]
				if socket.is_linked:
					link = socket.links[0]
					from_socket = link.from_socket
					
					# Special handling for Normal Map
					# If linked from a Normal Map node, check if we need to bypass it
					if principled_socket == 'Normal' and link.from_node.type == 'NORMAL_MAP':
						# Trace back to the input of Normal Map node
						nm_node = link.from_node
						if 'Color' in nm_node.inputs and nm_node.inputs['Color'].is_linked:
							from_socket = nm_node.inputs['Color'].links[0].from_socket
					
					# Create new link
					links.new(from_socket, fepbr_node.inputs[fepbr_socket_name])
					
		# Handle AO (Occlusion) from glTF Material Output
		if gltf_output and 'Occlusion' in gltf_output.inputs:
			socket = gltf_output.inputs['Occlusion']
			if socket.is_linked:
				from_socket = socket.links[0].from_socket
				if 'AO' in fepbr_node.inputs:
					links.new(from_socket, fepbr_node.inputs['AO'])
					
		# Connect FePBR to Material Output
		if material_output and 'Surface' in material_output.inputs:
			# Find output of FePBR (usually 'BSDF')
			output_socket = None
			for out in fepbr_node.outputs:
				if out.type == 'SHADER':
					output_socket = out
					break
			
			if output_socket:
				links.new(output_socket, material_output.inputs['Surface'])
				
		# Remove old Principled BSDF
		nodes.remove(principled)

	def load_template_materials(self):
		"""Append materials from template.blend"""
		template_path = os.path.join(os.path.dirname(__file__), "template.blend")
		if not os.path.exists(template_path):
			print(f"Warning: template.blend not found at {template_path}")
			return None

		# Load materials from template
		with bpy.data.libraries.load(template_path, link=False) as (data_from, data_to):
			data_to.materials = data_from.materials

		# Return the first loaded material if any
		if data_to.materials:
			return data_to.materials[0]
		return None

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
		
		# Load material from template
		template_material = self.load_template_materials()
		if template_material:
			print(f"=== Loaded template material: {template_material.name} ===")
		else:
			print("=== No template material loaded ===")

		print("=== Importing GLTF Files ===")
		for filepath in valid_files:
			try:
				# Get objects before import
				objects_before = set(context.scene.objects)
				
				# Import GLTF/GLB
				bpy.ops.import_scene.gltf(filepath=filepath)
				print(f"✓ Imported: {filepath}")
				
				# Get newly imported objects
				objects_after = set(context.scene.objects)
				new_objects = objects_after - objects_before
				
				for obj in new_objects:
					if obj.type == 'MESH':
						# Process all materials on the object
						for i, original_mat in enumerate(obj.data.materials):
							if not original_mat:
								continue
							
							# Make a full copy of the original material (preserves nodes, drivers, etc.)
							new_mat = original_mat.copy()
							new_mat.name = f"{original_mat.name}_FePBR"
							
							# Add FePBR node to the new material and connect everything
							self.replace_with_fepbr(new_mat, template_material)
							
							# Replace the material in the current slot
							obj.data.materials[i] = new_mat
				
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
