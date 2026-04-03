@tool
extends EditorPlugin

func _enter_tree():
	add_import_plugin(preload("json/json_import.gd").new())

func _exit_tree():
	pass
