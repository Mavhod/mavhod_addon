# Mavhod Blender Addon

A Blender addon for improved asset workflow, specifically designed for importing GLTF/FBX models and managing their materials with an optimized FePBR setup.

## Features

### 1. Advanced GLTF Import
- **Batch Import**: Select and import multiple `.gltf` or `.glb` files at once.
- **Auto-Material Conversion**: Automatically converts imported materials to a custom **FePBR** shader setup.
- **Node Preservation**: Preserves original texture mapping (UVs, Transforms) and other node connections while splicing in the FePBR shader.
- **Multi-Material Support**: Handles meshes with multiple material slots correctly.

### 2. FBX Import Tools
- **Batch Import**: Helper tools for importing multiple `.fbx` files.
- *(Note: Specific features depend on `import_fbx.py` implementation)*

### 3. Mesh Arrangement
- **Auto-Arrange**: Tools to arrange imported meshes in the scene (via `arrange_meshes.py`).

### 4. Convex Hull Creation
- **Create Convex Hull**: Generate collision meshes (UCX) for selected objects via the N-Panel > Mavhod tab.
- **Customizable**: Set decimation ratio (LOD) and naming suffix (default: `_UCX`).
- **Batch Processing**: Works on multiple selected objects simultaneously.

## Installation

1. Download the repository or the release `.zip` file.
2. Open Blender.
3. Go to `Edit` > `Preferences` > `Add-ons`.
4. Click `Install...` and select the downloaded zip file.
5. Enable the addon "Mavhod Blender Addon" (or "Import GLTF Files" depending on registration).

## Usage

1. **Import GLTF**:
   - Go to `File` > `Import` > `Mavhod GLTF Import` (or check the N-Panel / specific menu location).
   - Select your `.gltf`/`.glb` files.
   - The addon will import them and automatically set up the FePBR materials.

## Credits & Acknowledgments

This addon was developed with the assistance of **AI** (specifically Google DeepMind's coding agent) to accelerate development, refactor code, and implement complex material handling logic.

---
*Developed for internal use/specific workflows.*

## License

This project is licensed under the **GPL-2.0-or-later**.
See the `blender_manifest.toml` or LICENSE file (if available) for details.
