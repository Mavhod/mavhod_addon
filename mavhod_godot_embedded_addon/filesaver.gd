class_name FileSaver
extends RefCounted

signal finished(_isSuccess: bool)
var _group_id: int = -1
var filepath: String
var buffer: PackedByteArray = PackedByteArray()
var isSuccess: bool = false;

static func save(_filepath: String, _buffer: PackedByteArray):
	var fileSaver = FileSaver.new()._internal_save(_filepath, _buffer)
	return await fileSaver.finished

func _internal_save(_filepath: String, _buffer: PackedByteArray):
	filepath = _filepath
	buffer = _buffer
	_group_id = WorkerThreadPool.add_group_task(_internal_work, 1)
	WorkerThreadPool.add_task(_wait_logic)
	return self

func _internal_work(_index: int):
	var dir_path = filepath.get_base_dir()
	if not DirAccess.dir_exists_absolute(dir_path):
		var make_dir_err = DirAccess.make_dir_recursive_absolute(dir_path)
		if make_dir_err != OK: return;
	var file = FileAccess.open(filepath, FileAccess.WRITE)
	if not file: return;
	file.store_buffer(buffer)
	file.close()
	isSuccess = true

func _wait_logic():
	WorkerThreadPool.wait_for_group_task_completion(_group_id)
	finished.emit.call_deferred(isSuccess)
