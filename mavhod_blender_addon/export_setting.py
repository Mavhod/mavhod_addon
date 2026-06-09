import bpy
import os
import json
from bpy_extras.io_utils import ExportHelper, ImportHelper

class MavhodAddPathPair(bpy.types.Operator):
    """Add a new source/destination path pair"""
    bl_idname = "mavhod_tool.add_path_pair"
    bl_label = "Add Path Pair"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.MavhodToolProps.path_pairs.add()
        return {'FINISHED'}

class MavhodRemovePathPair(bpy.types.Operator):
    """Remove a source/destination path pair"""
    bl_idname = "mavhod_tool.remove_path_pair"
    bl_label = "Remove Path Pair"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty()

    def execute(self, context):
        context.scene.MavhodToolProps.path_pairs.remove(self.index)
        return {'FINISHED'}

class MavhodSaveSettingsJSON(bpy.types.Operator, ExportHelper):
    """Save path pair settings to a JSON file"""
    bl_idname = "mavhod_tool.save_settings_json"
    bl_label = "Save Settings"
    bl_options = {'REGISTER'}

    # ExportHelper mixin uses this
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(
        default="*.json",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer exceeds Blender's limit
    )

    def execute(self, context):
        props = context.scene.MavhodToolProps
        data = {
            "scene_extension": props.scene_extension,
            "object_extension": props.object_extension,
            "light_extension": props.light_extension,
            "path_pairs": [],
            "export_metadata": {
                "metadata_node": props.export_metadata_node,
                "metadata_mesh": props.export_metadata_mesh,
                "metadata_material": props.export_metadata_material,
                "metadata_scene": props.export_metadata_scene,
                "metadata_instance": props.export_metadata_instance,
                "metadata_level": props.export_metadata_level,
                "metadata_light": props.export_metadata_light
            }
        }
        for pair in props.path_pairs:
            data["path_pairs"].append({
                "source_path": pair.source_path,
                "dest_path": pair.dest_path
            })
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            self.report({'INFO'}, f"Saved settings to {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to save settings: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}

class MavhodLoadSettingsJSON(bpy.types.Operator, ImportHelper):
    """Load path pair settings from a JSON file"""
    bl_idname = "mavhod_tool.load_settings_json"
    bl_label = "Load Settings"
    bl_options = {'REGISTER', 'UNDO'}

    # ImportHelper mixin uses this
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(
        default="*.json",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        props = context.scene.MavhodToolProps
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 1. Load path pairs
            props.path_pairs.clear()
            path_pairs_data = data.get("path_pairs", [])
            for item in path_pairs_data:
                pair = props.path_pairs.add()
                pair.source_path = item.get("source_path", "")
                pair.dest_path = item.get("dest_path", "")
            
            # 2. Load extensions
            if "scene_extension" in data:
                props.scene_extension = data["scene_extension"]
            if "object_extension" in data:
                props.object_extension = data["object_extension"]
            if "light_extension" in data:
                props.light_extension = data["light_extension"]
            
            if "export_metadata" in data:
                tex_data = data["export_metadata"]
                props.export_metadata_node = tex_data.get("metadata_node", True)
                props.export_metadata_mesh = tex_data.get("metadata_mesh", True)
                props.export_metadata_material = tex_data.get("metadata_material", True)
                props.export_metadata_scene = tex_data.get("metadata_scene", True)
                props.export_metadata_instance = tex_data.get("metadata_instance", True)
                props.export_metadata_level = tex_data.get("metadata_level", True)
                props.export_metadata_light = tex_data.get("metadata_light", True)
            
            self.report({'INFO'}, f"Loaded settings from {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load settings: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}

class MavhodExportSetting(bpy.types.Operator):
    """Open dialog to configure source and destination path pairs"""
    bl_idname = "mavhod_tool.export_setting"
    bl_label = "Export Setting"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=600)

    def draw(self, context):
        layout = self.layout
        props = context.scene.MavhodToolProps
        
        layout.label(text="Configure Source and Destination Paths:")
        
        col_ext = layout.column(align=True)
        col_ext.prop(props, "scene_extension", text="Scene Extension")
        col_ext.prop(props, "object_extension", text="Object Extension")
        col_ext.prop(props, "light_extension", text="Light Extension")
        
        layout.label(text="Export Metadata:")
        box_meta = layout.box()
        col_meta = box_meta.column(align=True)
        col_meta.label(text="GLTF Content:")
        row_meta1 = col_meta.row(align=True)
        row_meta1.prop(props, "export_metadata_node", text="Node")
        row_meta1.prop(props, "export_metadata_mesh", text="Mesh")
        row_meta1.prop(props, "export_metadata_material", text="Material")
        row_meta1.prop(props, "export_metadata_scene", text="Scene")
        
        col_meta.separator()
        col_meta.label(text="Aggregate JSON:")
        row_meta2 = col_meta.row(align=True)
        row_meta2.prop(props, "export_metadata_instance", text="Instance")
        row_meta2.prop(props, "export_metadata_level", text="Level (Global)")
        row_meta2.prop(props, "export_metadata_light", text="Light")
        
        layout.separator()
        
        col = layout.column(align=True)
        for i, pair in enumerate(props.path_pairs):
            row = col.row(align=True)
            box = row.box()
            inner_col = box.column(align=True)
            inner_col.prop(pair, "source_path", text=f"Source {i+1}")
            inner_col.prop(pair, "dest_path", text=f"Dest {i+1}")
            
            # Remove button
            remove_op = row.operator("mavhod_tool.remove_path_pair", text="", icon="X")
            remove_op.index = i
            
        layout.operator("mavhod_tool.add_path_pair", text="Add Path Pair", icon="ADD")
 
        layout.separator()
        row = layout.row(align=True)
        row.operator("mavhod_tool.load_settings_json", text="Load", icon="FILE_FOLDER")
        row.operator("mavhod_tool.save_settings_json", text="Save", icon="FILE_TICK")

        layout.separator()
        layout.operator("mavhod_tool.export_light_settings", text="Export Light", icon="LIGHT_DATA")

    def execute(self, context):
        # This operator currently just manages the collection via the dialog.
        # Additional processing can be added here if needed.
        self.report({'INFO'}, "Settings updated")
        return {'FINISHED'}
