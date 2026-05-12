import bpy
import json
import os
import shutil
from bpy_extras.io_utils import ExportHelper

def get_robust_relpath(target_path, base_path):
	"""
	คำนวณหาพาธสัมพัทธ์ (Relative Path) จาก base_path ไปยัง target_path
	เพื่อให้แน่ใจว่าทั้งสองพาธเป็นพาธสัมบูรณ์ (Absolute Path) และทำการตรวจสอบลิงก์ (Symlinks) ก่อนคำนวณ
	"""
	if not target_path or not base_path: return target_path
	# แปลงพาธให้เป็นพาธสัมบูรณ์ที่แน่นอน (Resolved Absolute Path)
	abs_target = os.path.realpath(bpy.path.abspath(target_path))
	abs_base = os.path.realpath(bpy.path.abspath(base_path))
	#
	try:
		# พยายามหาพาธสัมพัทธ์
		return os.path.relpath(abs_target, abs_base)
	except (ValueError, Exception):
		# หากพาธอยู่คนละไดรฟ์ (ใน Windows) หรือเกิดข้อผิดพลาดอื่น ให้ส่งคืนพาธสัมบูรณ์เดิม
		return abs_target

class MavhodExportSettings(bpy.types.Operator, ExportHelper):
	bl_idname = "mavhod_tool.export_settings"
	bl_label = "Export Scene"
	bl_options = {'REGISTER', 'UNDO'}

	filename_ext = ".json"
	filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'}, maxlen=255,)

	def execute(self, context):
		bpy.ops.mavhod_tool.export_execute('INVOKE_DEFAULT', filepath=self.filepath)
		return {'FINISHED'}


class MavhodExportExecute(bpy.types.Operator):
	"""ออเปอเรเตอร์การส่งออกหลักที่จะประมวลผลทีละ Mesh เพื่อแสดงแถบความคืบหน้า"""
	bl_idname = "mavhod_tool.export_execute"
	bl_label = "Exporting..."
	bl_options = set()

	filepath: bpy.props.StringProperty(options={'HIDDEN'})
	_timer = None
	_current_index = 0
	_objects = []
	_exported_meshes = set()
	_original_selected = []
	_original_active = None
	_export_scene_path = ""
	_path_pairs = []

	# สถานะการเลือกว่าจะส่งออก Texture ชนิดใดบ้าง
	_export_albedo = True
	_export_metallic = True
	_export_roughness = True
	_export_normal = True
	_export_emission = True
	_export_alpha = True
	_export_ao = True

	def _get_path_pair(self, src_path):
		for pair in self.path_pairs:
			if pair["source_path"] in src_path: # src_path e.g. "/d/wander/leftway2/model/buildingNurseOffice/nurseOffice.gltf"
				rel_source = get_robust_relpath(src_path, pair['source_path'])
				return {
					'source_path': pair['source_path'], # e.g. "/d/wander/leftway2/model"
					'dest_path': pair['dest_path'], # e.g. "model"
					'rel_source': get_robust_relpath(src_path, pair['source_path']), # e.g. "buildingNurseOffice/nurseOffice.gltf"
					#'target_path': os.path.normpath(pair['dest_path'] + "/" + rel_source), # e.g. "model/buildingNurseOffice/nurseOffice.gltf"
				}
		return None

	def _get_export_paths(self, obj):
		"""คำนวณหาโฟลเดอร์ต้นทาง สถานะการลิงก์ และพาธการส่งออกที่เกี่ยวข้องทั้งหมด"""
		is_linked = False
		path_pair = None
		# ตรวจสอบว่าออบเจกต์มีการลิงก์มาจากไฟล์ Library หรือไม่
		lib = obj.library or (obj.data.library if obj.data else None)
		if lib and lib.filepath: # กรณีเป็นออบเจกต์ที่ลิงก์มา (Linked Object)
			is_linked = True
			# filepath e.g. "/d/wander/leftway2/model/buildingNurseOffice/nurseOffice.gltf"
			filepath = os.path.realpath(os.path.dirname(bpy.path.abspath(lib.filepath)) + "/" + obj.name + ".gltf")
			path_pair = self._get_path_pair(filepath)
		return {
			'is_linked': is_linked,
			'path_pair': path_pair,
		}
	
	def _collect_images(self, obj):
		"""
		รวบรวมข้อมูล Metadata ของ Texture จาก Material ของออบเจกต์
		คืนค่าเป็น image_metadata: dict ที่จับคู่ Blender Image กับ Metadata
		"""
		image_metadata = {}
		#
		for slot in obj.material_slots:
			if not (slot.material and slot.material.use_nodes): continue
			nodes = slot.material.node_tree.nodes
			for node in nodes:
				if not (node.type == 'TEX_IMAGE' and node.image): continue
				img = node.image
				if img in image_metadata: continue
				# ค้นหาพาธไฟล์ต้นฉบับดั้งเดิม (Resolve original source path)
				if img.library and img.library.filepath:
					lib_dir = os.path.dirname(os.path.realpath(bpy.path.abspath(img.library.filepath)))
					src_path = os.path.realpath(bpy.path.abspath(img.filepath, start=lib_dir)) if img.filepath else None
				else:
					src_path = os.path.realpath(bpy.path.abspath(img.filepath)) if img.filepath else None
				image_metadata[img] = {
					'src_path': src_path,
					'path_pair': self._get_path_pair(src_path)
				}
		return image_metadata

	def modal(self, context, event):
		if event.type != 'TIMER': return {'PASS_THROUGH'};
		if self._current_index >= len(self._objects): return self._finish(context);
		current_index = self._current_index
		self._current_index += 1
		obj = self._objects[current_index]
		# 1. คำนวณพาธสำหรับการส่งออกและตรวจสอบสถานะการลิงก์ (Linked Data)
		paths = self._get_export_paths(obj)
		is_linked = paths['is_linked']
		'''
		parent_folder_path = paths['parent_folder_path']
		relative_asset_path = paths['relative_asset_path']
		'''
		# อัปเดตข้อความสถานะบนแถบเครื่องมือของ Blender (Header)
		status_msg = f"Exporting {'(Linked)' if is_linked else '(Local)'} {current_index + 1}/{len(self._objects)}: {obj.name}"
		context.workspace.status_text_set(status_msg)
		# อัปเดตแถบความคืบหน้า (Progress Bar)
		wm = context.window_manager
		wm.progress_update(current_index)
		# ตรวจสอบว่าโมเดลนี้ยังไม่ได้ถูกส่งออก (เพื่อเลี่ยงการส่งออกซ้ำถ้า Mesh ถูกใช้ในหลายจุด)
		if obj.data.name not in self._exported_meshes:
			# สร้างโฟลเดอร์สำหรับเก็บ Asset ถ้ายังไม่มี
			#os.makedirs(parent_folder_path, exist_ok=True)
			# กำหนด Root สำหรับเก็บ Texture (จะใช้ Asset Path ถ้ามี มิฉะนั้นจะใช้ Scene Path)
			#tex_root = self._export_asset_path if self._export_asset_path else self._export_scene_path
			# 2. รวบรวมข้อมูลรูปภาพ (Textures) ที่ใช้งานใน Material
			ordered_images = self._collect_images(obj)



		return {'PASS_THROUGH'}
		
	def invoke(self, context, event):
		# ฟังก์ชันที่จะทำงานเป็นลำดับแรกเมื่อเริ่มกระบวนการส่งออก
		props = context.scene.MavhodToolProps
		# เริ่มต้นสถานะสำหรับการประมวลผล Modal
		self._exported_meshes = set()
		self._current_index = 0
		self._mesh_data_for_json = []
		# เก็บรายการที่เลือกไว้แต่แรกเพื่อเอาไว้คืนค่าเดิมหลังงานเสร็จ
		self._original_selected = list(context.selected_objects)
		self._original_active = context.view_layer.objects.active
		# ตรวจสอบการตั้งค่าของผู้ใช้สำหรับการส่งออกหน้าแผนผังพื้นผิว (Texture Maps)
		self._export_albedo = props.export_albedo
		self._export_metallic = props.export_metallic
		self._export_roughness = props.export_roughness
		self._export_normal = props.export_normal
		self._export_emission = props.export_emission
		self._export_alpha = props.export_alpha
		self._export_ao = props.export_ao
		# ควบคุมพาธปลายทาง (Export Path Selection)
		self._export_scene_path = os.path.dirname(self.filepath)
		if not self._export_scene_path:
			self.report({'WARNING'}, "ไม่ได้กำหนดพาธสำหรับส่งออกฉาก (Export Scene Path)!")
			return {'CANCELLED'}
		#
		self.path_pairs = []
		for pair in props.path_pairs:
			if not (pair.source_path and pair.dest_path): continue
			source_path = os.path.normpath(bpy.path.abspath("//" + pair.source_path))
			if not os.path.exists(source_path): continue
			#dest_path = os.path.normpath(bpy.path.abspath(self._export_scene_path + "/" + pair.dest_path))
			dest_path = pair.dest_path
			self.path_pairs.append({"source_path": source_path, "dest_path": dest_path})
		# เรียงลำดับ self.path_pairs ตาม source_path จากหลังไปหน้า (Z-A)
		self.path_pairs.sort(key=lambda x: x["source_path"], reverse=True)
		# รวบรวมเฉพาะออบเจกต์ประเภท Mesh ที่ถูกเลือกอยู่เท่านั้น
		self._objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
		if not self._objects:
			self.report({'WARNING'}, "ไม่ได้เลือก Mesh หรือโมเดลใดๆ เลย!")
			return {'CANCELLED'}
		# เริ่มต้นแถบความคืบหน้า (Progress Bar) และตัวจับเวลา (Timer)
		wm = context.window_manager
		wm.progress_begin(0, len(self._objects))
		self._timer = wm.event_timer_add(0.01, window=context.window)
		wm.modal_handler_add(self)
		#
		return {'RUNNING_MODAL'}

	def _finish(self, context):
		"""ฟังก์ชันทำความสะอาดและสรุปงานหลังจากการประมวลผลทั้งหมดเสร็จสิ้น"""
		wm = context.window_manager
		wm.event_timer_remove(self._timer)
		wm.progress_end()
		# ยกเลิกข้อความสถานะใน Header
		context.workspace.status_text_set(None)
		# คืนค่ารายการที่เลือก (Selection) ให้เหมือนตอนเริ่มต้นก่อนการส่งออก
		bpy.ops.object.select_all(action='DESELECT')
		for obj in self._original_selected:
			obj.select_set(True)
		context.view_layer.objects.active = self._original_active

		print("_finish")
		self.report(
			{'INFO'},
			f"เสร็จสมบูรณ์! ส่งออกทั้งหมด {len(self._objects)} ชิ้น, มีโมเดล GLTF ที่ไม่ซ้ำกัน {len(self._exported_meshes)} ไฟล์"
		)
		return {'FINISHED'}

