import bpy
import bmesh

class CreateDoubleSided(bpy.types.Operator):
	bl_idname = "mavhod_tool.create_double_sided"
	bl_label = "Create Double Sided"
	bl_description = "Create double-sided faces with symmetrical offset (Shrink/Fatten) for selected faces"
	bl_options = {'REGISTER', 'UNDO'}

	offset: bpy.props.FloatProperty(
		name="Offset",
		description="Distance to offset both front and back faces (Shrink/Fatten)",
		default=0.0001,
		min=-1.0,
		max=1.0,
		step=0.0001,
		precision=6
	)

	@classmethod
	def poll(cls, context):
		return context.mode == 'EDIT_MESH' and context.active_object and context.active_object.type == 'MESH'

	def execute(self, context):
		obj = context.active_object
		if not obj or obj.type != 'MESH':
			self.report({'WARNING'}, "Active object must be a Mesh")
			return {'CANCELLED'}

		bm = bmesh.from_edit_mesh(obj.data)
		bm.faces.ensure_lookup_table()

		selected_faces = [f for f in bm.faces if f.select]
		if not selected_faces:
			self.report({'WARNING'}, "No faces selected")
			return {'CANCELLED'}

		added_count = 0
		front_displacements = {}  # v -> normal displacement vector

		for f in selected_faces:
			verts = list(f.verts)
			reversed_verts = list(reversed(verts))
			face_normal = f.normal.copy()

			if self.offset != 0.0:
				# 1. Back face: create duplicated vertices offset by - (face_normal * offset)
				new_verts = []
				for v in reversed_verts:
					offset_co = v.co - (face_normal * self.offset)
					new_v = bm.verts.new(offset_co)
					new_verts.append(new_v)

				# Track front face displacement (+face_normal * offset) for original vertices
				for v in verts:
					if v not in front_displacements:
						front_displacements[v] = face_normal * self.offset
			else:
				new_verts = reversed_verts

			try:
				new_f = bm.faces.new(new_verts)
				new_f.material_index = f.material_index
				new_f.smooth = f.smooth

				# Copy UV layer data
				for uv_layer in bm.loops.layers.uv:
					vert_to_uv = {loop.vert: loop[uv_layer].uv.copy() for loop in f.loops}
					for loop, orig_v in zip(new_f.loops, reversed_verts):
						if orig_v in vert_to_uv:
							loop[uv_layer].uv = vert_to_uv[orig_v]

				new_f.select = True
				added_count += 1
			except ValueError:
				# Face with this winding already exists
				pass

		# 2. Front face: displace original vertices by + (face_normal * offset)
		if self.offset != 0.0:
			for v, disp in front_displacements.items():
				v.co += disp

		if added_count > 0:
			bmesh.update_edit_mesh(obj.data)
			self.report({'INFO'}, f"Created {added_count} double-sided face(s) with symmetrical offset ±{self.offset:.6f}")
			return {'FINISHED'}
		else:
			self.report({'WARNING'}, "Double-sided face(s) already exist for selected faces")
			return {'CANCELLED'}
