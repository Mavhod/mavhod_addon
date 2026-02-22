import bpy
import bmesh

class CreateConvexHull(bpy.types.Operator):
    """Create a convex hull mesh from the selected objects."""
    bl_idname = "mavhod_tool.create_convex_hull"
    bl_label = "Create Convex Hull"
    bl_options = {'REGISTER', 'UNDO'}

    decimate_ratio: bpy.props.FloatProperty(
        name="Decimate Ratio",
        description="Ratio of faces to keep (1.0 = keep all)",
        default=1.0,
        min=0.0,
        max=1.0
    )

    suffix: bpy.props.StringProperty(
        name="Suffix",
        description="Suffix to append to the new object name",
        default="_UCX"
    )

    keep_original: bpy.props.BoolProperty(
        name="Keep Original",
        description="Keep the original object selected after operation",
        default=True
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        new_objects = []

        for obj in selected_objects:
            if obj.type != 'MESH':
                continue

            # Duplicate the object
            new_obj = obj.copy()
            new_obj.data = obj.data.copy()
            new_obj.name = obj.name + self.suffix
            context.collection.objects.link(new_obj)
            
            # Select the new object and make it active
            bpy.ops.object.select_all(action='DESELECT')
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj

            # Use the standard operator `bpy.ops.mesh.convex_hull`
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.convex_hull(
                delete_unused=True, 
                use_existing_faces=True, 
                make_holes=False, 
                join_triangles=True, 
                face_threshold=0.698132, 
                shape_threshold=0.698132, 
                uvs=False, 
                vcols=False, 
                seam=False, 
                sharp=False, 
                materials=False
            )
            bpy.ops.object.mode_set(mode='OBJECT')

            # Apply Decimate if needed
            if self.decimate_ratio < 1.0:
                mod = new_obj.modifiers.new(name="Decimate", type='DECIMATE')
                mod.ratio = self.decimate_ratio
                bpy.ops.object.modifier_apply(modifier=mod.name)

            new_objects.append(new_obj)

        # Reselect original objects if requested
        if self.keep_original:
            for obj in selected_objects:
                obj.select_set(True)
            for new_obj in new_objects:
                new_obj.select_set(False) # Or keep them selected? 
                # User usually wants to see the result. 
                # Let's keep the NEW objects selected and the OLD ones deselected by default?
                # "Keep Original" implies we don't delete them.
                # If I want to inspect the result, I probably want the new ones selected.
                pass
        
        # Actually, let's select the NEW objects so the user can see them immediately.
        bpy.ops.object.select_all(action='DESELECT')
        for new_obj in new_objects:
            new_obj.select_set(True)
        context.view_layer.objects.active = new_objects[0] if new_objects else None

        return {'FINISHED'}
