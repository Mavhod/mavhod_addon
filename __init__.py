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
	imp.reload(import_fbx)
	imp.reload(import_gltf)
	imp.reload(arrange_meshes)
else:
	from . import import_fbx
	from . import import_gltf
	from . import arrange_meshes

import bpy

class FBXFileItem(bpy.types.PropertyGroup):
	filepath: bpy.props.StringProperty(name="File Path")

class TestAddonSceneProps(bpy.types.PropertyGroup):
	entryPath: bpy.props.StringProperty(default="..")
	savePoint: bpy.props.StringProperty(default=".")
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
		col.operator("test_addon.import_fbx_files", text="Import FBX", icon="FILE_3D")
		col.operator("test_addon.import_gltf_files", text="Import GLTF/GLB", icon="FILE_3D")
		
		# ========== MESH TOOLS SECTION ==========
		box = layout.box()
		box.label(text="Mesh Tools", icon="MESH_DATA")
		
		col = box.column(align=True)
		col.operator("test_addon.arrange_selected_meshes", text="Arrange Selected", icon="GRID")

classes = (
	FBXFileItem,
	TestAddonSceneProps,
	import_fbx.ImportFBXFiles,
	import_gltf.ImportGLTFFiles,
	arrange_meshes.ArrangeSelectedMeshes,
	MavhodToolPanel,
)

def register():
	for cls in classes: bpy.utils.register_class(cls);
	bpy.types.Scene.TestAddonProps = bpy.props.PointerProperty(type=TestAddonSceneProps)

def unregister():
	for cls in classes: bpy.utils.unregister_class(cls);

if __name__ == "__main__":
	register()

