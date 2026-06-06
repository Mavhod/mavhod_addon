import bpy
import os
import shutil
import hashlib
import json
import re

def get_robust_relpath(target_path, base_path):
    """
    Calculate relative path from base_path to target_path.
    Ensures both paths are absolute and resolves symlinks before calculation.
    """
    if not target_path or not base_path: return target_path
    abs_target = os.path.realpath(bpy.path.abspath(target_path))
    abs_base = os.path.realpath(bpy.path.abspath(base_path))
    try:
        return os.path.relpath(abs_target, abs_base)
    except (ValueError, Exception):
        return abs_target

def patch_gltf_output(dst_path, metadata_settings, image_metadata=None, object_ext=".gltf"):
    """
    Post-process GLTF output:
    1. Strip node transformations (identity).
    2. Patch image URIs using image_metadata.
    3. Remove hashed suffixes from material names.
    4. Filter metadata (extras) from nodes, meshes, materials, and scenes.
    5. Handle file extension renaming.
    """
    if not os.path.isfile(dst_path):
        return

    try:
        with open(dst_path, 'r', encoding='utf-8') as f:
            gltf_data = json.load(f)

        gltf_dir = os.path.dirname(dst_path)
        modified = False

        # 1. Strip Node transformations
        if 'nodes' in gltf_data:
            for node in gltf_data['nodes']:
                for key in ['translation', 'rotation', 'scale', 'matrix']:
                    if key in node:
                        del node[key]
                        modified = True
                # Filter Node Metadata
                if not metadata_settings.get('node', True) and 'extras' in node:
                    del node['extras']
                    modified = True

        # 2. Patch image URIs
        if image_metadata and 'images' in gltf_data:
            for img in gltf_data['images']:
                uri = img.get('uri')
                if not uri: continue
                file_basename = os.path.basename(uri)
                hash_name, ext = os.path.splitext(file_basename)
                
                if hash_name in image_metadata:
                    meta = image_metadata[hash_name]
                    final_image_dst = meta.get('dst_path')
                    if final_image_dst:
                        current_image_path = os.path.join(gltf_dir, uri)
                        if os.path.exists(current_image_path):
                            os.makedirs(os.path.dirname(final_image_dst), exist_ok=True)
                            shutil.move(current_image_path, final_image_dst)
                            rel_uri = get_robust_relpath(final_image_dst, gltf_dir)
                            img['uri'] = rel_uri.replace("\\", "/")
                            img['name'] = os.path.splitext(os.path.basename(final_image_dst))[0]
                            modified = True

        # 3. Clean Material Names and Filter Material Metadata
        if 'materials' in gltf_data:
            for mat in gltf_data['materials']:
                if not metadata_settings.get('material', True) and 'extras' in mat:
                    del mat['extras']
                    modified = True
                name = mat.get('name', '')
                clean = re.sub(r'_hashed(\.\d+)?$', '', name)
                if clean != name:
                    mat['name'] = clean
                    modified = True

        # 4. Filter Mesh Metadata
        if not metadata_settings.get('mesh', True) and 'meshes' in gltf_data:
            for mesh in gltf_data['meshes']:
                if 'extras' in mesh:
                    del mesh['extras']
                    modified = True
                for primitive in mesh.get('primitives', []):
                    if 'extras' in primitive:
                        del primitive['extras']
                        modified = True

        # 5. Filter Scene Metadata
        if not metadata_settings.get('scene', True) and 'scenes' in gltf_data:
            for scene in gltf_data['scenes']:
                if 'extras' in scene:
                    del scene['extras']
                    modified = True

        # Determine final output path
        dst_ext = os.path.splitext(dst_path)[1]
        if dst_ext.lower() != object_ext.lower():
            final_path = os.path.splitext(dst_path)[0] + object_ext
        else:
            final_path = dst_path

        if modified or final_path != dst_path:
            with open(final_path, 'w', encoding='utf-8') as f:
                json.dump(gltf_data, f, indent=4)
            if final_path != dst_path and os.path.isfile(dst_path):
                os.remove(dst_path)

    except Exception as e:
        print(f"Error patching GLTF {dst_path}: {str(e)}")

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
