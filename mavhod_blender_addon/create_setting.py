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
            
            # 2. Load texture map flags
            tex_data = data.get("export_texture_maps", {})
            props.export_albedo = tex_data.get("albedo", True)
            props.export_metallic = tex_data.get("metallic", True)
            props.export_roughness = tex_data.get("roughness", True)
            props.export_normal = tex_data.get("normal", True)
            props.export_emission = tex_data.get("emission", True)
            props.export_alpha = tex_data.get("alpha", True)
            props.export_ao = tex_data.get("ao", True)
            
            self.report({'INFO'}, f"Loaded settings from {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load settings: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}

class MavhodCreateSetting(bpy.types.Operator):
    """Open dialog to configure source and destination path pairs"""
    bl_idname = "mavhod_tool.create_setting"
    bl_label = "Create Setting"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=600)

    def draw(self, context):
        layout = self.layout
        props = context.scene.MavhodToolProps
        
        layout.label(text="Configure Source and Destination Paths:")
        
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
        
        # Texture Map Export Settings
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

        layout.separator()
        row = layout.row(align=True)
        row.operator("mavhod_tool.load_settings_json", text="Load", icon="FILE_FOLDER")
        row.operator("mavhod_tool.save_settings_json", text="Save", icon="FILE_TICK")

    def execute(self, context):
        # This operator currently just manages the collection via the dialog.
        # Additional processing can be added here if needed.
        self.report({'INFO'}, "Settings updated")
        return {'FINISHED'}
