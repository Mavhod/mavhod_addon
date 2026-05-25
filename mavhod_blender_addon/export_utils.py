import bpy
import os
import shutil
import hashlib

def get_images_from_materials():
    """Find all images used in materials of currently selected objects."""
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
    Copy images to output_dir and rename them to the hash of their real path.
    Returns Mapping: { image_name: hashed_full_path }.
    """
    os.makedirs(output_dir, exist_ok=True)
    images = get_images_from_materials()
    image_mapping = {}
    
    for img in images:
        if img.source != 'FILE':
            continue
            
        # Get real file path
        abs_path = bpy.path.abspath(img.filepath)
        real_path = os.path.realpath(abs_path)
        
        if not os.path.isfile(real_path):
            print(f"Warning: Image file not found: {real_path}")
            continue
            
        # Create SHA256 Hash from real path
        hash_obj = hashlib.sha256(real_path.encode('utf-8'))
        hash_name = hash_obj.hexdigest()
        
        # Get file extension
        ext = os.path.splitext(real_path)[1]
        new_filename = hash_name + ext
        dst_path = os.path.join(output_dir, new_filename)
        
        # Copy file
        try:
            shutil.copy2(real_path, dst_path)
            print(f"Copied image: {real_path} -> {dst_path}")
            image_mapping[img.name] = dst_path
        except Exception as e:
            print(f"Error copying image {real_path}: {str(e)}")
            
    return image_mapping

def rebind_materials_to_hashed_images(image_mapping):
    """
    Duplicate materials and update them to use new images according to image_mapping.
    Returns a mapping of { actual_blender_name: original_name } so the caller can
    restore original names in the exported GLTF (Blender may append .001, .002, etc.).
    """
    material_cache = {} # Mapping: { original_material_name: new_material }
    
    # Process selected objects
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
                
                # Scan for Image nodes and swap images
                if new_mat.use_nodes:
                    for node in new_mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            img_name = node.image.name
                            if img_name in image_mapping:
                                hashed_filepath = image_mapping[img_name]
                                # Load new image into Blender (reuse if existing)
                                new_img = bpy.data.images.load(hashed_filepath, check_existing=True)
                                node.image = new_img
                                print(f"Material '{new_mat.name}': Swapped image '{img_name}' -> '{new_img.name}'")
            
            # Replace original material with the hashed version
            mesh.materials[i] = material_cache[mat.name]

    # Return mapping: { actual_blender_assigned_name -> original_name }
    # new_mat.name may differ from f"{original}_hashed" if Blender appended .001, .002, etc.
    return {new_mat.name: original_name for original_name, new_mat in material_cache.items()}
