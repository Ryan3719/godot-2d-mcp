@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")

const MAX_ITEMS := 256
const MAX_TEXT_LENGTH := 4096
const MAX_PATH_LENGTH := 4096
const PERSISTENT_ITEM_FIELDS := ["text", "icon_path", "selectable", "disabled"]

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_item_list_items(params: Dictionary) -> Dictionary:
	var resolved := _resolve_item_list(params, false)
	if resolved.has("_error"):
		return resolved
	var page := _parse_page(params)
	if page.has("_error"):
		return page
	return _items_response(resolved["item_list"], resolved["scene_root"], page["offset"], page["limit"])


func set_item_list_items(params: Dictionary) -> Dictionary:
	var resolved := _resolve_item_list(params)
	if resolved.has("_error"):
		return resolved
	var parsed := _parse_items(params)
	if parsed.has("_error"):
		return parsed
	var item_list: ItemList = resolved["item_list"]
	var previous_items := _snapshot_items(item_list)
	var next_items: Array = parsed["items"]
	if _items_equal(previous_items, next_items):
		var unchanged := _items_response(item_list, resolved["scene_root"], 0, MAX_ITEMS)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_items(item_list, resolved["scene_root"], previous_items, next_items)
	var result := _items_response(item_list, resolved["scene_root"], 0, MAX_ITEMS)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_item_list_items(params: Dictionary) -> Dictionary:
	var resolved := _resolve_item_list(params)
	if resolved.has("_error"):
		return resolved
	var item_list: ItemList = resolved["item_list"]
	var previous_items := _snapshot_items(item_list)
	if previous_items.is_empty():
		var unchanged := _items_response(item_list, resolved["scene_root"], 0, MAX_ITEMS)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_items(item_list, resolved["scene_root"], previous_items, [])
	var result := _items_response(item_list, resolved["scene_root"], 0, MAX_ITEMS)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_item_list(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var guarded := MutationGuard.require_scene(params, require_writable)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var path := str(params.get("path", "")).strip_edges()
	if path.is_empty():
		return Errors.make("MISSING_PARAMETER", "path is required")
	var node := ScenePath.resolve(path, scene_root)
	if node == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"Node not found: %s" % path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not node is ItemList:
		return Errors.make(
			"ITEM_LIST_REQUIRED",
			"Node '%s' is %s, not an ItemList" % [node.name, node.get_class()],
			false,
			"Target a locally owned ItemList."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit ItemList '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned ItemList."
		)
	return {"item_list": node as ItemList, "scene_root": scene_root}


func _parse_page(params: Dictionary) -> Dictionary:
	var offset := _parse_integer(params.get("offset", 0), "offset", 0, MAX_ITEMS)
	if offset.has("_error"):
		return offset
	var limit := _parse_integer(params.get("limit", 100), "limit", 1, MAX_ITEMS)
	if limit.has("_error"):
		return limit
	return {"offset": offset["value"], "limit": limit["value"]}


func _parse_items(params: Dictionary) -> Dictionary:
	var raw_items: Variant = params.get("items", null)
	if not raw_items is Array or raw_items.is_empty() or raw_items.size() > MAX_ITEMS:
		return _invalid_configuration(
			"items must be a non-empty array containing at most %d entries" % MAX_ITEMS
		)
	var items: Array = []
	for index in range(raw_items.size()):
		var parsed := _parse_item(raw_items[index], index)
		if parsed.has("_error"):
			return parsed
		items.append(parsed["item"])
	return {"items": items}


func _parse_item(raw_item: Variant, index: int) -> Dictionary:
	if not raw_item is Dictionary:
		return _invalid_configuration("items[%d] must be an object" % index)
	for raw_key in raw_item:
		if not raw_key is String or not PERSISTENT_ITEM_FIELDS.has(raw_key):
			return _invalid_configuration("items[%d] contains an unsupported ItemList field" % index)
	var text_result := _parse_string(raw_item.get("text", ""), "items[%d].text" % index, MAX_TEXT_LENGTH)
	if text_result.has("_error"):
		return text_result
	var icon_result := _load_optional_texture(raw_item.get("icon_path", ""), "items[%d].icon_path" % index)
	if icon_result.has("_error"):
		return icon_result
	var selectable_result := _parse_bool(raw_item.get("selectable", true), "items[%d].selectable" % index)
	if selectable_result.has("_error"):
		return selectable_result
	var disabled_result := _parse_bool(raw_item.get("disabled", false), "items[%d].disabled" % index)
	if disabled_result.has("_error"):
		return disabled_result
	return {
		"item": {
			"text": text_result["value"],
			"icon": icon_result["value"],
			"selectable": selectable_result["value"],
			"disabled": disabled_result["value"],
		}
	}


func _parse_string(raw_value: Variant, label: String, maximum: int) -> Dictionary:
	if not raw_value is String or raw_value.length() > maximum:
		return _invalid_configuration("%s must be a string up to %d characters" % [label, maximum])
	return {"value": raw_value}


func _parse_bool(raw_value: Variant, label: String) -> Dictionary:
	if not raw_value is bool:
		return _invalid_configuration("%s must be a boolean" % label)
	return {"value": raw_value}


func _parse_integer(raw_value: Variant, label: String, minimum: int, maximum: int) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool \
		or not is_finite(float(raw_value)) or float(raw_value) != floorf(float(raw_value)):
		return _invalid_configuration("%s must be an integer between %d and %d" % [label, minimum, maximum])
	var value := int(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration("%s must be an integer between %d and %d" % [label, minimum, maximum])
	return {"value": value}


func _load_optional_texture(raw_value: Variant, label: String) -> Dictionary:
	if not raw_value is String or raw_value.length() > MAX_PATH_LENGTH:
		return _invalid_configuration("%s must be an empty string or a res:// Texture2D path" % label)
	var path: String = raw_value.strip_edges()
	if path.is_empty():
		return {"value": null}
	if not path.begins_with("res://"):
		return Errors.make(
			"PROJECT_PATH_REQUIRED",
			"%s must remain inside the project res:// directory" % label
		)
	if not ResourceLoader.exists(path):
		return Errors.make("RESOURCE_NOT_FOUND", "Resource does not exist: %s" % path)
	var resource := ResourceLoader.load(path)
	if resource == null or not resource is Texture2D:
		return Errors.make(
			"RESOURCE_TYPE_MISMATCH",
			"%s must load a Texture2D" % label,
			false,
			"Use an existing project-local Texture2D resource."
		)
	return {"value": resource as Texture2D}


func _snapshot_items(item_list: ItemList) -> Array:
	var items: Array = []
	for index in range(item_list.get_item_count()):
		items.append({
			"text": item_list.get_item_text(index),
			"icon": item_list.get_item_icon(index),
			"selectable": item_list.is_item_selectable(index),
			"disabled": item_list.is_item_disabled(index),
		})
	return items


func _items_equal(left: Array, right: Array) -> bool:
	if left.size() != right.size():
		return false
	for index in range(left.size()):
		var left_item: Dictionary = left[index]
		var right_item: Dictionary = right[index]
		if (
			left_item["text"] != right_item["text"]
			or left_item["selectable"] != right_item["selectable"]
			or left_item["disabled"] != right_item["disabled"]
			or not _textures_equal(left_item["icon"], right_item["icon"])
		):
			return false
	return true


func _textures_equal(left: Texture2D, right: Texture2D) -> bool:
	if left == right:
		return true
	if left == null or right == null:
		return false
	return not left.resource_path.is_empty() \
		and left.resource_path == right.resource_path


func _commit_items(item_list: ItemList, scene_root: Node, previous_items: Array, next_items: Array) -> void:
	_undo_redo.create_action(
		"Godot 2D MCP: Replace ItemList items for %s" % item_list.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_undo_redo.add_do_method(self, "_replace_items", item_list, next_items)
	_undo_redo.add_undo_method(self, "_replace_items", item_list, previous_items)
	_add_resource_references(next_items, true)
	_add_resource_references(previous_items, false)
	_undo_redo.commit_action()


func _replace_items(item_list: ItemList, items: Array) -> void:
	item_list.clear()
	for item in items:
		var icon: Texture2D = item["icon"]
		var index := item_list.add_item(item["text"], icon, item["selectable"])
		item_list.set_item_disabled(index, item["disabled"])


func _add_resource_references(items: Array, do_reference: bool) -> void:
	for item in items:
		if not item is Dictionary:
			continue
		var icon: Variant = item.get("icon", null)
		if not icon is Resource:
			continue
		if do_reference:
			_undo_redo.add_do_reference(icon)
		else:
			_undo_redo.add_undo_reference(icon)


func _items_response(item_list: ItemList, scene_root: Node, offset: int, limit: int) -> Dictionary:
	var items := _snapshot_items(item_list)
	var start := min(offset, items.size())
	var end := min(start + limit, items.size())
	var serialized: Array = []
	for index in range(start, end):
		serialized.append(_serialize_item(items[index]))
	return {
		"path": ScenePath.from_node(item_list, scene_root),
		"type": item_list.get_class(),
		"item_count": items.size(),
		"item_offset": start,
		"items": serialized,
		"items_truncated": end < items.size(),
		"persistent_item_fields": PERSISTENT_ITEM_FIELDS.duplicate(),
	}


func _serialize_item(item: Dictionary) -> Dictionary:
	return {
		"text": item["text"],
		"icon": _resource_descriptor(item["icon"]),
		"selectable": item["selectable"],
		"disabled": item["disabled"],
	}


func _resource_descriptor(resource: Resource) -> Dictionary:
	if resource == null:
		return {"assigned": false, "origin": "none", "resource_path": "", "resource_type": ""}
	return {
		"assigned": true,
		"origin": "external" if not resource.resource_path.is_empty() else "embedded",
		"resource_path": resource.resource_path,
		"resource_type": resource.get_class(),
	}


func _invalid_configuration(message: String) -> Dictionary:
	return Errors.make("INVALID_ITEM_LIST_CONFIGURATION", message)
