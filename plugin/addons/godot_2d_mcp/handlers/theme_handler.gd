@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_THEME_ITEMS := 256
const MAX_STYLEBOX_PROPERTIES := 48
const MAX_FONT_FAMILIES := 8
const MAX_NAME_LENGTH := 256
const MAX_FONT_SIZE := 4096
const MIN_BASE_SCALE := 0.01
const MAX_BASE_SCALE := 100.0
const PROTECTED_STYLEBOX_PROPERTIES := {
	"resource_path": true,
	"resource_name": true,
	"script": true,
}
const ITEM_KIND_BY_NAME := {
	"color": true,
	"constant": true,
	"font_size": true,
	"font": true,
	"icon": true,
	"stylebox_flat": true,
}
const DEFAULT_NAMES := {
	"font": true,
	"font_size": true,
	"base_scale": true,
}
const ITEM_GROUPS := [
	{
		"key": "colors",
		"kind": "color",
		"type_list": "get_color_type_list",
		"name_list": "get_color_list",
		"getter": "get_color",
	},
	{
		"key": "constants",
		"kind": "constant",
		"type_list": "get_constant_type_list",
		"name_list": "get_constant_list",
		"getter": "get_constant",
	},
	{
		"key": "font_sizes",
		"kind": "font_size",
		"type_list": "get_font_size_type_list",
		"name_list": "get_font_size_list",
		"getter": "get_font_size",
	},
	{
		"key": "fonts",
		"kind": "font",
		"type_list": "get_font_type_list",
		"name_list": "get_font_list",
		"getter": "get_font",
	},
	{
		"key": "icons",
		"kind": "icon",
		"type_list": "get_icon_type_list",
		"name_list": "get_icon_list",
		"getter": "get_icon",
	},
	{
		"key": "styleboxes",
		"kind": "stylebox_flat",
		"type_list": "get_stylebox_type_list",
		"name_list": "get_stylebox_list",
		"getter": "get_stylebox",
	},
]

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_theme(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params, false)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	return {
		"path": ScenePath.from_node(control, scene_root),
		"type": control.get_class(),
		"theme": _serialize_theme(control.theme),
	}


func create_theme(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params)
	if resolved.has("_error"):
		return resolved
	var resource_name_result := _parse_optional_resource_name(params.get("resource_name", ""))
	if resource_name_result.has("_error"):
		return resource_name_result
	var replace_result := _parse_bool(params.get("replace", false), "replace")
	if replace_result.has("_error"):
		return replace_result
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	var old_theme: Theme = control.theme
	if old_theme != null and not replace_result["value"]:
		return Errors.make(
			"THEME_ALREADY_ASSIGNED",
			"Control '%s' already has a Theme assigned" % control.name,
			false,
			"Call control_theme_get to inspect it, or pass replace=true to replace only this Control's assignment."
		)
	var replacement := Theme.new()
	replacement.resource_name = resource_name_result["value"]
	_undo_redo.create_action(
		"Godot 2D MCP: Create Theme for %s" % control.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_undo_redo.add_do_method(control, "set_theme", replacement)
	_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_method(control, "set_theme", old_theme)
	if old_theme != null:
		_undo_redo.add_undo_reference(old_theme)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"replaced": old_theme != null,
		"theme": _serialize_theme(replacement),
		"undoable": true,
		"_scene_mutated": true,
	}


func assign_theme(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params)
	if resolved.has("_error"):
		return resolved
	var theme_result := _load_theme_path(params.get("theme_path", ""), true)
	if theme_result.has("_error"):
		return theme_result
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	var old_theme: Theme = control.theme
	var replacement: Theme = theme_result["theme"]
	if old_theme == replacement:
		return {
			"path": ScenePath.from_node(control, scene_root),
			"changed": false,
			"theme": _serialize_theme(replacement),
			"undoable": false,
		}
	_undo_redo.create_action(
		"Godot 2D MCP: Assign Theme for %s" % control.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_undo_redo.add_do_method(control, "set_theme", replacement)
	if replacement != null:
		_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_method(control, "set_theme", old_theme)
	if old_theme != null:
		_undo_redo.add_undo_reference(old_theme)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"changed": true,
		"theme": _serialize_theme(replacement),
		"undoable": true,
		"_scene_mutated": true,
	}


func set_defaults(params: Dictionary) -> Dictionary:
	var resolved := _resolve_embedded_theme(params)
	if resolved.has("_error"):
		return resolved
	var parsed := _parse_default_updates(params)
	if parsed.has("_error"):
		return parsed
	var theme: Theme = resolved["theme"]
	var scene_root: Node = resolved["scene_root"]
	var control: Control = resolved["control"]
	var changes: Array[Dictionary] = parsed["changes"]
	for change in changes:
		change["had_old"] = _has_default_value(theme, change["name"])
		change["old"] = _get_default_value(theme, change["name"])
	_undo_redo.create_action(
		"Godot 2D MCP: Update Theme defaults for %s" % control.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	for change in changes:
		_add_default_state_operation(theme, change["name"], true, change["value"], true)
		_add_default_state_operation(
			theme, change["name"], change["had_old"], change["old"], false
		)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"theme": _serialize_theme(theme),
		"updated": parsed["names"],
		"undoable": true,
		"_scene_mutated": true,
	}


func clear_defaults(params: Dictionary) -> Dictionary:
	var resolved := _resolve_embedded_theme(params)
	if resolved.has("_error"):
		return resolved
	var names_result := _parse_default_names(params.get("defaults", []))
	if names_result.has("_error"):
		return names_result
	var theme: Theme = resolved["theme"]
	var scene_root: Node = resolved["scene_root"]
	var control: Control = resolved["control"]
	var changes: Array[Dictionary] = []
	for name in names_result["names"]:
		var old_value := _get_default_value(theme, name)
		var had_value := _has_default_value(theme, name)
		if had_value:
			changes.append({"name": name, "value": null, "had_old": true, "old": old_value})
	if changes.is_empty():
		return {
			"path": ScenePath.from_node(control, scene_root),
			"changed": false,
			"theme": _serialize_theme(theme),
			"undoable": false,
		}
	_undo_redo.create_action(
		"Godot 2D MCP: Clear Theme defaults for %s" % control.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	for change in changes:
		_add_default_state_operation(theme, change["name"], false, null, true)
		_add_default_state_operation(
			theme, change["name"], change["had_old"], change["old"], false
		)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"changed": true,
		"cleared": names_result["names"],
		"theme": _serialize_theme(theme),
		"undoable": true,
		"_scene_mutated": true,
	}


func upsert_item(params: Dictionary) -> Dictionary:
	var resolved := _resolve_embedded_theme(params)
	if resolved.has("_error"):
		return resolved
	var item_result := _parse_theme_item(params, resolved["theme"])
	if item_result.has("_error"):
		return item_result
	var theme: Theme = resolved["theme"]
	var scene_root: Node = resolved["scene_root"]
	var control: Control = resolved["control"]
	var item: Dictionary = item_result["item"]
	var old := _theme_item_state(theme, item["kind"], item["name"], item["theme_type"])
	_undo_redo.create_action(
		"Godot 2D MCP: Set Theme %s %s/%s" % [item["kind"], item["theme_type"], item["name"]],
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_add_theme_item_operation(theme, item, true)
	_add_theme_item_operation(theme, old, false)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"item": _serialize_item(item),
		"replaced": old["exists"],
		"undoable": true,
		"_scene_mutated": true,
	}


func clear_item(params: Dictionary) -> Dictionary:
	var resolved := _resolve_embedded_theme(params)
	if resolved.has("_error"):
		return resolved
	var identity_result := _parse_item_identity(params)
	if identity_result.has("_error"):
		return identity_result
	var theme: Theme = resolved["theme"]
	var scene_root: Node = resolved["scene_root"]
	var control: Control = resolved["control"]
	var old := _theme_item_state(
		theme, identity_result["kind"], identity_result["name"], identity_result["theme_type"]
	)
	if not old["exists"]:
		return Errors.make(
			"THEME_ITEM_NOT_FOUND",
			"Theme has no local %s item '%s' for %s" % [
				identity_result["kind"], identity_result["name"], identity_result["theme_type"]
			],
			false,
			"Call control_theme_get to inspect local Theme items."
		)
	var clear_item := identity_result.duplicate()
	clear_item["exists"] = false
	clear_item["value"] = null
	_undo_redo.create_action(
		"Godot 2D MCP: Clear Theme %s %s/%s" % [
			identity_result["kind"], identity_result["theme_type"], identity_result["name"]
		],
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_add_theme_item_operation(theme, clear_item, true)
	_add_theme_item_operation(theme, old, false)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"item_type": identity_result["kind"],
		"theme_type": identity_result["theme_type"],
		"name": identity_result["name"],
		"undoable": true,
		"_scene_mutated": true,
	}


func _resolve_control(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
			"Control not found: %s" % path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not node is Control:
		return Errors.make(
			"CONTROL_REQUIRED",
			"Node '%s' is %s, not a Control" % [node.name, node.get_class()],
			false,
			"Choose a Control-derived UI node."
		)
	var control: Control = node
	if require_writable and control != scene_root and control.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit Control '%s' because it belongs to an instanced scene" % control.name,
			false,
			"Edit the source PackedScene or target a locally owned Control."
		)
	return {"control": control, "scene_root": scene_root}


func _resolve_embedded_theme(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var theme: Theme = control.theme
	if theme == null:
		return Errors.make(
			"THEME_NOT_ASSIGNED",
			"Control '%s' has no local Theme assigned" % control.name,
			false,
			"Call control_theme_create before editing Theme entries."
		)
	if not theme.is_built_in() or not theme.resource_path.is_empty():
		return Errors.make(
			"EXTERNAL_THEME_READ_ONLY",
			"Theme '%s' is external and cannot be modified through scene undo/redo" % theme.resource_path,
			false,
			"Assign or create an embedded Theme before editing it."
		)
	resolved["theme"] = theme
	return resolved


func _load_theme_path(raw_path: Variant, allow_empty: bool) -> Dictionary:
	if not raw_path is String:
		return Errors.make("INVALID_RESOURCE_PATH", "theme_path must be a res:// path or an empty string")
	var path: String = raw_path.strip_edges()
	if path.is_empty():
		if allow_empty:
			return {"theme": null}
		return Errors.make("MISSING_PARAMETER", "theme_path is required")
	var resource_result := _load_project_resource(path, "Theme")
	if resource_result.has("_error"):
		return resource_result
	if not resource_result["resource"] is Theme:
		return Errors.make(
			"RESOURCE_TYPE_MISMATCH",
			"Resource '%s' is %s, not Theme" % [path, resource_result["resource"].get_class()]
		)
	return {"theme": resource_result["resource"] as Theme}


func _parse_default_updates(params: Dictionary) -> Dictionary:
	var changes: Array[Dictionary] = []
	var names: Array[String] = []
	if params.has("font") and params["font"] != null:
		var font_result := _parse_font_value(params["font"])
		if font_result.has("_error"):
			return font_result
		changes.append({"name": "font", "value": font_result["value"]})
		names.append("font")
	if params.has("font_size") and params["font_size"] != null:
		var size_result := _parse_font_size(params["font_size"])
		if size_result.has("_error"):
			return size_result
		changes.append({"name": "font_size", "value": size_result["value"]})
		names.append("font_size")
	if params.has("base_scale") and params["base_scale"] != null:
		var scale_result := _parse_base_scale(params["base_scale"])
		if scale_result.has("_error"):
			return scale_result
		changes.append({"name": "base_scale", "value": scale_result["value"]})
		names.append("base_scale")
	if changes.is_empty():
		return Errors.make("MISSING_PARAMETER", "font, font_size, or base_scale must be supplied")
	return {"changes": changes, "names": names}


func _parse_default_names(raw_names: Variant) -> Dictionary:
	if not raw_names is Array or raw_names.is_empty() or raw_names.size() > DEFAULT_NAMES.size():
		return Errors.make("INVALID_THEME_DEFAULTS", "defaults must contain one or more default names")
	var names: Array[String] = []
	for raw_name in raw_names:
		if not raw_name is String:
			return Errors.make("INVALID_THEME_DEFAULTS", "default names must be strings")
		var name: String = raw_name.to_lower().strip_edges()
		if not DEFAULT_NAMES.has(name) or names.has(name):
			return Errors.make("INVALID_THEME_DEFAULTS", "defaults contains an unsupported or duplicate name")
		names.append(name)
	return {"names": names}


func _add_default_state_operation(
	theme: Theme, name: String, exists: bool, value: Variant, is_do: bool
) -> void:
	var prefix := "add_do_" if is_do else "add_undo_"
	var set_method := ""
	var clear_value: Variant = null
	match name:
		"font":
			set_method = "set_default_font"
		"font_size":
			set_method = "set_default_font_size"
			clear_value = 0
		"base_scale":
			set_method = "set_default_base_scale"
			clear_value = 0.0
	var applied_value := value if exists else clear_value
	_undo_redo.call(prefix + "method", theme, set_method, applied_value)
	if applied_value is Resource:
		_undo_redo.call(prefix + "reference", applied_value)


func _has_default_value(theme: Theme, name: String) -> bool:
	match name:
		"font":
			return theme.has_default_font()
		"font_size":
			return theme.has_default_font_size()
		"base_scale":
			return theme.has_default_base_scale()
	return false


func _get_default_value(theme: Theme, name: String) -> Variant:
	match name:
		"font":
			return theme.get_default_font()
		"font_size":
			return theme.get_default_font_size()
		"base_scale":
			return theme.get_default_base_scale()
	return null


func _parse_theme_item(params: Dictionary, theme: Theme) -> Dictionary:
	var identity_result := _parse_item_identity(params)
	if identity_result.has("_error"):
		return identity_result
	if not params.has("value"):
		return Errors.make("MISSING_PARAMETER", "value is required")
	var item := identity_result.duplicate()
	var kind: String = item["kind"]
	var raw_value: Variant = params["value"]
	match kind:
		"color":
			var color_result := _parse_color(raw_value)
			if color_result.has("_error"):
				return color_result
			item["value"] = color_result["value"]
		"constant":
			var constant_result := _parse_constant(raw_value)
			if constant_result.has("_error"):
				return constant_result
			item["value"] = constant_result["value"]
		"font_size":
			var size_result := _parse_font_size(raw_value)
			if size_result.has("_error"):
				return size_result
			item["value"] = size_result["value"]
		"font":
			var font_result := _parse_font_value(raw_value)
			if font_result.has("_error"):
				return font_result
			item["value"] = font_result["value"]
		"icon":
			var icon_result := _parse_icon_value(raw_value)
			if icon_result.has("_error"):
				return icon_result
			item["value"] = icon_result["value"]
		"stylebox_flat":
			var style_result := _parse_stylebox_flat(raw_value, theme, item)
			if style_result.has("_error"):
				return style_result
			item["value"] = style_result["value"]
	item["exists"] = true
	return {"item": item}


func _parse_item_identity(params: Dictionary) -> Dictionary:
	var raw_kind := params.get("item_type", "")
	if not raw_kind is String:
		return Errors.make("INVALID_THEME_ITEM", "item_type must be a supported Theme item name")
	var kind: String = raw_kind.to_lower().strip_edges()
	if not ITEM_KIND_BY_NAME.has(kind):
		return Errors.make("INVALID_THEME_ITEM", "item_type is not supported")
	var type_result := _parse_theme_name(params.get("theme_type", ""), "theme_type")
	if type_result.has("_error"):
		return type_result
	var name_result := _parse_theme_name(params.get("name", ""), "name")
	if name_result.has("_error"):
		return name_result
	return {"kind": kind, "theme_type": type_result["value"], "name": name_result["value"]}


func _parse_theme_name(raw_value: Variant, label: String) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_THEME_ITEM", "%s must be a non-empty Theme identifier" % label)
	var value: String = raw_value.strip_edges()
	if value.is_empty() or value.length() > MAX_NAME_LENGTH or "/" in value or ":" in value:
		return Errors.make("INVALID_THEME_ITEM", "%s must be a non-empty Theme identifier" % label)
	return {"value": value}


func _parse_color(raw_value: Variant) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_COLOR}, Color.WHITE)
	if decoded.has("_error"):
		return Errors.make("THEME_VALUE_TYPE_MISMATCH", decoded["_error"]["message"])
	return {"value": decoded["value"]}


func _parse_constant(raw_value: Variant) -> Dictionary:
	if not _is_integral_number(raw_value) or abs(int(raw_value)) > 1000000:
		return Errors.make("THEME_VALUE_TYPE_MISMATCH", "constant must be an integer between -1000000 and 1000000")
	return {"value": int(raw_value)}


func _parse_font_size(raw_value: Variant) -> Dictionary:
	if not _is_integral_number(raw_value) or int(raw_value) < 1 or int(raw_value) > MAX_FONT_SIZE:
		return Errors.make("THEME_VALUE_TYPE_MISMATCH", "font_size must be an integer between 1 and %d" % MAX_FONT_SIZE)
	return {"value": int(raw_value)}


func _parse_base_scale(raw_value: Variant) -> Dictionary:
	if not _is_finite_number(raw_value):
		return Errors.make("THEME_VALUE_TYPE_MISMATCH", "base_scale must be a finite number")
	var value := float(raw_value)
	if value < MIN_BASE_SCALE or value > MAX_BASE_SCALE:
		return Errors.make("THEME_VALUE_TYPE_MISMATCH", "base_scale must be between %s and %s" % [MIN_BASE_SCALE, MAX_BASE_SCALE])
	return {"value": value}


func _parse_font_value(raw_value: Variant) -> Dictionary:
	if not raw_value is Dictionary:
		return Errors.make("THEME_VALUE_TYPE_MISMATCH", "font must be a {source, ...} object")
	var source: String = str(raw_value.get("source", "")).to_lower().strip_edges()
	if source == "path":
		if raw_value.size() != 2 or not raw_value.has("path"):
			return Errors.make("THEME_VALUE_TYPE_MISMATCH", "path fonts require exactly source and path")
		var resource_result := _load_project_resource(raw_value["path"], "Font")
		if resource_result.has("_error"):
			return resource_result
		if not resource_result["resource"] is Font:
			return Errors.make("RESOURCE_TYPE_MISMATCH", "Font path must resolve to a Font resource")
		return {"value": resource_result["resource"] as Font}
	if source == "system":
		if raw_value.size() != 2 or not raw_value.has("families"):
			return Errors.make("THEME_VALUE_TYPE_MISMATCH", "system fonts require exactly source and families")
		if not raw_value["families"] is Array or raw_value["families"].is_empty() or raw_value["families"].size() > MAX_FONT_FAMILIES:
			return Errors.make("THEME_VALUE_TYPE_MISMATCH", "families must contain 1 to %d font family names" % MAX_FONT_FAMILIES)
		var families := PackedStringArray()
		for raw_family in raw_value["families"]:
			if not raw_family is String or raw_family.strip_edges().is_empty() or raw_family.length() > MAX_NAME_LENGTH:
				return Errors.make("THEME_VALUE_TYPE_MISMATCH", "font family names must be non-empty strings")
			families.append(raw_family.strip_edges())
		var system_font := SystemFont.new()
		system_font.font_names = families
		return {"value": system_font}
	return Errors.make("THEME_VALUE_TYPE_MISMATCH", "font.source must be path or system")


func _parse_icon_value(raw_value: Variant) -> Dictionary:
	var resource_result := _load_project_resource(raw_value, "Texture2D")
	if resource_result.has("_error"):
		return resource_result
	if not resource_result["resource"] is Texture2D:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "icon path must resolve to a Texture2D resource")
	return {"value": resource_result["resource"] as Texture2D}


func _parse_stylebox_flat(raw_value: Variant, theme: Theme, item: Dictionary) -> Dictionary:
	if not raw_value is Dictionary or raw_value.is_empty() or raw_value.size() > MAX_STYLEBOX_PROPERTIES:
		return Errors.make("THEME_VALUE_TYPE_MISMATCH", "stylebox_flat value must be a non-empty property object")
	var source: StyleBox = null
	if theme.has_stylebox(StringName(item["name"]), StringName(item["theme_type"])):
		source = theme.get_stylebox(StringName(item["name"]), StringName(item["theme_type"]))
	var stylebox: StyleBoxFlat
	if source is StyleBoxFlat:
		stylebox = source.duplicate(true) as StyleBoxFlat
	else:
		stylebox = StyleBoxFlat.new()
	var applied := _apply_stylebox_properties(stylebox, raw_value)
	if applied.has("_error"):
		return applied
	return {"value": stylebox}


func _load_project_resource(raw_path: Variant, expected_type: String) -> Dictionary:
	if not raw_path is String:
		return Errors.make("INVALID_RESOURCE_PATH", "%s path must be a res:// string" % expected_type)
	var path: String = raw_path.strip_edges()
	if path.is_empty() or not path.begins_with("res://") or "/../" in path or path.ends_with("/.."):
		return Errors.make("INVALID_RESOURCE_PATH", "%s path must stay inside res://" % expected_type)
	if not ResourceLoader.exists(path):
		return Errors.make("RESOURCE_NOT_FOUND", "%s resource does not exist: %s" % [expected_type, path])
	var resource := ResourceLoader.load(path)
	if resource == null:
		return Errors.make("RESOURCE_LOAD_FAILED", "Godot could not load resource: %s" % path)
	return {"resource": resource}


func _apply_stylebox_properties(stylebox: StyleBoxFlat, requested: Dictionary) -> Dictionary:
	var property_info_by_name := {}
	for property_info_value in stylebox.get_property_list():
		var property_info: Dictionary = property_info_value
		property_info_by_name[str(property_info.get("name", ""))] = property_info
	for property_name_value in requested:
		var property_name := str(property_name_value)
		if not property_info_by_name.has(property_name):
			return Errors.make("STYLEBOX_PROPERTY_NOT_FOUND", "StyleBoxFlat property '%s' does not exist" % property_name)
		var property_info: Dictionary = property_info_by_name[property_name]
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if PROTECTED_STYLEBOX_PROPERTIES.has(property_name) or not _is_writable_public_property(usage):
			return Errors.make("STYLEBOX_PROPERTY_NOT_WRITABLE", "StyleBoxFlat property '%s' is not writable" % property_name)
		var decoded := VariantCodec.decode(requested[property_name_value], property_info, stylebox.get(property_name))
		if decoded.has("_error"):
			return Errors.make("STYLEBOX_PROPERTY_TYPE_MISMATCH", decoded["_error"]["message"], false, "Use a compatible JSON value.", {"property": property_name})
		stylebox.set(property_name, decoded["value"])
	return {}


func _theme_item_state(theme: Theme, kind: String, name: String, theme_type: String) -> Dictionary:
	var exists := _has_theme_item(theme, kind, name, theme_type)
	return {
		"kind": kind,
		"name": name,
		"theme_type": theme_type,
		"exists": exists,
		"value": _get_theme_item(theme, kind, name, theme_type) if exists else null,
	}


func _has_theme_item(theme: Theme, kind: String, name: String, theme_type: String) -> bool:
	match kind:
		"color":
			return theme.has_color(StringName(name), StringName(theme_type))
		"constant":
			return theme.has_constant(StringName(name), StringName(theme_type))
		"font_size":
			return theme.has_font_size(StringName(name), StringName(theme_type))
		"font":
			return theme.has_font(StringName(name), StringName(theme_type))
		"icon":
			return theme.has_icon(StringName(name), StringName(theme_type))
		"stylebox_flat":
			return theme.has_stylebox(StringName(name), StringName(theme_type))
	return false


func _get_theme_item(theme: Theme, kind: String, name: String, theme_type: String) -> Variant:
	match kind:
		"color":
			return theme.get_color(StringName(name), StringName(theme_type))
		"constant":
			return theme.get_constant(StringName(name), StringName(theme_type))
		"font_size":
			return theme.get_font_size(StringName(name), StringName(theme_type))
		"font":
			return theme.get_font(StringName(name), StringName(theme_type))
		"icon":
			return theme.get_icon(StringName(name), StringName(theme_type))
		"stylebox_flat":
			return theme.get_stylebox(StringName(name), StringName(theme_type))
	return null


func _add_theme_item_operation(theme: Theme, item: Dictionary, is_do: bool) -> void:
	var prefix := "add_do_" if is_do else "add_undo_"
	var kind: String = item["kind"]
	var method := _theme_item_setter(kind) if item["exists"] else _theme_item_clearer(kind)
	if item["exists"]:
		_undo_redo.call(prefix + "method", theme, method, StringName(item["name"]), StringName(item["theme_type"]), item["value"])
		if item["value"] is Resource:
			_undo_redo.call(prefix + "reference", item["value"])
	else:
		_undo_redo.call(prefix + "method", theme, method, StringName(item["name"]), StringName(item["theme_type"]))


func _theme_item_setter(kind: String) -> String:
	match kind:
		"color":
			return "set_color"
		"constant":
			return "set_constant"
		"font_size":
			return "set_font_size"
		"font":
			return "set_font"
		"icon":
			return "set_icon"
		"stylebox_flat":
			return "set_stylebox"
	return ""


func _theme_item_clearer(kind: String) -> String:
	match kind:
		"color":
			return "clear_color"
		"constant":
			return "clear_constant"
		"font_size":
			return "clear_font_size"
		"font":
			return "clear_font"
		"icon":
			return "clear_icon"
		"stylebox_flat":
			return "clear_stylebox"
	return ""


func _serialize_theme(theme: Theme) -> Variant:
	if theme == null:
		return null
	var items_result := _serialize_theme_items(theme)
	return {
		"resource_type": theme.get_class(),
		"resource_path": theme.resource_path,
		"resource_name": theme.resource_name,
		"built_in": theme.is_built_in(),
		"editable": theme.is_built_in() and theme.resource_path.is_empty(),
		"defaults": {
			"font": _serialize_resource(theme.get_default_font()) if theme.has_default_font() else null,
			"font_size": theme.get_default_font_size() if theme.has_default_font_size() else null,
			"base_scale": theme.get_default_base_scale() if theme.has_default_base_scale() else null,
		},
		"items": items_result["items"],
		"item_count": items_result["count"],
		"items_truncated": items_result["truncated"],
	}


func _serialize_theme_items(theme: Theme) -> Dictionary:
	var result := {}
	for group in ITEM_GROUPS:
		result[group["key"]] = []
	var count := 0
	var truncated := false
	for group in ITEM_GROUPS:
		var type_names: Array[String] = []
		for raw_type in theme.call(group["type_list"]):
			type_names.append(str(raw_type))
		type_names.sort()
		for theme_type in type_names:
			var names: Array[String] = []
			for raw_name in theme.call(group["name_list"], StringName(theme_type)):
				names.append(str(raw_name))
			names.sort()
			for name in names:
				if count >= MAX_THEME_ITEMS:
					truncated = true
					break
				var value := theme.call(group["getter"], StringName(name), StringName(theme_type))
				result[group["key"]].append(
					_serialize_item({
						"kind": group["kind"],
						"theme_type": theme_type,
						"name": name,
						"value": value,
					})
				)
				count += 1
			if truncated:
				break
		if truncated:
			break
	return {"items": result, "count": count, "truncated": truncated}


func _serialize_item(item: Dictionary) -> Dictionary:
	return {
		"item_type": item["kind"],
		"theme_type": item["theme_type"],
		"name": item["name"],
		"value": _serialize_item_value(item["kind"], item["value"]),
	}


func _serialize_item_value(kind: String, value: Variant) -> Variant:
	if kind == "stylebox_flat" and value is StyleBoxFlat:
		return {
			"resource": _serialize_resource(value),
			"flat_properties": _serialize_flat_properties(value),
		}
	if value is Resource:
		return _serialize_resource(value)
	return VariantCodec.serialize(value)


func _serialize_resource(resource: Resource) -> Variant:
	if resource == null:
		return null
	return {
		"resource_type": resource.get_class(),
		"resource_path": resource.resource_path,
		"resource_name": resource.resource_name,
		"built_in": resource.is_built_in(),
	}


func _serialize_flat_properties(stylebox: StyleBoxFlat) -> Dictionary:
	var properties := {}
	for property_info_value in stylebox.get_property_list():
		var property_info: Dictionary = property_info_value
		var property_name := str(property_info.get("name", ""))
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if property_name.is_empty() or PROTECTED_STYLEBOX_PROPERTIES.has(property_name) or not _is_public_property(usage):
			continue
		properties[property_name] = VariantCodec.serialize(stylebox.get(property_name))
	return properties


func _parse_optional_resource_name(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_RESOURCE_NAME", "resource_name must be a string")
	var value: String = raw_value.strip_edges()
	if value.length() > MAX_NAME_LENGTH or "/" in value or ":" in value:
		return Errors.make("INVALID_RESOURCE_NAME", "resource_name is invalid")
	return {"value": value}


func _parse_bool(raw_value: Variant, label: String) -> Dictionary:
	if not raw_value is bool:
		return Errors.make("INVALID_PARAMETER", "%s must be a boolean" % label)
	return {"value": raw_value}


func _is_public_property(usage: int) -> bool:
	return bool(usage & (PROPERTY_USAGE_STORAGE | PROPERTY_USAGE_EDITOR))


func _is_writable_public_property(usage: int) -> bool:
	return _is_public_property(usage) and not bool(usage & PROPERTY_USAGE_READ_ONLY)


func _is_finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _is_integral_number(value: Variant) -> bool:
	return _is_finite_number(value) and is_equal_approx(float(value), round(float(value)))
