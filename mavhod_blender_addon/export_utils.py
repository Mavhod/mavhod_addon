import bpy
import os
import shutil
import hashlib

def get_images_from_materials():
    """ค้นหา Image ทั้งหมดที่ถูกใช้ใน Material ของ Object ที่กำลังถูกเลือก"""
    images = set()
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            for slot in obj.material_slots:
                mat = slot.material
                if mat and mat.use_nodes:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            images.add(node.image)
    return images

def copy_and_hash_images(output_dir):
    """
    Copy image ไปที่ output_dir และเปลี่ยนชื่อเป็น hash ของ real path
    คืนค่าเป็น Mapping { image_name: hashed_full_path }
    """
    os.makedirs(output_dir, exist_ok=True)
    images = get_images_from_materials()
    image_mapping = {}
    
    for img in images:
        if img.source != 'FILE':
            continue
            
        # หา Path จริงของไฟล์
        abs_path = bpy.path.abspath(img.filepath)
        real_path = os.path.realpath(abs_path)
        
        if not os.path.isfile(real_path):
            print(f"Warning: Image file not found: {real_path}")
            continue
            
        # สร้าง SHA256 Hash จากค่า real path
        hash_obj = hashlib.sha256(real_path.encode('utf-8'))
        hash_name = hash_obj.hexdigest()
        
        # แยกนามสกุลไฟล์
        ext = os.path.splitext(real_path)[1]
        new_filename = hash_name + ext
        dst_path = os.path.join(output_dir, new_filename)
        
        # ทำการ Copy ไฟล์
        try:
            shutil.copy2(real_path, dst_path)
            print(f"Copied image: {real_path} -> {dst_path}")
            image_mapping[img.name] = dst_path
        except Exception as e:
            print(f"Error copying image {real_path}: {str(e)}")
            
    return image_mapping

def rebind_materials_to_hashed_images(image_mapping):
    """
    Duplicate material และแก้ให้ใช้ Image ใหม่ตาม image_mapping
    """
    material_cache = {} # Mapping { original_material_name: new_material }
    
    # รวบรวมออบเจกต์ที่ถูกเลือก
    for obj in bpy.context.selected_objects:
        if obj.type != 'MESH' or not obj.data:
            continue
        
        mesh = obj.data
        for i in range(len(mesh.materials)):
            mat = mesh.materials[i]
            if not mat:
                continue
                
            if mat.name not in material_cache:
                # Duplicate material
                new_mat = mat.copy()
                new_mat.name = f"{mat.name}_hashed"
                material_cache[mat.name] = new_mat
                
                # สแกนหา Image nodes และเปลี่ยน image
                if new_mat.use_nodes:
                    for node in new_mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            img_name = node.image.name
                            if img_name in image_mapping:
                                hashed_filepath = image_mapping[img_name]
                                # Load image ใหม่เข้า Blender (ถ้ามีอยู่แล้วจะใช้ตัวเดิม)
                                new_img = bpy.data.images.load(hashed_filepath, check_existing=True)
                                node.image = new_img
                                print(f"Material '{new_mat.name}': Swapped image '{img_name}' -> '{new_img.name}'")
            
            # แทนที่ material เดิมด้วยตัวใหม่ที่แก้แล้ว
            mesh.materials[i] = material_cache[mat.name]
