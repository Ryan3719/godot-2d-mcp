@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const TypePolicy := preload("res://addons/godot_2d_mcp/utils/type_policy.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_SIGNALS := 256
const MAX_CONNECTIONS_PER_SIGNAL := 128
const MAX_BIND_ARGUMENTS := 16
const MAX_BIND_CONTAINER_ITEMS := 128
const MAX_BIND_DEPTH := 8

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_signals(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params, "path", false)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	var signals: Array[Dictionary] = []
	var truncated := false
	for signal_info_value in node.get_signal_list():
		if signals.size() >= MAX_SIGNALS:
			truncated = true
			break
		var signal_info: Dictionary = signal_info_value
		var signal_name := str(signal_info.get("name", ""))
		if signal_name.is_empty():
			continue
		signals.append(_serialize_signal(node, scene_root, signal_info))
	return {
		"path": ScenePath.from_node(node, scene_root),
		"type": node.get_class(),
		"signals": signals,
		"count": signals.size(),
		"truncated": truncated,
	}


func connect_signal(params: Dictionary) -> Dictionary:
	var guarded := MutationGuard.require_scene(params)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var source_result := _resolve_scene_node(scene_root, str(params.get("source_path", "")), "Source")
	if source_result.has("_error"):
		return source_result
	var target_result := _resolve_scene_node(scene_root, str(params.get("target_path", "")), "Target")
	if target_result.has("_error"):
		return target_result
	var source: Node = source_result["node"]
	var target: Node = target_result["node"]
	var source_editability := _require_locally_owned(source, scene_root, "connect signals from")
	if source_editability != null:
		return source_editability
	var target_editability := _require_locally_owned(target, scene_root, "connect signals to")
	if target_editability != null:
		return target_editability

	var signal_name := str(params.get("signal", "")).strip_edges()
	if signal_name.is_empty() or signal_name.length() > 256:
		return Errors.make("MISSING_PARAMETER", "signal is required")
	if not source.has_signal(StringName(signal_name)):
		return Errors.make(
			"SIGNAL_NOT_FOUND",
			"Signal '%s' does not exist on %s" % [signal_name, source.get_class()],
			false,
			"Call node_get_signals to inspect available signals."
		)
	var method_name := str(params.get("method", "")).strip_edges()
	if method_name.is_empty() or method_name.length() > 256:
		return Errors.make("MISSING_PARAMETER", "method is required")
	if not target.has_method(StringName(method_name)):
		return Errors.make(
			"TARGET_METHOD_NOT_FOUND",
			"Method '%s' does not exist on %s" % [method_name, target.get_class()],
			false,
			"Choose an existing method on the target node. This tool does not create script methods."
		)
	var binds_result := _parse_binds(params)
	if binds_result.has("_error"):
		return binds_result
	var binds: Array = binds_result["binds"]
	var arity_result := _validate_connection_arity(source, signal_name, target, method_name, binds)
	if arity_result.has("_error"):
		return arity_result
	var options_result := _parse_options(params)
	if options_result.has("_error"):
		return options_result

	var callable := Callable(target, StringName(method_name))
	if not binds.is_empty():
		callable = callable.bindv(binds)
	if source.is_connected(StringName(signal_name), callable):
		return Errors.make(
			"SIGNAL_ALREADY_CONNECTED",
			"Signal '%s' is already connected to %s.%s" % [signal_name, target.name, method_name],
			false,
			"Call node_get_signals to inspect the existing connection or use signal_disconnect first."
		)
	var flags: int = options_result["flags"]
	_undo_redo.create_action(
		"Godot 2D MCP: Connect %s.%s to %s.%s" % [source.name, signal_name, target.name, method_name],
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(source, "connect", StringName(signal_name), callable, flags)
	_undo_redo.add_undo_method(source, "disconnect", StringName(signal_name), callable)
	_undo_redo.commit_action()

	return {
		"source_path": ScenePath.from_node(source, scene_root),
		"signal": signal_name,
		"target_path": ScenePath.from_node(target, scene_root),
		"method": method_name,
		"binds": _serialize_binds(binds),
		"persistent": true,
		"deferred": options_result["deferred"],
		"one_shot": options_result["one_shot"],
		"undoable": true,
		"_scene_mutated": true,
	}


func disconnect_signal(params: Dictionary) -> Dictionary:
	var guarded := MutationGuard.require_scene(params)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var source_result := _resolve_scene_node(scene_root, str(params.get("source_path", "")), "Source")
	if source_result.has("_error"):
		return source_result
	var target_result := _resolve_scene_node(scene_root, str(params.get("target_path", "")), "Target")
	if target_result.has("_error"):
		return target_result
	var source: Node = source_result["node"]
	var target: Node = target_result["node"]
	var source_editability := _require_locally_owned(source, scene_root, "disconnect signals from")
	if source_editability != null:
		return source_editability
	var target_editability := _require_locally_owned(target, scene_root, "disconnect signals to")
	if target_editability != null:
		return target_editability

	var signal_name := str(params.get("signal", "")).strip_edges()
	var method_name := str(params.get("method", "")).strip_edges()
	if signal_name.is_empty() or method_name.is_empty():
		return Errors.make("MISSING_PARAMETER", "signal and method are required")
	var connection := _find_connection(source, signal_name, target, method_name)
	if connection.is_empty():
		return Errors.make(
			"SIGNAL_CONNECTION_NOT_FOUND",
			"No connection exists from %s.%s to %s.%s"
			% [source.name, signal_name, target.name, method_name],
			false,
			"Call node_get_signals to inspect current connections."
		)
	var flags := int(connection.get("flags", 0))
	if not bool(flags & Object.CONNECT_PERSIST):
		return Errors.make(
			"NON_PERSISTENT_CONNECTION",
			"Only persistent scene connections can be changed through this tool",
			false,
			"Use Godot's runtime API for temporary signal connections."
		)
	var callable: Callable = connection["callable"]
	_undo_redo.create_action(
		"Godot 2D MCP: Disconnect %s.%s from %s.%s"
		% [source.name, signal_name, target.name, method_name],
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(source, "disconnect", StringName(signal_name), callable)
	_undo_redo.add_undo_method(source, "connect", StringName(signal_name), callable, flags)
	_undo_redo.commit_action()

	return {
		"source_path": ScenePath.from_node(source, scene_root),
		"signal": signal_name,
		"target_path": ScenePath.from_node(target, scene_root),
		"method": method_name,
		"undoable": true,
		"_scene_mutated": true,
	}


func _serialize_signal(node: Node, scene_root: Node, signal_info: Dictionary) -> Dictionary:
	var signal_name := str(signal_info.get("name", ""))
	var arguments: Array[Dictionary] = []
	var raw_arguments = signal_info.get("args", [])
	if raw_arguments is Array:
		for argument_info_value in raw_arguments:
			var argument_info: Dictionary = argument_info_value
			arguments.append(
				{
					"name": str(argument_info.get("name", "")),
					"type": type_string(int(argument_info.get("type", TYPE_NIL))),
					"class_name": str(argument_info.get("class_name", "")),
					"hint": int(argument_info.get("hint", PROPERTY_HINT_NONE)),
					"hint_string": str(argument_info.get("hint_string", "")),
				}
			)
	var connections: Array[Dictionary] = []
	var truncated := false
	for connection_value in node.get_signal_connection_list(StringName(signal_name)):
		if connections.size() >= MAX_CONNECTIONS_PER_SIGNAL:
			truncated = true
			break
		var connection: Dictionary = connection_value
		connections.append(_serialize_connection(connection, scene_root))
	return {
		"name": signal_name,
		"arguments": arguments,
		"connections": connections,
		"connection_count": connections.size(),
		"connections_truncated": truncated,
	}


func _serialize_connection(connection: Dictionary, scene_root: Node) -> Dictionary:
	var callable: Callable = connection.get("callable", Callable())
	var target_object := callable.get_object()
	var target_path := ""
	var target_type := ""
	var target_in_scene := false
	if target_object is Node:
		var target: Node = target_object
		target_type = target.get_class()
		if target == scene_root or scene_root.is_ancestor_of(target):
			target_path = ScenePath.from_node(target, scene_root)
			target_in_scene = true
	var flags := int(connection.get("flags", 0))
	return {
		"target_path": target_path,
		"target_type": target_type,
		"target_in_scene": target_in_scene,
		"method": str(callable.get_method()),
		"binds": _serialize_binds(callable.get_bound_arguments()),
		"unbound_count": callable.get_unbound_arguments_count(),
		"custom_callable": callable.is_custom(),
		"flags": flags,
		"persistent": bool(flags & Object.CONNECT_PERSIST),
		"deferred": bool(flags & Object.CONNECT_DEFERRED),
		"one_shot": bool(flags & Object.CONNECT_ONE_SHOT),
	}


func _serialize_binds(binds: Array) -> Array:
	var result: Array = []
	for bind in binds:
		result.append(VariantCodec.serialize(bind))
	return result


func _parse_binds(params: Dictionary) -> Dictionary:
	var raw_binds = params.get("binds", [])
	if not raw_binds is Array:
		return Errors.make("INVALID_BIND_ARGUMENT", "binds must be an array")
	if raw_binds.size() > MAX_BIND_ARGUMENTS:
		return Errors.make(
			"REQUEST_LIMIT_EXCEEDED",
			"binds can contain at most %d values" % MAX_BIND_ARGUMENTS
		)
	for bind in raw_binds:
		if not _is_supported_bind_value(bind):
			return Errors.make(
				"INVALID_BIND_ARGUMENT",
				"binds only support bounded JSON-compatible values",
				false,
				"Use null, booleans, finite numbers, strings, arrays, or dictionaries."
			)
	return {"binds": raw_binds.duplicate(true)}


func _is_supported_bind_value(value: Variant, depth: int = 0) -> bool:
	if depth > MAX_BIND_DEPTH:
		return false
	match typeof(value):
		TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_STRING:
			return true
		TYPE_FLOAT:
			return is_finite(value)
		TYPE_ARRAY:
			if value.size() > MAX_BIND_CONTAINER_ITEMS:
				return false
			for item in value:
				if not _is_supported_bind_value(item, depth + 1):
					return false
			return true
		TYPE_DICTIONARY:
			if value.size() > MAX_BIND_CONTAINER_ITEMS:
				return false
			for key in value:
				if not key is String or not _is_supported_bind_value(value[key], depth + 1):
					return false
			return true
	return false


func _parse_options(params: Dictionary) -> Dictionary:
	var deferred = params.get("deferred", false)
	var one_shot = params.get("one_shot", false)
	if not deferred is bool or not one_shot is bool:
		return Errors.make("INVALID_PARAMETER", "deferred and one_shot must be booleans")
	var flags := Object.CONNECT_PERSIST
	if deferred:
		flags |= Object.CONNECT_DEFERRED
	if one_shot:
		flags |= Object.CONNECT_ONE_SHOT
	return {"flags": flags, "deferred": deferred, "one_shot": one_shot}


func _validate_connection_arity(
	source: Node, signal_name: String, target: Node, method_name: String, binds: Array
) -> Dictionary:
	var signal_info := _find_signal_info(source, signal_name)
	var method_info := _find_method_info(target, method_name)
	if signal_info.is_empty() or method_info.is_empty():
		return Errors.make(
			"METHOD_SIGNATURE_UNAVAILABLE",
			"Godot could not read the signal or target method signature",
			false,
			"Choose a built-in or script method that appears in Godot's method list."
		)
	var signal_arguments: Array = signal_info.get("args", [])
	var method_arguments: Array = method_info.get("args", [])
	var default_arguments: Array = method_info.get("default_args", [])
	var supplied_count: int = signal_arguments.size() + binds.size()
	var required_count: int = maxi(0, method_arguments.size() - default_arguments.size())
	var is_vararg := bool(int(method_info.get("flags", 0)) & METHOD_FLAG_VARARG)
	if supplied_count < required_count or (not is_vararg and supplied_count > method_arguments.size()):
		return Errors.make(
			"SIGNAL_METHOD_ARITY_MISMATCH",
			"%s.%s emits %d arguments and binds provide %d, but %s.%s accepts %d to %d"
			% [
				source.name,
				signal_name,
				signal_arguments.size(),
				binds.size(),
				target.name,
				method_name,
				required_count,
				method_arguments.size(),
			],
			false,
			"Change the binding arguments or choose a compatible target method."
		)
	return {}


func _find_signal_info(node: Node, signal_name: String) -> Dictionary:
	for signal_info_value in node.get_signal_list():
		var signal_info: Dictionary = signal_info_value
		if str(signal_info.get("name", "")) == signal_name:
			return signal_info
	return {}


func _find_method_info(node: Node, method_name: String) -> Dictionary:
	for method_info_value in node.get_method_list():
		var method_info: Dictionary = method_info_value
		if str(method_info.get("name", "")) == method_name:
			return method_info
	return {}


func _find_connection(source: Node, signal_name: String, target: Node, method_name: String) -> Dictionary:
	for connection_value in source.get_signal_connection_list(StringName(signal_name)):
		var connection: Dictionary = connection_value
		var callable: Callable = connection.get("callable", Callable())
		if callable.get_object() == target and str(callable.get_method()) == method_name:
			return connection
	return {}


func _resolve_node(params: Dictionary, path_key: String, require_writable: bool) -> Dictionary:
	var guarded := MutationGuard.require_scene(params, require_writable)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var result := _resolve_scene_node(scene_root, str(params.get(path_key, "")), "Node")
	if result.has("_error"):
		return result
	result["scene_root"] = scene_root
	return result


func _resolve_scene_node(scene_root: Node, path: String, label: String) -> Dictionary:
	var requested_path := path.strip_edges()
	if requested_path.is_empty():
		return Errors.make("MISSING_PARAMETER", "%s path is required" % label.to_lower())
	var node := ScenePath.resolve(requested_path, scene_root)
	if node == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"%s node not found: %s" % [label, requested_path],
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not TypePolicy.is_supported_node_class(node.get_class()):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"%s node is outside the supported 2D policy: %s" % [label, node.get_class()]
		)
	return {"node": node}


func _require_locally_owned(node: Node, scene_root: Node, operation: String) -> Variant:
	if node == scene_root or node.owner == scene_root:
		return null
	return Errors.make(
		"PACKED_SCENE_BOUNDARY",
		"Cannot %s node '%s' because it belongs to an instanced scene" % [operation, node.name],
		false,
		"Edit the source PackedScene or target a locally owned node."
	)
