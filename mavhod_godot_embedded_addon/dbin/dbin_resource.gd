@tool extends Resource
class_name DbinResource

@export var data: Variant
@export var source_dbin_path: String = ""

## Save any data to a .dbin file on disk
static func save_to_file(path: String, p_data: Variant) -> Error:
	var buffer = var_to_bytes(p_data)
	var dir_path = path.get_base_dir()
	if not DirAccess.dir_exists_absolute(dir_path):
		var make_dir_err = DirAccess.make_dir_recursive_absolute(dir_path)
		if make_dir_err != OK:
			push_error("Failed to create directory: %s (Error: %d)" % [dir_path, make_dir_err])
			return make_dir_err

	var file = FileAccess.open(path, FileAccess.WRITE)
	if not file:
		var err = FileAccess.get_open_error()
		push_error("Failed to open file for writing: %s (Error: %d)" % [path, err])
		return err
	
	file.store_buffer(buffer)
	file.close()
	return OK

## Save data to a .dbin file asynchronously and wait for completion (can be awaited)
static func save_to_file_async(path: String, p_data: Variant) -> Error:
	var err_box = [OK]
	var task_id = WorkerThreadPool.add_task(
		func():
			err_box[0] = save_to_file(path, p_data)
	)
	
	# Wait for completion without blocking the main thread
	while not WorkerThreadPool.is_task_completed(task_id):
		await Engine.get_main_loop().process_frame
	
	return err_box[0]

## Load data directly from a .dbin file on disk (works for res:// and user://)
static func load_from_file(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		push_error("File not found: %s" % path)
		return null
		
	var buffer = FileAccess.get_file_as_bytes(path)
	if buffer.is_empty():
		return null
		
	return bytes_to_var(buffer)

## Load data directly from a .dbin file asynchronously (can be awaited)
static func load_from_file_async(path: String) -> Variant:
	var result_box = [null]
	var task_id = WorkerThreadPool.add_task(
		func():
			result_box[0] = load_from_file(path)
	)
	
	while not WorkerThreadPool.is_task_completed(task_id):
		await Engine.get_main_loop().process_frame
		
	return result_box[0]
