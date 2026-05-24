import bpy
import json
import os
import shutil
import hashlib
import subprocess
from .export_utils import copy_and_hash_images, rebind_materials_to_hashed_images
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
	_path_pairs = []
	
	# src_path e.g. '/d/wander/leftway2/model/buildingNurseOffice/nurseOffice.gltf'
	# dst_path e.g. '/d/wander/leftway2/level/New Folder/model/buildingNurseOffice/nurseOffice.gltf',
	def _get_dst_path(self, src_path):
		for pair in self.path_pairs:
			if pair['source_path'] in src_path:
				rel_source = get_robust_relpath(src_path, pair['source_path'])
				dest_path = pair['dest_path']
				# Resolve Blender-relative paths or ensure absolute paths are clean
				if dest_path.startswith("//") or dest_path.startswith("/"):
					dest_path = bpy.path.abspath(dest_path)
				return os.path.realpath(os.path.join(self._export_scene_path, dest_path, rel_source))
		return None

	def _get_export_path(self, obj):
		"""คำนวณหาโฟลเดอร์ต้นทาง สถานะการลิงก์ และพาธการส่งออกที่เกี่ยวข้องทั้งหมด"""
		is_linked = False
		# ตรวจสอบว่าออบเจกต์มีการลิงก์มาจากไฟล์ Library หรือไม่
		lib = obj.library or (obj.data.library if obj.data else None)
		if lib and lib.filepath: # กรณีเป็นออบเจกต์ที่ลิงก์มา (Linked Object)
			is_linked = True
			# filepath e.g. "/d/wander/leftway2/model/buildingNurseOffice/nurseOffice.gltf"
			blend_filepath = os.path.realpath(bpy.path.abspath(lib.filepath))
			filepath = os.path.dirname(blend_filepath) + "/" + obj.data.name + ".gltf"
			dst_path = self._get_dst_path(filepath)
		else:
			blend_filepath = os.path.realpath(bpy.data.filepath)
			dst_path = f"{self._export_scene_path}/{self._blend_filename}/{obj.data.name}.gltf"
		#	
		return {
			'is_linked': is_linked,
			'blend_filepath': blend_filepath, # e.g. "/d/wander/leftway2/model/buildingNurseOffice/buildingNurseOffice.blend"
			'dst_path': dst_path
		}

	def _collect_images(self, obj):
		"""
		รวบรวมข้อมูล Metadata ของ Texture จาก Material ของออบเจกต์
		คืนค่าเป็น image_metadata: dict ที่จับคู่ hash sha256 กับ Metadata
		"""
		image_metadata = {} # hash sha256 -> {src_path, dst_path}
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
				# สร้าง SHA256 Hash
				hash_obj = hashlib.sha256(src_path.encode('utf-8'))
				hash_name = hash_obj.hexdigest()
				#
				image_metadata[hash_name] = {
					'src_path': src_path,
					'dst_path': self._get_dst_path(src_path),
				}
		return image_metadata

	def _export_and_patch_gltf(self, context, obj, path_info, image_metadata):
		"""
		ส่งออก GLTF และทำการปรับแก้ไฟล์ (Patching) โดยการแกะรอยตามโครงสร้างโหนด (Socket -> GLTF)
		เพื่อให้แน่ใจว่าการอ้างอิงชื่อและ Filter ถูกต้อง 100%
		"""
		dst_path = path_info['dst_path']
		# Ensure destination directory exists
		dst_dir = os.path.dirname(path_info['dst_path'])
		os.makedirs(dst_dir, exist_ok=True)
		
		if path_info['is_linked']:
			# Use subprocess to export linked mesh data
			blender_bin = bpy.app.binary_path
			# export_bg.py is expected to be in the same directory as this script
			script_path = os.path.join(os.path.dirname(__file__), "export_bg.py")
			blend_file = path_info['blend_filepath']
			mesh_name = obj.data.name
			
			cmd = [
				blender_bin,
				"--factory-startup",
				"-b", blend_file,
				"-P", script_path,
				"--",
				"--output", dst_path,
				"--mesh", mesh_name
			]
			
			print(f"Running subprocess: {' '.join(cmd)}")
			try:
				subprocess.run(cmd, check=True)
			except subprocess.CalledProcessError as e:
				self.report({'ERROR'}, f"Subprocess failed for {obj.name}")
				return
		else:
			# Local object export
			# แยกออบเจกต์ออกมา (Isolate Object)
			bpy.ops.object.select_all(action='DESELECT')
			obj.select_set(True)
			context.view_layer.objects.active = obj
			
			# 1. ทำการ Copy และ Hash Image + Re-bind Material สำหรับ Local Object
			output_dir = os.path.dirname(dst_path)
			image_mapping = copy_and_hash_images(output_dir)
			
			# เก็บรายชื่อ Material เดิมไว้เพื่อคืนค่าหลัง Export เสร็จ
			original_materials = list(obj.data.materials)
			
			try:
				rebind_materials_to_hashed_images(image_mapping)
				
				bpy.ops.export_scene.gltf(
					filepath=dst_path,
					use_selection=True,
					export_format='GLTF_SEPARATE',
					export_image_format='AUTO',
					export_apply=True
				)
			finally:
				# คืนค่า Material เดิมให้กับ Object
				for i, mat in enumerate(original_materials):
					obj.data.materials[i] = mat
		#
		if not os.path.isfile(dst_path): return
		# 2. อ่านไฟล์ GLTF และทำการแก้ไข (Patching)
		try:
			with open(dst_path, 'r', encoding='utf-8') as gf:
				gltf_data = json.load(gf)
			
			gltf_dir = os.path.dirname(dst_path)
			modified = False
			
			if 'images' in gltf_data:
				for img in gltf_data['images']:
					uri = img.get('uri')
					if not uri: continue
					# uri มักจะเป็นชื่อไฟล์ hash.ext ถ้าส่งออกด้วย GLTF_SEPARATE
					file_basename = os.path.basename(uri)
					hash_name, ext = os.path.splitext(file_basename)
					
					if hash_name in image_metadata:
						meta = image_metadata[hash_name]
						final_image_dst = meta.get('dst_path')
						
						if final_image_dst:
							# พาธปัจจุบันของไฟล์ภาพที่ถูก Hash ไว้
							current_image_path = os.path.join(gltf_dir, uri)
							#
							if os.path.exists(current_image_path):
								# สร้างโฟลเดอร์ปลายทางสำหรับภาพ
								os.makedirs(os.path.dirname(final_image_dst), exist_ok=True)
								# ย้ายไฟล์ภาพไปยังตำแหน่งสุดท้ายตาม image_metadata
								shutil.move(current_image_path, final_image_dst)	
								# คำนวณหาพาธสัมพัทธ์จากไฟล์ GLTF ไปยังพาธภาพใหม่
								rel_uri = get_robust_relpath(final_image_dst, gltf_dir)
								# GLTF ใช้ forward slashes เสมอ
								img['uri'] = rel_uri.replace("\\", "/")
								img['name'] = os.path.splitext(os.path.basename(final_image_dst))[0]
								modified = True
								print(f"Patched image uri: {uri} -> {img['uri']} and moved to {final_image_dst}")

			if modified:
				with open(dst_path, 'w', encoding='utf-8') as gf:
					json.dump(gltf_data, gf, indent=4)
		except Exception as e:
			self.report({'WARNING'}, f"Could not patch GLTF textures: {str(e)}")




	def _get_mesh_instance_data(self, obj, path_info):
		"""เตรียมข้อมูลของ Instance สำหรับการเขียนลงในไฟล์ JSON ผลลัพธ์สุดท้าย"""
		local_matrix = obj.matrix_local
		loc, rot_quat, scale = local_matrix.decompose()
		return {
			"name": obj.name,
			"asset_path": get_robust_relpath(path_info['dst_path'], self._export_scene_path),
			"location": {"x": loc.x, "y": loc.y, "z": loc.z},
			"rotation": {"x": rot_quat.x, "y": rot_quat.y, "z": rot_quat.z, "w": rot_quat.w},
			"scale": {"x": scale.x, "y": scale.y, "z": scale.z}
		}

	def modal(self, context, event):
		if event.type != 'TIMER': return {'PASS_THROUGH'};
		if self._current_index >= len(self._objects): return self._finish(context);
		current_index = self._current_index
		self._current_index += 1
		obj = self._objects[current_index]
		# 1. คำนวณพาธสำหรับการส่งออกและตรวจสอบสถานะการลิงก์ (Linked Data)
		path_info = self._get_export_path(obj)
		if path_info['dst_path'] == None: return {'PASS_THROUGH'};
		is_linked = path_info['is_linked']
		# อัปเดตข้อความสถานะบนแถบเครื่องมือของ Blender (Header)
		status_msg = f"Exporting {'(Linked)' if is_linked else '(Local)'} {current_index + 1}/{len(self._objects)}: {obj.name}"
		context.workspace.status_text_set(status_msg)
		# อัปเดตแถบความคืบหน้า (Progress Bar)
		wm = context.window_manager
		wm.progress_update(current_index)
		# ตรวจสอบว่าโมเดลนี้ยังไม่ได้ถูกส่งออก (เพื่อเลี่ยงการส่งออกซ้ำถ้า Mesh ถูกใช้ในหลายจุด)
		export_key = f"{path_info['blend_filepath']}|{obj.data.name}" # e.g. "/d/wander/leftway2/level/theme1.blend:Cube.049"
		if export_key not in self._exported_meshes:
			# 2. รวบรวมข้อมูลรูปภาพ (Textures) ที่ใช้งานใน Material
			image_metadata = self._collect_images(obj)
			# 3. ส่งออกโมเดลเป็น GLTF และทำการปรับแก้ไฟล์ (Patching) เพื่อแก้ไขพาธของภาพและ Filter
			self._export_and_patch_gltf(context, obj, path_info, image_metadata)
			self._exported_meshes.add(export_key)
			# 4. บันทึกข้อมูล Instance ลงในรายการเพื่อเตรียมเขียนไฟล์ JSON ของ Scene รวม
			self._mesh_data_for_json.append(self._get_mesh_instance_data(obj, path_info))

		#print(path_info)
		#print(image_metadata)
		#print(export_key)
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
		#
		if not self.filepath:
			self.report({'WARNING'}, "ไม่ได้กำหนด filepath สำหรับส่งออกฉาก!")
			return {'CANCELLED'}
		#
		self._export_scene_path = os.path.realpath(os.path.dirname(self.filepath)) # e.g. "/d/wander/leftway2/level/New Folder"
		self._blend_filename = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
		#
		self.path_pairs = []
		for pair in props.path_pairs:
			if not (pair.source_path and pair.dest_path): continue
			source_path = os.path.normpath(bpy.path.abspath("//" + pair.source_path))
			if not os.path.exists(source_path): continue
			#dest_path = os.path.normpath(bpy.path.abspath(self._export_scene_path + "/" + pair.dest_path))
			dest_path = pair.dest_path
			self.path_pairs.append({'source_path': source_path, 'dest_path': dest_path})
		# เรียงลำดับ self.path_pairs ตาม source_path จากหลังไปหน้า (Z-A)
		self.path_pairs.sort(key=lambda x: x['source_path'], reverse=True)
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
		# บันทึกข้อมูล Scene รวมทั้งหมดลงไฟล์ JSON
		try:
			# สร้างโฟลเดอร์สำหรับ Save ถ้ายังไม่มี
			os.makedirs(self._export_scene_path, exist_ok=True)
			with open(self.filepath, 'w', encoding='utf-8') as f:
				json.dump({"instances": self._mesh_data_for_json}, f, indent=4)
		except Exception as e:
			self.report({'ERROR'}, f"ไม่สามารถบันทึกไฟล์ JSON ได้: {str(e)}")
			return {'CANCELLED'}

		print("_finish")
		self.report(
			{'INFO'},
			f"เสร็จสมบูรณ์! ส่งออกทั้งหมด {len(self._objects)} ชิ้น, มีโมเดล GLTF ที่ไม่ซ้ำกัน {len(self._exported_meshes)} ไฟล์"
		)
		return {'FINISHED'}
