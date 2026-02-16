# Mavhod Godot Addon

A Godot editor plugin to enhance asset workflow and integration with Blender.

## Features

- **Blender Integration**: Select and work with `.blend` files directly from the Godot editor.
- **Custom Dock**: Access tool shortcuts and utilities through a dedicated dock in the Godot inspector/bottom panel area.
- **External Scripting**: Bridge tools via Python scripts (e.g., `extract_meshes.py`).

## Installation

1. Copy the `mavhod_godot_addon` folder into your Godot project's `res://addons/` directory.
2. Open Godot.
3. Go to `Project` > `Project Settings` > `Plugins`.
4. Find **Mavhod Godot Addon** and set its status to **Enabled**.

## Components

- `mavhod_godot_addon.gd`: Main plugin script handling lifecycle and UI integration.
- `dock.tscn`: UI layout for the plugin's dock.
- `extract_meshes.py`: Utility script for mesh processing.

## License

This project is licensed under the **MIT License**.
