@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const TypePolicy := preload("res://addons/godot_2d_mcp/utils/type_policy.gd")

const MAX_DESCRIPTION_ITEMS := 500
const DESCRIPTION_SECTIONS := {
	"overview": true,
	"properties": true,
	"methods": true,
	"signals": true,
	"enums": true,
}


func search(params: Dictionary) -> Dictionary:
	var query := str(params.get("query", "")).strip_edges().to_lower()
	var offset := maxi(0, int(params.get("offset", 0)))
	var limit := clampi(int(params.get("limit", 100)), 1, 500)
	var matches: Array[Dictionary] = []

	var class_names := Array(ClassDB.get_class_list())
	class_names.sort()
	for class_name_value in class_names:
		var type_name := StringName(class_name_value)
		var class_string := String(type_name)
		if not query.is_empty() and not class_string.to_lower().contains(query):
			continue
		if not TypePolicy.is_supported_node_class(type_name):
			continue
		matches.append(
			{
				"name": class_string,
				"parent": String(ClassDB.get_parent_class(type_name)),
				"category": TypePolicy.category(type_name),
				"property_count": ClassDB.class_get_property_list(type_name).size(),
				"signal_count": ClassDB.class_get_signal_list(type_name).size(),
			}
		)

	var end := mini(offset + limit, matches.size())
	var page: Array[Dictionary] = []
	if offset < matches.size():
		page.assign(matches.slice(offset, end))
	return {
		"classes": page,
		"total": matches.size(),
		"offset": offset,
		"limit": limit,
		"has_more": end < matches.size(),
	}


func coverage(params: Dictionary) -> Dictionary:
	var query := str(params.get("query", "")).strip_edges().to_lower()
	var scope := str(params.get("scope", "all")).strip_edges().to_lower()
	var offset := maxi(0, int(params.get("offset", 0)))
	var limit := clampi(int(params.get("limit", 100)), 1, 500)
	var entries: Array[Dictionary] = []
	var summary := {"node": 0, "resource": 0, "semantic": 0, "generic": 0, "semantic_smoke": 0}

	var class_names := Array(ClassDB.get_class_list())
	class_names.sort()
	for class_name_value in class_names:
		var type_name := StringName(class_name_value)
		var class_string := String(type_name)
		if not query.is_empty() and not class_string.to_lower().contains(query):
			continue
		var kind := TypePolicy.coverage_kind(type_name)
		if kind.is_empty() or (scope != "all" and kind != scope):
			continue
		var semantic_tools := TypePolicy.coverage_semantic_tools(type_name, kind)
		var test_status := TypePolicy.coverage_test_status(type_name)
		summary[kind] = int(summary[kind]) + 1
		if semantic_tools.is_empty():
			summary["generic"] = int(summary["generic"]) + 1
		else:
			summary["semantic"] = int(summary["semantic"]) + 1
		if test_status == "semantic_smoke":
			summary["semantic_smoke"] = int(summary["semantic_smoke"]) + 1
		entries.append(
			{
				"name": class_string,
				"parent": String(ClassDB.get_parent_class(type_name)),
				"kind": kind,
				"category": TypePolicy.coverage_category(type_name, kind),
				"instantiable": ClassDB.can_instantiate(type_name),
				"property_count": ClassDB.class_get_property_list(type_name).size(),
				"signal_count": ClassDB.class_get_signal_list(type_name).size(),
				"base_support": TypePolicy.coverage_base_support(kind),
				"semantic_tools": semantic_tools,
				"support_level": "semantic" if not semantic_tools.is_empty() else "generic",
				"test_status": test_status,
			}
		)

	var end := mini(offset + limit, entries.size())
	var page: Array[Dictionary] = []
	if offset < entries.size():
		page.assign(entries.slice(offset, end))
	var version_info := Engine.get_version_info()
	return {
		"audit_version": 1,
		"engine": {
			"major": int(version_info.get("major", 0)),
			"minor": int(version_info.get("minor", 0)),
			"patch": int(version_info.get("patch", 0)),
			"status": str(version_info.get("status", "")),
		},
		"scope": scope,
		"query": query,
		"entries": page,
		"total": entries.size(),
		"offset": offset,
		"limit": limit,
		"has_more": end < entries.size(),
		"summary": summary,
	}


func describe(params: Dictionary) -> Dictionary:
	var type_name := StringName(str(params.get("type", "")).strip_edges())
	if String(type_name).is_empty():
		return Errors.make("MISSING_PARAMETER", "type is required")
	var kind := TypePolicy.coverage_kind(type_name)
	if kind.is_empty():
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Class '%s' is outside the supported 2D policy" % String(type_name),
			false,
			"Use class_search or class_2d_coverage to select a supported 2D class."
		)
	var section := str(params.get("section", "overview")).strip_edges().to_lower()
	if not DESCRIPTION_SECTIONS.has(section):
		return Errors.make(
			"INVALID_CLASS_DESCRIPTION_SECTION",
			"section must be overview, properties, methods, signals, or enums"
		)
	var offset := maxi(0, int(params.get("offset", 0)))
	var limit := clampi(int(params.get("limit", 100)), 1, MAX_DESCRIPTION_ITEMS)
	var items: Array[Dictionary] = []
	match section:
		"properties":
			items = _property_descriptors(type_name)
		"methods":
			items = _method_descriptors(type_name)
		"signals":
			items = _signal_descriptors(type_name)
		"enums":
			items = _enum_descriptors(type_name)
	var page := _page(items, offset, limit)
	return {
		"name": String(type_name),
		"kind": kind,
		"category": TypePolicy.coverage_category(type_name, kind),
		"parent": String(ClassDB.get_parent_class(type_name)),
		"inheritance": _inheritance(type_name),
		"instantiable": ClassDB.can_instantiate(type_name),
		"api_type": _api_type_name(ClassDB.class_get_api_type(type_name)),
		"section": section,
		"items": page["items"],
		"total": items.size(),
		"offset": page["offset"],
		"limit": limit,
		"has_more": page["has_more"],
		"available_sections": DESCRIPTION_SECTIONS.keys(),
	}


func _property_descriptors(type_name: StringName) -> Array[Dictionary]:
	var descriptors: Array[Dictionary] = []
	for property_info_value in ClassDB.class_get_property_list(type_name):
		var property_info: Dictionary = property_info_value
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if not _is_public_property(usage):
			continue
		var property_name := StringName(str(property_info.get("name", "")))
		if String(property_name).is_empty():
			continue
		var descriptor := _property_descriptor(property_info)
		descriptor["read_only"] = (usage & PROPERTY_USAGE_READ_ONLY) != 0
		descriptor["getter"] = String(ClassDB.class_get_property_getter(type_name, property_name))
		descriptor["setter"] = String(ClassDB.class_get_property_setter(type_name, property_name))
		descriptors.append(descriptor)
	descriptors.sort_custom(func(left: Dictionary, right: Dictionary) -> bool: return left["name"] < right["name"])
	return descriptors


func _method_descriptors(type_name: StringName) -> Array[Dictionary]:
	var descriptors: Array[Dictionary] = []
	for method_info_value in ClassDB.class_get_method_list(type_name):
		var method_info: Dictionary = method_info_value
		var method_name := str(method_info.get("name", ""))
		if method_name.is_empty():
			continue
		var arguments: Array[Dictionary] = []
		var raw_arguments = method_info.get("args", [])
		if raw_arguments is Array:
			for argument_info_value in raw_arguments:
				arguments.append(_property_descriptor(argument_info_value))
		var default_arguments := method_info.get("default_args", [])
		descriptors.append(
			{
				"name": method_name,
				"arguments": arguments,
				"default_argument_count": default_arguments.size() if default_arguments is Array else 0,
				"return": _property_descriptor(method_info.get("return", {})),
				"flags": int(method_info.get("flags", 0)),
			}
		)
	descriptors.sort_custom(func(left: Dictionary, right: Dictionary) -> bool: return left["name"] < right["name"])
	return descriptors


func _signal_descriptors(type_name: StringName) -> Array[Dictionary]:
	var descriptors: Array[Dictionary] = []
	for signal_info_value in ClassDB.class_get_signal_list(type_name):
		var signal_info: Dictionary = signal_info_value
		var signal_name := str(signal_info.get("name", ""))
		if signal_name.is_empty():
			continue
		var arguments: Array[Dictionary] = []
		var raw_arguments = signal_info.get("args", [])
		if raw_arguments is Array:
			for argument_info_value in raw_arguments:
				arguments.append(_property_descriptor(argument_info_value))
		var default_arguments := signal_info.get("default_args", [])
		descriptors.append(
			{
				"name": signal_name,
				"arguments": arguments,
				"default_argument_count": default_arguments.size() if default_arguments is Array else 0,
				"flags": int(signal_info.get("flags", 0)),
			}
		)
	descriptors.sort_custom(func(left: Dictionary, right: Dictionary) -> bool: return left["name"] < right["name"])
	return descriptors


func _enum_descriptors(type_name: StringName) -> Array[Dictionary]:
	var descriptors: Array[Dictionary] = []
	for enum_name_value in ClassDB.class_get_enum_list(type_name):
		var enum_name := StringName(enum_name_value)
		var values: Array[Dictionary] = []
		for constant_name_value in ClassDB.class_get_enum_constants(type_name, enum_name):
			var constant_name := StringName(constant_name_value)
			values.append(
				{
					"name": String(constant_name),
					"value": ClassDB.class_get_integer_constant(type_name, constant_name),
				}
			)
		values.sort_custom(func(left: Dictionary, right: Dictionary) -> bool: return left["name"] < right["name"])
		descriptors.append({"name": String(enum_name), "values": values})
	descriptors.sort_custom(func(left: Dictionary, right: Dictionary) -> bool: return left["name"] < right["name"])
	return descriptors


func _property_descriptor(property_info_value: Variant) -> Dictionary:
	var property_info: Dictionary = property_info_value if property_info_value is Dictionary else {}
	return {
		"name": str(property_info.get("name", "")),
		"type": type_string(int(property_info.get("type", TYPE_NIL))),
		"class_name": str(property_info.get("class_name", "")),
		"hint": int(property_info.get("hint", PROPERTY_HINT_NONE)),
		"hint_string": str(property_info.get("hint_string", "")),
	}


func _inheritance(type_name: StringName) -> Array[String]:
	var chain: Array[String] = []
	var current := type_name
	while not current.is_empty() and ClassDB.class_exists(current):
		chain.append(String(current))
		current = ClassDB.get_parent_class(current)
	return chain


func _api_type_name(api_type: int) -> String:
	match api_type:
		ClassDB.API_CORE:
			return "core"
		ClassDB.API_EDITOR:
			return "editor"
		ClassDB.API_EXTENSION:
			return "extension"
		ClassDB.API_EDITOR_EXTENSION:
			return "editor_extension"
	return "none"


func _is_public_property(usage: int) -> bool:
	return (usage & (PROPERTY_USAGE_EDITOR | PROPERTY_USAGE_STORAGE)) != 0


func _page(items: Array[Dictionary], offset: int, limit: int) -> Dictionary:
	var start := mini(offset, items.size())
	var end := mini(start + limit, items.size())
	var page: Array[Dictionary] = []
	if start < items.size():
		page.assign(items.slice(start, end))
	return {"items": page, "offset": start, "has_more": end < items.size()}
