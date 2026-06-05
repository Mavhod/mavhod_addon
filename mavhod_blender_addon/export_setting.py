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
            "path_pairs": [],
            "export_texture_maps": {
                "albedo": props.export_albedo,
                "metallic": props.export_metallic,
                "roughness": props.export_roughness,
                "normal": props.export_normal,
                "emission": props.export_emission,
                "alpha": props.export_alpha,
                "ao": props.export_ao
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

    def execute(self, context):
        # This operator currently just manages the collection via the dialog.
        # Additional processing can be added here if needed.
        self.report({'INFO'}, "Settings updated")
        return {'FINISHED'}
