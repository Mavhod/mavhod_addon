@tool
extends RefCounted

const CONFIG_PATH = "user://mavhod_config.cfg"

static func show_dialog() -> void:
	print("Mavhod: Asset Manager button pressed.")

	# Load the dialog from the scene file
	var asset_dialog = preload("res://addons/mavhod_godot_addon/asset_manager_dialog.tscn").instantiate()

	# Connect the close_requested signal to handle closing via the title bar X button
	asset_dialog.close_requested.connect(func(): asset_dialog.queue_free())

	# Connect the Save Settings button
	var save_button = asset_dialog.get_node("TabContainer/Settings/VBoxContainer/HBoxContainer/SaveButton")
	save_button.pressed.connect(func(): _on_save_settings_pressed(asset_dialog))

	# Load settings when dialog is shown
	_load_settings(asset_dialog)

	# Add to editor and show centered
	EditorInterface.get_base_control().add_child(asset_dialog)
	asset_dialog.popup_centered()

	print("Mavhod: Dialog should be visible now.")


static func _on_save_settings_pressed(dialog: Window) -> void:
	var config = ConfigFile.new()
	config.set_value("paths", "blender_assets", dialog.get_node("TabContainer/Settings/VBoxContainer/GridContainer/BlenderAssetsPathEdit").text)
	config.set_value("paths", "godot_assets", dialog.get_node("TabContainer/Settings/VBoxContainer/GridContainer/GodotAssetsPathEdit").text)
	config.set_value("paths", "blender_scenes", dialog.get_node("TabContainer/Settings/VBoxContainer/GridContainer/BlenderScenesPathEdit").text)
	config.set_value("paths", "godot_scenes", dialog.get_node("TabContainer/Settings/VBoxContainer/GridContainer/GodotScenesPathEdit").text)
	config.save(CONFIG_PATH)

static func _load_settings(dialog: Window) -> void:
	var config = ConfigFile.new()
	var err = config.load(CONFIG_PATH)

	var blender_assets_edit = dialog.get_node("TabContainer/Settings/VBoxContainer/GridContainer/BlenderAssetsPathEdit") as LineEdit
	var godot_assets_edit = dialog.get_node("TabContainer/Settings/VBoxContainer/GridContainer/GodotAssetsPathEdit") as LineEdit
	var blender_scenes_edit = dialog.get_node("TabContainer/Settings/VBoxContainer/GridContainer/BlenderScenesPathEdit") as LineEdit
	var godot_scenes_edit = dialog.get_node("TabContainer/Settings/VBoxContainer/GridContainer/GodotScenesPathEdit") as LineEdit

	if err == OK:
		blender_assets_edit.text = config.get_value("paths", "blender_assets", "")
		godot_assets_edit.text = config.get_value("paths", "godot_assets", "")
		blender_scenes_edit.text = config.get_value("paths", "blender_scenes", "")
		godot_scenes_edit.text = config.get_value("paths", "godot_scenes", "")
	else:
		blender_assets_edit.text = ""
		godot_assets_edit.text = ""
		blender_scenes_edit.text = ""
		godot_scenes_edit.text = ""
