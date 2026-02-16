@tool
extends EditorPlugin

var dock
var file_dialog: FileDialog

func _enter_tree() -> void:
	dock = preload("res://addons/mavhod_godot_addon/dock.tscn").instantiate()
	add_control_to_dock(EditorPlugin.DOCK_SLOT_LEFT_BR, dock)
	
	# Connect the test button to a function
	var test_button = dock.get_node("VBoxContainer/TestButton")
	test_button.pressed.connect(_on_test_button_pressed)


func _exit_tree() -> void:
	if dock:
		remove_control_from_docks(dock)
		dock.queue_free()


func _on_test_button_pressed() -> void:
	# Create and show a file dialog to select .blend files
	file_dialog = FileDialog.new()
	file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	file_dialog.add_filter("*.blend", "Blender Files")
	file_dialog.title = "Select .blend file"
	file_dialog.access = FileDialog.ACCESS_FILESYSTEM  # Allow access outside project
	
	file_dialog.file_selected.connect(_on_blend_file_selected)
	file_dialog.canceled.connect(_on_dialog_closed)
	
	# Show the dialog
	get_editor_interface().get_base_control().add_child(file_dialog)
	file_dialog.popup_centered_ratio(0.5)

func _on_blend_file_selected(path: String) -> void:
	var blender_path = get_editor_interface()\
		.get_editor_settings()\
		.get_setting("filesystem/import/blender/blender_path")
	print("Selected .blend file: ", path)
	print("blender_path: ", blender_path)
	if blender_path != "":
		var output = []
		OS.execute(blender_path, ["--version"], output)
		print(output)
	# Clean up the dialog
	file_dialog.queue_free()


func _on_dialog_closed() -> void:
	# Clean up the dialog if cancelled
	if file_dialog:
		file_dialog.queue_free()
