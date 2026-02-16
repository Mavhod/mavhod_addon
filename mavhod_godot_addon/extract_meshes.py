#!/usr/bin/env python3
"""
Script to extract mesh information from a .blend file using Blender's Python API.
This script is meant to be called from the Godot addon.
"""

import bpy
import sys
import os
import json

def extract_meshes_from_blend(blend_file_path):
    """Extract mesh names from a .blend file"""
    try:
        # Load the .blend file
        bpy.ops.wm.open_mainfile(filepath=blend_file_path)
        
        # Find all mesh objects in the scene
        meshes = []
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                meshes.append(obj.name)
        
        return meshes
    
    except Exception as e:
        print(f"ERROR: {str(e)}", file=sys.stderr)
        return []

def main():
    if len(sys.argv) < 2:
        print("Usage: blender -b -P extract_meshes.py -- <blend_file_path>", file=sys.stderr)
        sys.exit(1)
    
    # Find the blend file path in the remaining arguments
    blend_file_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--":
            blend_file_path = sys.argv[i + 1]
            break
    
    if not blend_file_path or not os.path.exists(blend_file_path):
        print(f"ERROR: Blend file does not exist: {blend_file_path}", file=sys.stderr)
        sys.exit(1)
    
    meshes = extract_meshes_from_blend(blend_file_path)
    
    # Print the results as JSON
    result = {
        "blend_file": blend_file_path,
        "meshes": meshes,
        "count": len(meshes)
    }
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()