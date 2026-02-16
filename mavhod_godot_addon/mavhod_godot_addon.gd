@tool
extends EditorPlugin

var dock

func _enter_tree() -> void:
	dock = preload("res://addons/mavhod_godot_addon/dock.tscn").instantiate()
	add_control_to_dock(EditorPlugin.DOCK_SLOT_LEFT_BR, dock)
	
	# Connect the asset manager button to a function
	var asset_button = dock.get_node("VBoxContainer/AssetManagerButton")
	asset_button.pressed.connect(_on_asset_manager_pressed)


func _exit_tree() -> void:
	if dock:
		remove_control_from_docks(dock)
		dock.queue_free()


func _on_asset_manager_pressed() -> void:
	print("Mavhod: Asset Manager button pressed.")

	# Load the dialog from the scene file
	var asset_dialog = preload("res://addons/mavhod_godot_addon/asset_manager_dialog.tscn").instantiate()

	# Connect the close_requested signal to handle closing via the title bar X button
	asset_dialog.close_requested.connect(func(): asset_dialog.queue_free())

	# Connect the Close button inside the dialog
	var close_button = asset_dialog.get_node("VBoxContainer/HBoxContainer/CloseButton")
	close_button.pressed.connect(func(): asset_dialog.queue_free())

	# Add to editor and show centered
	EditorInterface.get_base_control().add_child(asset_dialog)
	asset_dialog.popup_centered()

	print("Mavhod: Dialog should be visible now.")


func _on_blend_file_selected(_path: String) -> void:
	# Keep this function for future use when we reintegrate line extraction
	pass
