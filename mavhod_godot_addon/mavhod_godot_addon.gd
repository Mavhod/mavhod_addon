@tool
extends EditorPlugin

var dock

const AssetManagerScript = preload("res://addons/mavhod_godot_addon/asset_manager.gd")

func _enter_tree() -> void:
	dock = preload("res://addons/mavhod_godot_addon/dock.tscn").instantiate()
	add_control_to_dock(EditorPlugin.DOCK_SLOT_LEFT_BR, dock)

	# Connect the asset manager button directly to the asset manager script
	var asset_button = dock.get_node("VBoxContainer/AssetManagerButton")
	asset_button.pressed.connect(AssetManagerScript.show_dialog)


func _exit_tree() -> void:
	if dock:
		remove_control_from_docks(dock)
		dock.queue_free()


func _on_blend_file_selected(_path: String) -> void:
	# Keep this function for future use when we reintegrate line extraction
	pass
