bl_info = {
	"name": "Mavhod Tool",
	"author": "Mavhod Realhod",
	"version": (1, 0, 0),
	"blender": (4, 2, 0),
	"location": "View3D > Mavhod Tool",
	"description": "Tools for importing FBX/GLTF with FePBR materials and mesh arrangement",
	"category": "Import-Export",
	"doc_url": "",
	"tracker_url": "",
}

import sys
import os

path = sys.path
flag = False
for item in path:
	if "test_view_3d" in item:
		flag = True
if flag is False:
	sys.path.append(os.path.join(os.path.dirname(__file__), "..", "test_view_3d"))

if "bpy" in locals():
	import importlib as imp
	from . import import_fbx
	from . import import_gltf
	from . import arrange_meshes
	from . import create_convex
	from . import export_scene
	imp.reload(import_fbx)
	imp.reload(import_gltf)
	imp.reload(arrange_meshes)
	imp.reload(create_convex)
	imp.reload(export_scene)
else:
	from . import import_fbx
	from . import import_gltf
	from . import arrange_meshes
	from . import create_convex
	from . import export_scene

import bpy

class FBXFileItem(bpy.types.PropertyGroup):
	filepath: bpy.props.StringProperty(name="File Path")

class MavhodToolSceneProps(bpy.types.PropertyGroup):
	entryPath: bpy.props.StringProperty(default="..")
	savePoint: bpy.props.StringProperty(default=".")
	exportAssetPath: bpy.props.StringProperty(
		name="Export Asset Path",
		description="Path for exporting assets",
		default="",
		subtype='DIR_PATH'
	)
	exportScenePath: bpy.props.StringProperty(
		name="Export Scene Path",
		description="Path for exporting scenes",
		default="",
		subtype='DIR_PATH'
	)
	fbx_files: bpy.props.CollectionProperty(type=FBXFileItem)

class MavhodToolPanel(bpy.types.Panel):
	bl_label = "Mavhod Tool"
	bl_idname = "TOOLS_PT_mavhod_tool_panel"
	bl_space_type = "VIEW_3D"
	bl_region_type = "UI"
	bl_category = "Mavhod"
	bl_context = "objectmode"

	def draw(self, context):
		layout = self.layout
		
		# ========== IMPORT SECTION ==========
		box = layout.box()
		box.label(text="Import", icon="IMPORT")
		
		col = box.column(align=True)
		col.operator("mavhod_tool.import_fbx_files", text="Import FBX", icon="FILE_3D")
		col.operator("mavhod_tool.import_gltf_files", text="Import GLTF/GLB", icon="FILE_3D")
		
		# ========== EXPORT SECTION ==========
		box = layout.box()
		box.label(text="Export", icon="EXPORT")
		box.operator("mavhod_tool.export_settings", text="Export Scene", icon="EXPORT")

		# ========== MESH TOOLS SECTION ==========
		box = layout.box()
		box.label(text="Mesh Tools", icon="MESH_DATA")
		
		col = box.column(align=True)
		col.operator("mavhod_tool.arrange_selected_meshes", text="Arrange Selected", icon="GRID")
		col.operator("mavhod_tool.create_convex_hull", text="Create Convex Hull", icon="MESH_ICOSPHERE")

classes = (
	FBXFileItem,
	MavhodToolSceneProps,
	import_fbx.ImportFBXFiles,
	import_gltf.ImportGLTFFiles,
	arrange_meshes.ArrangeSelectedMeshes,
	create_convex.CreateConvexHull,
	export_scene.MavhodExportSettings,
	export_scene.MavhodExportExecute,
	MavhodToolPanel,
)

def register():
	for cls in classes: bpy.utils.register_class(cls);
	bpy.types.Scene.MavhodToolProps = bpy.props.PointerProperty(type=MavhodToolSceneProps)

def unregister():
	for cls in classes: bpy.utils.unregister_class(cls);

if __name__ == "__main__":
	register()

