@tool
extends RefCounted

const TypePolicy := preload("res://addons/godot_2d_mcp/utils/type_policy.gd")


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
