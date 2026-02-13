import bpy
import math
import mathutils

class ArrangeSelectedMeshes(bpy.types.Operator):
	bl_idname = "test_addon.arrange_selected_meshes"
	bl_label = "Arrange Selected Meshes"
	bl_description = "Arrange selected meshes in a grid layout without overlapping"
	bl_options = {'REGISTER', 'UNDO'}
	
	# Properties for grid arrangement
	spacing: bpy.props.FloatProperty(
		name="Spacing",
		description="Space between objects",
		default=2.0,
		min=0.1,
		max=100.0
	)
	
	columns: bpy.props.IntProperty(
		name="Columns",
		description="Number of columns in the grid (0 = auto)",
		default=0,
		min=0,
		max=100
	)
	
	def get_object_bounds_size(self, obj):
		"""Get the bounding box size of an object"""
		if obj.type == 'MESH':
			# Get bounding box in world space
			bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
			
			# Calculate min and max for each axis
			min_x = min(corner.x for corner in bbox_corners)
			max_x = max(corner.x for corner in bbox_corners)
			min_y = min(corner.y for corner in bbox_corners)
			max_y = max(corner.y for corner in bbox_corners)
			min_z = min(corner.z for corner in bbox_corners)
			max_z = max(corner.z for corner in bbox_corners)
			
			return (max_x - min_x, max_y - min_y, max_z - min_z)
		return (0, 0, 0)
	
	def execute(self, context):
		# Get selected objects
		selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
		
		if len(selected_objects) == 0:
			self.report({'WARNING'}, "No mesh objects selected")
			return {'CANCELLED'}
		
		print(f"\n=== Smart Arranging {len(selected_objects)} mesh(es) ===")
		print(f"Spacing: {self.spacing} units")
		
		# Get size for each object and sort by size (largest first for better packing)
		objects_with_size = []
		for obj in selected_objects:
			size = self.get_object_bounds_size(obj)
			area = size[0] * size[1]  # Calculate area for sorting
			objects_with_size.append({
				'obj': obj,
				'size': size,
				'area': area
			})
		
		# Sort by area (largest first)
		objects_with_size.sort(key=lambda x: x['area'], reverse=True)
		
		# Smart packing algorithm
		if self.columns > 0:
			cols = self.columns
		else:
			# Auto-calculate columns
			cols = math.ceil(math.sqrt(len(selected_objects)))
		
		print(f"Target columns: {cols}")
		
		# Track the current position and row heights
		current_x = 0
		current_y = 0
		current_row_height = 0
		current_col = 0
		row_num = 0
		
		# Arrange objects with smart packing
		for i, item in enumerate(objects_with_size):
			obj = item['obj']
			size = item['size']
			
			# Check if we need to move to next row
			if current_col >= cols:
				# Move to next row
				current_x = 0
				current_y -= (current_row_height + self.spacing)
				current_row_height = 0
				current_col = 0
				row_num += 1
			
			# Place object at current position
			obj.location = (current_x, current_y, 0)
			
			print(f"  {i+1}. {obj.name} (size: {size[0]:.2f}×{size[1]:.2f}) → ({current_x:.2f}, {current_y:.2f}, 0.00)")
			
			# Update position for next object
			current_x += size[0] + self.spacing
			current_row_height = max(current_row_height, size[1])
			current_col += 1
		
		print(f"=== Arrangement complete ({row_num + 1} rows used) ===\n")
		
		self.report({'INFO'}, f"Smart arranged {len(selected_objects)} mesh(es) in {row_num + 1} rows")
		return {'FINISHED'}
	
	def invoke(self, context, event):
		# Show dialog with options
		return context.window_manager.invoke_props_dialog(self)
	
	def draw(self, context):
		layout = self.layout
		layout.prop(self, "spacing")
		layout.prop(self, "columns")
		layout.label(text="(0 columns = auto square grid)")
