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
	if not target_path or not base_path:
		return target_path
	
	# แปลงพาธให้เป็นพาธสัมบูรณ์ที่แน่นอน (Resolved Absolute Path)
	abs_target = os.path.realpath(bpy.path.abspath(target_path))
	abs_base = os.path.realpath(bpy.path.abspath(base_path))
	
	try:
		# พยายามหาพาธสัมพัทธ์
		return os.path.relpath(abs_target, abs_base)
	except (ValueError, Exception):
		# หากพาธอยู่คนละไดรฟ์ (ใน Windows) หรือเกิดข้อผิดพลาดอื่น ให้ส่งคืนพาธสัมบูรณ์เดิม
		return abs_target


class MavhodExportSettings(bpy.types.Operator, ExportHelper):
	"""เปิดหน้าต่างโต้ตอบ (Dialog) เพื่อส่งออกฉาก (Scene) ปัจจุบัน"""
	bl_idname = "mavhod_tool.export_settings"
	bl_label = "Export Scene"
	bl_options = {'REGISTER', 'UNDO'}

	# ExportHelper จะใช้ส่วนขยายไฟล์ที่กำหนดที่นี่
	filename_ext = ".json"
	filter_glob: bpy.props.StringProperty(
		default="*.json",
		options={'HIDDEN'},
		maxlen=255,
	)

	def execute(self, context):
		# เรียกใช้ออเปอเรเตอร์สำหรับการส่งออกจริง (Modal Export Operator) พร้อมพาธที่เลือก
		bpy.ops.mavhod_tool.export_execute('INVOKE_DEFAULT', filepath=self.filepath)
		return {'FINISHED'}


class MavhodExportExecute(bpy.types.Operator):
	"""ออเปอเรเตอร์การส่งออกหลักที่จะประมวลผลทีละ Mesh เพื่อแสดงแถบความคืบหน้า"""
	bl_idname = "mavhod_tool.export_execute"
	bl_label = "Exporting..."
	bl_options = set()

	filepath: bpy.props.StringProperty(options={'HIDDEN'})

	# ตัวแปรภายในสำหรับเก็บข้อมูลระหว่างการส่งออก
	_timer = None
	_objects = []
	_exported_meshes = set()
	_original_selected = []
	_original_active = None
	_current_index = 0
	_total = 0
	_export_asset_path = ""
	_export_scene_path = ""
	_asset_source_path = ""
	_mesh_data_for_json = []

	# สถานะการเลือกว่าจะส่งออก Texture ชนิดใดบ้าง
	_export_albedo = True
	_export_metallic = True
	_export_roughness = True
	_export_normal = True
	_export_emission = True
	_export_alpha = True
	_export_ao = True

	# จับคู่ชื่อ Input ของโหนด FePBR หรือ Principled BSDF กับคีย์ของสถานะการส่งออก
	INPUT_TO_FLAG = {
		'Albedo Map': '_export_albedo',
		'Base Color': '_export_albedo',
		'Metallic': '_export_metallic',
		'Roughness': '_export_roughness',
		'Normal Map': '_export_normal',
		'Normal': '_export_normal',
		'Emission': '_export_emission',
		'Emission Color': '_export_emission',
		'Alpha Map': '_export_alpha',
		'Alpha': '_export_alpha',
		'AO': '_export_ao'
	}

	def modal(self, context, event):
		# ฟังก์ชัน Modal ที่จะทำงานซ้ำๆ ตาม Timer
		if event.type == 'TIMER':
			# ตรวจสอบว่าประมวลผลครบทุกออบเจกต์หรือยัง?
			if self._current_index >= self._total:
				return self._finish(context)

			obj = self._objects[self._current_index]
			mesh_data_name = obj.data.name

			# 1. คำนวณพาธสำหรับการส่งออกและตรวจสอบสถานะการลิงก์ (Linked Data)
			paths = self._get_export_paths(obj)
			is_linked = paths['is_linked']
			parent_folder_path = paths['parent_folder_path']
			relative_asset_path = paths['relative_asset_path']
			root_dir = paths['root_dir']

			# อัปเดตข้อความสถานะบนแถบเครื่องมือของ Blender (Header)
			status_msg = f"Exporting {'(Linked)' if is_linked else '(Local)'} {self._current_index + 1}/{self._total}: {obj.name} -> {paths['dest_display']}"
			context.workspace.status_text_set(status_msg)
			
			# อัปเดตแถบความคืบหน้า (Progress Bar)
			wm = context.window_manager
			wm.progress_update(self._current_index)

			# ตรวจสอบว่าโมเดลนี้ยังไม่ได้ถูกส่งออก (เพื่อเลี่ยงการส่งออกซ้ำถ้า Mesh ถูกใช้ในหลายจุด)
			if root_dir and mesh_data_name not in self._exported_meshes:
				# สร้างโฟลเดอร์สำหรับเก็บ Asset ถ้ายังไม่มี
				os.makedirs(parent_folder_path, exist_ok=True)
				
				# กำหนด Root สำหรับเก็บ Texture (จะใช้ Asset Path ถ้ามี มิฉะนั้นจะใช้ Scene Path)
				tex_root = self._export_asset_path if self._export_asset_path else self._export_scene_path

				# 2. รวบรวมข้อมูลรูปภาพ (Textures) ที่ใช้งานใน Material
				ordered_images = self._collect_images(obj, tex_root, parent_folder_path)

				# 3. ส่งออกโมเดลเป็น GLTF และทำการปรับแก้ไฟล์ (Patching) เพื่อแก้ไขพาธของภาพและ Filter
				full_path = os.path.join(parent_folder_path, f"{mesh_data_name}.gltf")
				self._export_and_patch_gltf(context, obj, parent_folder_path, full_path, ordered_images)
				self._exported_meshes.add(mesh_data_name)

			# 4. บันทึกข้อมูล Instance ลงในรายการเพื่อเตรียมเขียนไฟล์ JSON ของ Scene รวม
			self._mesh_data_for_json.append(
				self._get_mesh_instance_data(obj, is_linked, relative_asset_path)
			)
			self._current_index += 1

		return {'PASS_THROUGH'}

	def _get_export_paths(self, obj):
		"""คำนวณหาโฟลเดอร์ต้นทาง สถานะการลิงก์ และพาธการส่งออกที่เกี่ยวข้องทั้งหมด"""
		source_folder = "local"
		is_linked = False
		# ตรวจสอบว่าออบเจกต์มีการลิงก์มาจากไฟล์ Library หรือไม่
		lib = obj.library or (obj.data.library if obj.data else None)
		
		if lib and lib.filepath:
			# กรณีเป็นออบเจกต์ที่ลิงก์มา (Linked Object)
			abs_lib_path = os.path.realpath(bpy.path.abspath(lib.filepath))
			if self._asset_source_path:
				rel_source = get_robust_relpath(os.path.dirname(abs_lib_path), self._asset_source_path)
				source_folder = "" if rel_source == "." else rel_source
			else:
				source_folder = os.path.basename(os.path.dirname(abs_lib_path))
			is_linked = True
		elif bpy.data.filepath:
			# กรณีเป็นออบเจกต์ที่อยู่ภายใต้ไฟล์ปัจจุบัน (Local Object)
			abs_blend_path = os.path.realpath(bpy.path.abspath(bpy.data.filepath))
			if self._asset_source_path:
				rel_source = get_robust_relpath(os.path.dirname(abs_blend_path), self._asset_source_path)
				source_folder = "" if rel_source == "." else rel_source
			else:
				source_folder = os.path.basename(os.path.dirname(abs_blend_path))

		# ตัดสินใจเลือกไดเรกทอรีรูท (Root Directory)
		root_dir = self._export_asset_path if is_linked else self._export_scene_path
		if not root_dir:
			root_dir = self._export_scene_path if self._export_scene_path else self._export_asset_path

		# สร้างพาธต่างๆ
		if is_linked:
			parent_folder_path = os.path.join(root_dir, source_folder)
			relative_asset_path = os.path.join(source_folder, f"{obj.data.name}.gltf")
			dest_display = f"{source_folder}/"
		else:
			parent_folder_path = root_dir
			relative_asset_path = f"{obj.data.name}.gltf"
			dest_display = "scene (root)/"

		return {
			'is_linked': is_linked,
			'root_dir': root_dir,
			'parent_folder_path': parent_folder_path,
			'relative_asset_path': relative_asset_path,
			'dest_display': dest_display
		}

	def _collect_images(self, obj, tex_root, parent_folder_path):
		"""
		รวบรวมข้อมูล Metadata ของ Texture จาก Material ของออบเจกต์
		คืนค่าเป็น image_metadata: dict ที่จับคู่ Blender Image กับ Metadata
		"""
		image_metadata = {} # img -> {should_export, abs_dst, rel_uri, src_path}

		for slot in obj.material_slots:
			if not (slot.material and slot.material.use_nodes):
				continue

			nodes = slot.material.node_tree.nodes
			for node in nodes:
				if not (node.type == 'TEX_IMAGE' and node.image):
					continue
				
				img = node.image
				if img in image_metadata:
					continue

				# ค้นหาพาธไฟล์ต้นฉบับดั้งเดิม (Resolve original source path)
				if img.library and img.library.filepath:
					lib_dir = os.path.dirname(os.path.realpath(bpy.path.abspath(img.library.filepath)))
					src_path = os.path.realpath(bpy.path.abspath(img.filepath, start=lib_dir)) if img.filepath else None
				else:
					src_path = os.path.realpath(bpy.path.abspath(img.filepath)) if img.filepath else None

				# เตรียมข้อมูลปลายทางสำหรับการบันทึก
				abs_dst = None
				rel_uri = None
				if src_path and os.path.isfile(src_path):
					if self._asset_source_path:
						rel_source = get_robust_relpath(os.path.dirname(src_path), self._asset_source_path)
						img_source_folder = "" if rel_source == "." else rel_source
					else:
						img_source_folder = os.path.basename(os.path.dirname(src_path))

					img_filename = os.path.basename(src_path)
					target_tex_dir = os.path.join(tex_root, img_source_folder)
					# สร้างโฟลเดอร์สำหรับเก็บ Texture ถ้ายังไม่มี
					os.makedirs(target_tex_dir, exist_ok=True)
					abs_dst = os.path.join(target_tex_dir, img_filename)
					# คำนวณหาพาธสัมพัทธ์เพื่อใส่ลงในไฟล์ GLTF เพื่อให้ชี้ไปยังไฟล์ภาพที่ถูกต้อง
					rel_uri = get_robust_relpath(abs_dst, parent_folder_path)

				image_metadata[img] = {
					'src_path': src_path,
					'abs_dst': abs_dst,
					'rel_uri': rel_uri
				}

		return image_metadata

	def _export_and_patch_gltf(self, context, obj, parent_folder_path, full_path, image_metadata):
		"""
		ส่งออก GLTF และทำการปรับแก้ไฟล์ (Patching) โดยการแกะรอยตามโครงสร้างโหนด (Socket -> GLTF)
		เพื่อให้แน่ใจว่าการอ้างอิงชื่อและ Filter ถูกต้อง 100%
		"""
		# แยกออบเจกต์ออกมา (Isolate Object)
		bpy.ops.object.select_all(action='DESELECT')
		obj.select_set(True)
		context.view_layer.objects.active = obj

		# 1. ขั้นตอนการส่งออกตามปกติของ Blender
		bpy.ops.export_scene.gltf(
			filepath=full_path,
			use_selection=True,
			export_format='GLTF_SEPARATE',
			export_image_format='AUTO',
			export_apply=True
		)

		if not os.path.isfile(full_path):
			return

		try:
			with open(full_path, 'r', encoding='utf-8') as gf:
				gltf_data = json.load(gf)

			gltf_images = gltf_data.get('images', [])
			gltf_textures = gltf_data.get('textures', [])
			gltf_materials = gltf_data.get('materials', [])

			# --- ขั้นตอน A: ทำการแผนผังความสัมพันธ์ (Map) ระหว่าง Blender Material Socket กับดรรชนี (Indices) ใน GLTF ---
			indices_to_remove = set()
			gltf_img_idx_to_blender_img = {} # i_idx -> Blender Image object (สำหรับใช้อ้างอิงภาพใน Blender)
			
			for m_idx, slot in enumerate(obj.material_slots):
				if m_idx >= len(gltf_materials): break
				if not (slot.material and slot.material.use_nodes): continue
				
				g_mat = gltf_materials[m_idx]
				nodes = slot.material.node_tree.nodes
				
				# แกะรอย Sockets เพื่อหาว่าถูกเชื่อมต่อกับภาพใดใน Blender
				socket_to_image = {} # socket_name -> Image object
				target_nodes = [n for n in nodes if n.type in {'GROUP', 'BSDF_PRINCIPLED'}]
				
				for target in target_nodes:
					for sock in target.inputs:
						if not sock.is_linked: continue
						
						from_node = sock.links[0].from_node
						# กรณีเป็นโหนด Normal Map ต้องขยับไปหาโหนด Image Texture ที่เชื่อมต่ออยู่
						if from_node.type == 'NORMAL_MAP' and sock.name in {'Normal', 'Normal Map'}:
							if from_node.inputs['Color'].is_linked:
								from_node = from_node.inputs['Color'].links[0].from_node
						
						if from_node.type == 'TEX_IMAGE' and from_node.image:
							socket_to_image[sock.name] = from_node.image

				# กำหนดการจับคู่ระหว่าง Attribute ใน GLTF กับชื่อ Socket ใน Blender
				# (Exporter ของ Blender มีเกณฑ์การจับคู่เฉพาะตัว)
				attr_map = {
					('pbrMetallicRoughness', 'baseColorTexture'): ['Base Color', 'Albedo Map'],
					('pbrMetallicRoughness', 'metallicRoughnessTexture'): ['Metallic', 'Roughness'], # กรณีใช้แผนผัง ORM
					('normalTexture',): ['Normal', 'Normal Map'],
					('occlusionTexture',): ['AO'],
					('emissiveTexture',): ['Emission', 'Emission Color']
				}

				for gltf_path, socket_names in attr_map.items():
					# เข้าถึงส่วนอ้างอิง Texture ใน GLTF
					tex_ref = g_mat
					for p in gltf_path:
						if isinstance(tex_ref, dict): tex_ref = tex_ref.get(p)
					
					if not tex_ref or not isinstance(tex_ref, dict): continue
					t_idx = tex_ref.get('index')
					if t_idx is None or t_idx >= len(gltf_textures): continue
					i_idx = gltf_textures[t_idx].get('source')
					if i_idx is None: continue

					# บันทึกการจับคู่ไว้เพื่อใช้แก้ URI ในภายหลัง
					for sname in socket_names:
						if sname in socket_to_image:
							gltf_img_idx_to_blender_img[i_idx] = socket_to_image[sname]
							break

					# ตรวจสอบว่าภาพที่เชื่อมต่ออยู่นั้น ผู้ใช้เลือกที่จะส่งออกหรือไม่ (ตามตัวเลือกใน UI)
					should_export = True
					for sname in socket_names:
						flag = self.INPUT_TO_FLAG.get(sname)
						if flag and not getattr(self, flag):
							# ถ้าผู้ใช้ไม่ได้เลือกช่องนี้ (Unchecked) จะไม่ส่งออกภาพนี้
							should_export = False
							break
					
					if not should_export:
						# ลบ Attribute ออกจากข้อมูล Material ใน GLTF
						parent = g_mat
						for p in gltf_path[:-1]: parent = parent.get(p)
						if isinstance(parent, dict): del parent[gltf_path[-1]]
						indices_to_remove.add(i_idx)

			# --- ขั้นตอน B: ปรับแก้ URI และล้างข้อมูลที่ไม่จำเป็นอย่างปลอดภัย ---
			# เราจะวนซ้ำภาพทั้งหมดที่มีอยู่ในไฟล์ GLTF เพื่อตรวจสอบว่าจะสามารถเปลี่ยนไปใช้ไฟล์ต้นฉบับได้หรือไม่
			used_img_indices = set()
			# ค้นหากลับว่าหลังจากลบบางตัวออกไปแล้ว ยังมีภาพใดบ้างที่ถูกใช้งานจริงอยู่
			for g_mat in gltf_materials:
				# ค้นหาคีย์ 'index' ที่ชี้ไปยัง Texture แบบ Recursive
				def find_used(data):
					if isinstance(data, dict):
						if 'index' in data and len(data) == 1: # มักจะเป็นโครงสร้างการอ้างอิง texture
							t_idx = data['index']
							if t_idx < len(gltf_textures):
								src = gltf_textures[t_idx].get('source')
								if src is not None: used_img_indices.add(src)
						for v in data.values(): find_used(v)
					elif isinstance(data, list):
						for item in data: find_used(item)
				find_used(g_mat)

			# สร้างรายการภาพ (Image List) ชุดใหม่สำหรับ GLTF
			new_img_list = []
			old_to_new_img = {}
			
			for i, gimg in enumerate(gltf_images):
				temp_uri = gimg.get('uri', '')
				temp_path = os.path.join(parent_folder_path, temp_uri) if temp_uri else None
				
				if i not in used_img_indices:
					# หากภาพนี้ไม่ได้ใช้งานแล้ว (ถูกลบออกจากการ Patch ก่อนหน้า) ให้ลบไฟล์ที่ส่งออกมาโดย Blender ทิ้ง
					if temp_path and os.path.isfile(temp_path): os.remove(temp_path)
					continue

				# เปลี่ยนพาธ (URI Re-mapping) ไปหาไฟล์ต้นฉบับดั้งเดิมโดยใช้ความสัมพันธ์ที่แกะรอยไว้ได้ก่อนหน้า
				blender_img = gltf_img_idx_to_blender_img.get(i)
				matched_meta = image_metadata.get(blender_img) if blender_img else None
				
				old_to_new_img[i] = len(new_img_list)
				if matched_meta and matched_meta['abs_dst']:
					# คัดลอกไฟล์ต้นฉบับที่ต้องการไปวางไว้และเปลี่ยนพาธใน GLTF
					try:
						if matched_meta['src_path'] and os.path.isfile(matched_meta['src_path']):
							if not os.path.exists(matched_meta['abs_dst']):
								shutil.copy2(matched_meta['src_path'], matched_meta['abs_dst'])
							gimg['uri'] = matched_meta['rel_uri'].replace("\\", "/")
							# ลบไฟล์ชั่วคราวที่ Blender สร้างขึ้นทิ้งไป
							if temp_path and os.path.isfile(temp_path): os.remove(temp_path)
					except Exception:
						pass # หากคัดลอกไฟล์ไม่สำเร็จ ให้เก็บไฟล์เดิมที่ส่งออกมาจาก Blender ไว้
				
				new_img_list.append(gimg)

			# ทำดรรชนีของ Texture ใหม่ (Re-index Textures)
			new_tex_list = []
			old_to_new_tex = {}
			for i, gtex in enumerate(gltf_textures):
				src = gtex.get('source')
				if src is not None and src in old_to_new_img:
					old_to_new_tex[i] = len(new_tex_list)
					gtex['source'] = old_to_new_img[src]
					new_tex_list.append(gtex)

			# อัปเดตดรรชนีอ้างอิงใน Material ใหม่เพื่อให้ชี้ไปยังรายการชุดใหม่ได้ถูกต้อง
			def update_indices(data):
				if isinstance(data, dict):
					if 'index' in data and len(data) == 1:
						if data['index'] in old_to_new_tex:
							data['index'] = old_to_new_tex[data['index']]
					for v in data.values(): update_indices(v)
				elif isinstance(data, list):
					for item in data: update_indices(item)
			update_indices(gltf_materials)

			# บันทึกไฟล์ที่ปรับแก้แล้วลงทับที่เดิม
			gltf_data['images'] = new_img_list
			gltf_data['textures'] = new_tex_list
			
			with open(full_path, 'w', encoding='utf-8') as gf:
				json.dump(gltf_data, gf, indent=4)
				
		except Exception as e:
			self.report({'WARNING'}, f"Could not patch GLTF textures: {str(e)}")

	def _get_mesh_instance_data(self, obj, is_linked, relative_asset_path):
		"""เตรียมข้อมูลของ Instance สำหรับการเขียนลงในไฟล์ JSON ผลลัพธ์สุดท้าย"""
		local_matrix = obj.matrix_local
		loc, rot_quat, scale = local_matrix.decompose()
		return {
			"name": obj.name,
			"mesh_data": obj.data.name,
			"is_linked": is_linked,
			"asset_path": relative_asset_path,
			"location": {"x": loc.x, "y": loc.y, "z": loc.z},
			"rotation": {"x": rot_quat.x, "y": rot_quat.y, "z": rot_quat.z, "w": rot_quat.w},
			"scale": {"x": scale.x, "y": scale.y, "z": scale.z}
		}

	def invoke(self, context, event):
		# ฟังก์ชันที่จะทำงานเป็นลำดับแรกเมื่อเริ่มกระบวนการส่งออก
		props = context.scene.MavhodToolProps
		
		# ควบคุมพาธปลายทาง (Export Path Selection)
		if self.filepath:
			self._export_scene_path = os.path.dirname(self.filepath)
		else:
			self._export_scene_path = bpy.path.abspath(props.scene_dest_path)
			
		self._export_asset_path = bpy.path.abspath(props.asset_dest_path) if props.asset_dest_path else ""
		self._asset_source_path = bpy.path.abspath(props.asset_source_path) if props.asset_source_path else ""
		
		# ตรวจสอบการตั้งค่าของผู้ใช้สำหรับการส่งออกหน้าแผนผังพื้นผิว (Texture Maps)
		self._export_albedo = props.export_albedo
		self._export_metallic = props.export_metallic
		self._export_roughness = props.export_roughness
		self._export_normal = props.export_normal
		self._export_emission = props.export_emission
		self._export_alpha = props.export_alpha
		self._export_ao = props.export_ao

		if not self._export_scene_path:
			self.report({'WARNING'}, "ไม่ได้กำหนดพาธสำหรับส่งออกฉาก (Export Scene Path)!")
			return {'CANCELLED'}

		print(self._export_scene_path)
		for pair in props.path_pairs:
			print(pair.source_path)
			print(pair.dest_path)
		return {'CANCELLED'}

		# เตรียมโฟลเดอร์สำหรับส่งออกไฟล์ JSON และไฟล์โมเดล GLTF
		os.makedirs(self._export_scene_path, exist_ok=True)
		if self._export_asset_path:
			os.makedirs(self._export_asset_path, exist_ok=True)

		# รวบรวมเฉพาะออบเจกต์ประเภท Mesh ที่ถูกเลือกอยู่เท่านั้น
		self._objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
		if not self._objects:
			self.report({'WARNING'}, "ไม่ได้เลือก Mesh หรือโมเดลใดๆ เลย!")
			return {'CANCELLED'}

		# เริ่มต้นสถานะสำหรับการประมวลผล Modal
		self._exported_meshes = set()
		self._current_index = 0
		self._total = len(self._objects)
		self._mesh_data_for_json = []
		# เก็บรายการที่เลือกไว้แต่แรกเพื่อเอาไว้คืนค่าเดิมหลังงานเสร็จ
		self._original_selected = list(context.selected_objects)
		self._original_active = context.view_layer.objects.active

		# เริ่มต้นแถบความคืบหน้า (Progress Bar) และตัวจับเวลา (Timer)
		wm = context.window_manager
		wm.progress_begin(0, self._total)
		self._timer = wm.event_timer_add(0.01, window=context.window)
		wm.modal_handler_add(self)
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
		if self.filepath:
			json_path = self.filepath
		else:
			json_path = os.path.join(self._export_scene_path, "scene_export.json")
			
		try:
			with open(json_path, 'w', encoding='utf-8') as f:
				json.dump({"instances": self._mesh_data_for_json}, f, indent=4)
		except Exception as e:
			self.report({'ERROR'}, f"ไม่สามารถบันทึกไฟล์ JSON ได้: {str(e)}")
			return {'CANCELLED'}

		self.report(
			{'INFO'},
			f"เสร็จสมบูรณ์! ส่งออกทั้งหมด {self._total} ชิ้น, มีโมเดล GLTF ที่ไม่ซ้ำกัน {len(self._exported_meshes)} ไฟล์"
		)
		return {'FINISHED'}
