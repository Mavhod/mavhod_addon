@tool extends EditorImportPlugin

# Importer name (must be unique)
func _get_importer_name() -> String:
	return "custom.json.to.resource"

func _get_visible_name() -> String:
	return "JSON to Generic Resource"

# Accept .json files
func _get_recognized_extensions() -> PackedStringArray:
	return PackedStringArray(["json"])

# Save as .tres
func _get_save_extension() -> String:
	return "tres"

# Resource type to create
func _get_resource_type() -> String:
	return "JsonResource" # Must match the class_name we create

# Preset (we only use default)
func _get_preset_count() -> int:
	return 1

func _get_preset_name(preset_index: int) -> String:
	return "Default"

func _get_import_options(path: String, preset_index: int) -> Array:
	return []

# Important: Function that performs the actual conversion
func _import(source_file: String, save_path: String, options: Dictionary, platform_variants: Array, gen_files: Array) -> int:
	var file = FileAccess.open(source_file, FileAccess.READ)
	if not file:
		return ERR_FILE_CANT_OPEN

	var json_text = file.get_as_text()
	var json = JSON.new()
	var parse_err = json.parse(json_text)

	if parse_err != OK:
		push_error("JSON Parse error in file %s: %s" % [source_file, json.get_error_message()])
		return ERR_PARSE_ERROR

	# Create Generic Resource
	var resource = JsonResource.new()
	resource.data = json.data
	resource.source_json_path = source_file

	# Save .tres file
	var filename = save_path + "." + _get_save_extension()
	var err = ResourceSaver.save(resource, filename)

	if err == OK:
		print("JSON Imported successfully: " + source_file + " → " + filename)
		return OK
	else:
		push_error("Failed to save .tres: " + str(err))
		return err
