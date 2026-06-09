import bpy
import json
import os
from .export_utils import convert_zup_to_yup
from bpy_extras.io_utils import ExportHelper


class MavhodExportLightSettings(bpy.types.Operator, ExportHelper):
	bl_idname = "mavhod_tool.export_light_settings"
	bl_label = "Export Light"
	bl_options = {'REGISTER', 'UNDO'}

	filename_ext = ".json"
	filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'}, maxlen=255,)

	def invoke(self, context, event):
		props = context.scene.MavhodToolProps
		ext = props.light_extension
		if not ext.startswith("."):
			ext = "." + ext
		self.filename_ext = ext
		self.filter_glob = "*" + ext
		return super().invoke(context, event)

	def execute(self, context):
		bpy.ops.mavhod_tool.export_light_execute('INVOKE_DEFAULT', filepath=self.filepath)
		return {'FINISHED'}


class MavhodExportLightExecute(bpy.types.Operator):
	"""Export selected lights to a JSON file"""
	bl_idname = "mavhod_tool.export_light_execute"
	bl_label = "Exporting Lights..."
	bl_options = set()

	filepath: bpy.props.StringProperty(options={'HIDDEN'})

	@staticmethod
	def _collect_light_data(context):
		"""Collect selected light objects and prepare data for JSON export"""
		props = context.scene.MavhodToolProps

		lights_data = []
		for obj in context.selected_objects:
			if obj.type != 'LIGHT':
				continue

			light = obj.data
			world_matrix = obj.matrix_world
			loc, rot_quat, scale = world_matrix.decompose()

			loc_G, rot_quat_G, scale_G = convert_zup_to_yup(loc, rot_quat, scale)
			# Map Blender light types to common names
			light_type_map = {
				'POINT': 'point',
				'SUN': 'directional',
				'SPOT': 'spot',
				'AREA': 'area'
			}
			bl_type = light.type
			game_type = light_type_map.get(bl_type, bl_type.lower())

			light_entry = {
				"name": obj.name,
				"type": game_type,
				"color": {"r": light.color.r, "g": light.color.g, "b": light.color.b},
				"energy": light.energy,
				"location": {"x": loc_G.x, "y": loc_G.y, "z": loc_G.z},
				"rotation": {"x": rot_quat_G.x, "y": rot_quat_G.y, "z": rot_quat_G.z, "w": rot_quat_G.w},
				"scale": {"x": scale_G.x, "y": scale_G.y, "z": scale_G.z}
			}

			# Type-specific properties
			if bl_type == 'SPOT':
				light_entry["spot_size"] = light.spot_size
				light_entry["spot_blend"] = light.spot_blend

			if bl_type == 'AREA':
				light_entry["shape"] = light.shape
				light_entry["size"] = light.size
				if light.shape in {'SQUARE', 'DISK'}:
					light_entry["size_y"] = light.size_y

			if bl_type == 'SUN':
				light_entry["angle"] = light.angle

			# Optional metadata
			if props.export_metadata_light:
				extras = {}
				for key in obj.keys():
					if key == "_RNA_UI":
						continue
					val = obj[key]
					if hasattr(val, "to_list"):
						val = val.to_list()
					extras[key] = val
				# Also include light datablock custom properties
				for key in light.keys():
					if key == "_RNA_UI":
						continue
					val = light[key]
					if hasattr(val, "to_list"):
						val = val.to_list()
					extras[key] = val
				if extras:
					light_entry["metadata"] = extras

			lights_data.append(light_entry)

		return lights_data

	def execute(self, context):
		if not self.filepath:
			self.report({'WARNING'}, "Export filepath not defined!")
			return {'CANCELLED'}

		export_scene_path = os.path.realpath(os.path.dirname(self.filepath))

		try:
			os.makedirs(export_scene_path, exist_ok=True)

			light_data = MavhodExportLightExecute._collect_light_data(context)

			if not light_data:
				self.report({'WARNING'}, "No selected lights found!")
				return {'CANCELLED'}

			light_json_data = {"lights": light_data}
			with open(self.filepath, 'w', encoding='utf-8') as f:
				json.dump(light_json_data, f, indent=4)

			self.report({'INFO'}, f"Exported {len(light_data)} light(s) to {self.filepath}")
		except Exception as e:
			self.report({'ERROR'}, f"Could not save light JSON file: {str(e)}")
			return {'CANCELLED'}

		return {'FINISHED'}
