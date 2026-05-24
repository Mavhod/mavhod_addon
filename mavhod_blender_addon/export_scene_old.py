





class MavhodExportExecute(bpy.types.Operator):

	



	# ตัวแปรภายในสำหรับเก็บข้อมูลระหว่างการส่งออก
	_mesh_data_for_json = []


	def modal(self, context, event):


		


		# ตรวจสอบว่าโมเดลนี้ยังไม่ได้ถูกส่งออก (เพื่อเลี่ยงการส่งออกซ้ำถ้า Mesh ถูกใช้ในหลายจุด)
		if root_dir and obj.data.name not in self._exported_meshes:







	def _export_and_patch_gltf(self, context, obj, parent_folder_path, full_path, image_metadata):





		try:

			
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
			


	def invoke(self, context, event):
					
		self._export_asset_path = bpy.path.abspath(props.asset_dest_path) if props.asset_dest_path else ""
		self._asset_source_path = bpy.path.abspath(props.asset_source_path) if props.asset_source_path else ""
		



		for pair in props.path_pairs:
			print(pair.source_path)
			print(pair.dest_path)
		return {'CANCELLED'}

	def _finish(self, context):

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

