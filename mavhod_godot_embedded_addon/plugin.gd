@tool
extends EditorPlugin

var json_plugin
var dbin_plugin

func _enter_tree():
	json_plugin = preload("json/json_import.gd").new()
	add_import_plugin(json_plugin)
	
	dbin_plugin = preload("dbin/dbin_import.gd").new()
	add_import_plugin(dbin_plugin)

func _exit_tree():
	remove_import_plugin(json_plugin)
	remove_import_plugin(dbin_plugin)
