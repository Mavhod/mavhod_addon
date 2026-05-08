class_name FileLoader
extends RefCounted

signal finished(result)

var _group_id: int = -1
var filepaths: Array
var buffers: Array

static func loads(_filepaths: Array) -> Array:
	var fileloader = FileLoader.new()._internal_loads(_filepaths)
	return await fileloader.finished

func _internal_loads(_filepaths: Array):
	filepaths = _filepaths
	buffers = []
	buffers.resize(filepaths.size())
	_group_id = WorkerThreadPool.add_group_task(_internal_work, filepaths.size())
	WorkerThreadPool.add_task(_wait_logic)
	return self

func _internal_work(index: int):
	var filepath = filepaths[index]
	if not FileAccess.file_exists(filepath): buffers[index] = PackedByteArray(); return ;
	buffers[index] = FileAccess.get_file_as_bytes(filepath)

func _wait_logic():
	WorkerThreadPool.wait_for_group_task_completion(_group_id)
	finished.emit.call_deferred(buffers)
