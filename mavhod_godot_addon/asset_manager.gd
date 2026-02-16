@tool
extends RefCounted

static func show_dialog() -> void:
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
