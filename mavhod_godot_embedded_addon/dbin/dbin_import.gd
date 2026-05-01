@tool extends EditorImportPlugin

# Importer name (must be unique)
func _get_importer_name() -> String:
	return "custom.dbin.to.resource"

func _get_visible_name() -> String:
	return "DBIN to Generic Resource"

# Accept .dbin files
func _get_recognized_extensions() -> PackedStringArray:
	return PackedStringArray(["dbin"])

# Save as .tres
func _get_save_extension() -> String:
	return "tres"

# Resource type to create
func _get_resource_type() -> String:
	return "DbinResource"

# Preset (we only use default)
func _get_preset_count() -> int:
	return 1

func _get_preset_name(preset_index: int) -> String:
	return "Default"

func _get_import_options(path: String, preset_index: int) -> Array:
	return []

# Important: Function that performs the actual conversion
func _import(source_file: String, save_path: String, options: Dictionary, platform_variants: Array, gen_files: Array) -> int:
	var buffer = FileAccess.get_file_as_bytes(source_file)
	if buffer.is_empty():
		push_error("Failed to read binary file (or file is empty): " + source_file)
		return ERR_FILE_CANT_OPEN

	var data = bytes_to_var(buffer)

	# Create Generic Resource
	var resource = DbinResource.new()
	resource.data = data
	resource.source_dbin_path = source_file

	# Save .tres file
	var filename = save_path + "." + _get_save_extension()
	var err = ResourceSaver.save(resource, filename)

	if err == OK:
		print("DBIN Imported successfully: " + source_file + " → " + filename)
		return OK
	else:
		push_error("Failed to save .tres: " + str(err))
		return err
