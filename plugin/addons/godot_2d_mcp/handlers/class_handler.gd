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
