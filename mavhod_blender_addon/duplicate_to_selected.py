import bpy

class DuplicateToSelected(bpy.types.Operator):
    """Duplicate the active object and match the transform of other selected objects"""
    bl_idname = "mavhod_tool.duplicate_to_selected"
    bl_label = "Duplicate to Selected"
    bl_description = "Duplicate the active (orange) object and place a copy at the transform of each other selected object"
    bl_options = {'REGISTER', 'UNDO'}

    delete_targets: bpy.props.BoolProperty(
        name="Delete Targets",
        description="Delete target objects after duplicating",
        default=False
    )

    linked_duplicates: bpy.props.BoolProperty(
        name="Linked Duplicates",
        description="Create linked duplicates (share object data block like Alt+D)",
        default=True
    )

    def execute(self, context):
        active_obj = context.active_object
        selected_objs = context.selected_objects

        if not active_obj:
            self.report({'WARNING'}, "No active object selected (orange highlight)")
            return {'CANCELLED'}

        if active_obj not in selected_objs:
            self.report({'WARNING'}, "Active object must be selected")
            return {'CANCELLED'}

        # Targets are selected objects other than the active object
        targets = [obj for obj in selected_objs if obj != active_obj]

        if not targets:
            self.report({'WARNING'}, "No target objects selected. Please select other objects to place duplicates on")
            return {'CANCELLED'}

        # Determine if we should create a linked duplicate.
        # We create a linked duplicate if the user requested it, or if the source object's
        # data is already shared (users > 1).
        is_linked = self.linked_duplicates
        if active_obj.data and active_obj.data.users > 1:
            is_linked = True

        duplicated_objects = []

        # Duplicate active object at the location of each target
        for target in targets:
            # Copy the object structure
            new_obj = active_obj.copy()

            # If not linking duplicates, duplicate the underlying data block (mesh, curve, light, etc.)
            if not is_linked and new_obj.data:
                new_obj.data = new_obj.data.copy()

            # Align world transform
            new_obj.matrix_world = target.matrix_world.copy()

            # Link to the same collections as the target object
            if target.users_collection:
                for col in target.users_collection:
                    col.objects.link(new_obj)
            else:
                context.collection.objects.link(new_obj)

            duplicated_objects.append(new_obj)

        deleted_count = 0
        # Delete original target objects if requested
        if self.delete_targets:
            deleted_count = len(targets)
            for target in targets:
                bpy.data.objects.remove(target, do_unlink=True)

        # Select the newly created duplicates and make active
        bpy.ops.object.select_all(action='DESELECT')
        for obj in duplicated_objects:
            obj.select_set(True)
        if duplicated_objects:
            context.view_layer.objects.active = duplicated_objects[0]

        msg = f"Duplicated '{active_obj.name}' onto {len(duplicated_objects)} target(s)"
        if deleted_count > 0:
            msg += f" and deleted {deleted_count} target(s)"
        self.report({'INFO'}, msg)

        return {'FINISHED'}
