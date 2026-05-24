import bpy
import sys
import argparse
import os

# Add current directory to sys.path to allow importing export_utils
sys.path.append(os.path.dirname(__file__))
import export_utils
from export_utils import copy_and_hash_images, rebind_materials_to_hashed_images

def main():
    # Get arguments passed after "--"
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", required=True, help="Path for the output .gltf file")
    parser.add_argument("--mesh", "-m", help="Name of the mesh data to export")
    args = parser.parse_args(argv)

    if args.mesh:
        print(f"Filtering for mesh data: {args.mesh}")
        # Deselect all objects
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select objects using the specified mesh data
        found = False
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data and obj.data.name == args.mesh:
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                found = True
        
        if not found:
            print(f"Warning: Mesh data '{args.mesh}' not found in the scene.")
            return
    else:
        # If no mesh is specified, select all Mesh objects in the Scene
        bpy.ops.object.select_all(action='DESELECT')
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                obj.select_set(True)

    # 1. Copy and Rename Images
    output_dir = os.path.dirname(args.output)
    print(f"Processing images to: {output_dir}")
    image_mapping = copy_and_hash_images(output_dir)

    # 2. Duplicate Materials and Re-bind Images
    print("Re-binding materials to hashed images...")
    rebind_materials_to_hashed_images(image_mapping)

    print(f"Exporting to: {args.output}")

    # 3. Export as GLTF
    bpy.ops.export_scene.gltf(
        filepath=args.output,
        export_format='GLTF_SEPARATE',
        export_image_format='AUTO',
        use_selection=True
    )

if __name__ == "__main__":
    main()
