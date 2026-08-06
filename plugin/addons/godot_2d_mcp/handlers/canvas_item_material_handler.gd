@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")

const MATERIAL_PROPERTIES := [
	"blend_mode", "light_mode", "particles_animation", "particles_anim_h_frames",
	"particles_anim_v_frames", "particles_anim_loop",
]
const BLEND_MODES := {
	"mix": CanvasItemMaterial.BLEND_MODE_MIX,
	"add": CanvasItemMaterial.BLEND_MODE_ADD,
	"subtract": CanvasItemMaterial.BLEND_MODE_SUB,
	"multiply": CanvasItemMaterial.BLEND_MODE_MUL,
	"premultiplied_alpha": CanvasItemMaterial.BLEND_MODE_PREMULT_ALPHA,
}
const LIGHT_MODES := {
	"normal": CanvasItemMaterial.LIGHT_MODE_NORMAL,
	"unshaded": CanvasItemMaterial.LIGHT_MODE_UNSHADED,
	"light_only": CanvasItemMaterial.LIGHT_MODE_LIGHT_ONLY,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_canvas_item_material(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params, false)
	if resolved.has("_error"):
		return resolved
	return _response(resolved["canvas_item"], resolved["scene_root"])


func create_canvas_item_material(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var replace_result := _parse_replace_existing(params)
	if replace_result.has("_error"):
		return replace_result
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var old_material: Material = canvas_item.material
	if old_material != null and not replace_result["replace_existing"]:
		return Errors.make(
			"CANVAS_ITEM_MATERIAL_ALREADY_ASSIGNED",
			"CanvasItem '%s' already has a %s material" % [canvas_item.name, old_material.get_class()],
			false,
			"Inspect it first or pass replace_existing: true to replace it with an embedded CanvasItemMaterial."
		)
	var replacement := CanvasItemMaterial.new()
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		replacement,
		"Create CanvasItemMaterial on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["created"] = true
	result["replaced_existing"] = old_material != null
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func bind_canvas_item_material(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var resource_result := _load_canvas_item_material(params.get("resource_path", null))
	if resource_result.has("_error"):
		return resource_result
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var replacement: CanvasItemMaterial = resource_result["material"]
	if canvas_item.material == replacement:
		return _unchanged_response(_response(canvas_item, resolved["scene_root"]))
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		replacement,
		"Bind CanvasItemMaterial on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["changed"] = true
	result["bound_external_resource"] = not replacement.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_canvas_item_material(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var current := canvas_item.material as CanvasItemMaterial
	if current == null:
		return Errors.make(
			"CANVAS_ITEM_MATERIAL_REQUIRED",
			"CanvasItem '%s' has no assigned CanvasItemMaterial" % canvas_item.name,
			false,
			"Call canvas_item_material_create or canvas_item_material_bind first."
		)
	var parsed := _parse_updates(params.get("properties", null))
	if parsed.has("_error"):
		return parsed
	var duplicate_result := _duplicate_material(current)
	if duplicate_result.has("_error"):
		return duplicate_result
	var replacement: CanvasItemMaterial = duplicate_result["material"]
	for property_name_value in parsed["updates"]:
		var property_name := str(property_name_value)
		replacement.set(property_name, parsed["updates"][property_name_value])
	if _configuration_matches(current, replacement):
		return _unchanged_response(_response(canvas_item, resolved["scene_root"]))
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		replacement,
		"Update CanvasItemMaterial on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["changed"] = true
	result["copied_external_material"] = not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_canvas_item_material(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var old_material: Material = canvas_item.material
	if old_material == null:
		return Errors.make(
			"CANVAS_ITEM_MATERIAL_NOT_ASSIGNED",
			"CanvasItem '%s' has no material to clear" % canvas_item.name,
			false,
			"Call canvas_item_material_get to inspect the current material."
		)
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		null,
		"Clear CanvasItem material on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["cleared"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_canvas_item(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	if not node is CanvasItem:
		return Errors.make(
			"CANVAS_ITEM_REQUIRED",
			"Node '%s' is %s, not a CanvasItem" % [node.name, node.get_class()],
			false,
			"Target a 2D CanvasItem such as Node2D, Control, Sprite2D, or Polygon2D."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit node '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	return {"canvas_item": node as CanvasItem, "scene_root": scene_root}


func _parse_replace_existing(params: Dictionary) -> Dictionary:
	var raw_value: Variant = params.get("replace_existing", false)
	if not raw_value is bool:
		return Errors.make("INVALID_CANVAS_ITEM_MATERIAL", "replace_existing must be a boolean")
	return {"replace_existing": raw_value}


func _parse_updates(raw_properties: Variant) -> Dictionary:
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MATERIAL_PROPERTIES.size():
		return Errors.make(
			"INVALID_CANVAS_ITEM_MATERIAL_PROPERTIES",
			"properties must be a non-empty object containing at most %d entries" % MATERIAL_PROPERTIES.size()
		)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not MATERIAL_PROPERTIES.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_CANVAS_ITEM_MATERIAL_PROPERTY",
				"Unsupported CanvasItemMaterial property: %s" % str(raw_name),
				false,
				"Call canvas_item_material_get to inspect supported_properties."
			)
		var property_name: String = raw_name
		var value_result := _parse_property_value(property_name, raw_properties[raw_name])
		if value_result.has("_error"):
			return value_result
		updates[property_name] = value_result["value"]
	return {"updates": updates}


func _parse_property_value(property_name: String, raw_value: Variant) -> Dictionary:
	if property_name == "blend_mode":
		return _parse_enum(raw_value, property_name, BLEND_MODES)
	if property_name == "light_mode":
		return _parse_enum(raw_value, property_name, LIGHT_MODES)
	if property_name in ["particles_animation", "particles_anim_loop"]:
		if not raw_value is bool:
			return Errors.make("INVALID_CANVAS_ITEM_MATERIAL_CONFIGURATION", "%s must be a boolean" % property_name)
		return {"value": raw_value}
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)) or float(raw_value) != floorf(float(raw_value)):
		return Errors.make("INVALID_CANVAS_ITEM_MATERIAL_CONFIGURATION", "%s must be an integer" % property_name)
	var value := int(raw_value)
	if value < 1 or value > 128:
		return Errors.make("INVALID_CANVAS_ITEM_MATERIAL_CONFIGURATION", "%s must be between 1 and 128" % property_name)
	return {"value": value}


func _parse_enum(raw_value: Variant, property_name: String, options: Dictionary) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CANVAS_ITEM_MATERIAL_CONFIGURATION", "%s must name a supported mode" % property_name)
	var label: String = raw_value.strip_edges().to_lower()
	if not options.has(label):
		return Errors.make(
			"INVALID_CANVAS_ITEM_MATERIAL_CONFIGURATION",
			"%s must be one of: %s" % [property_name, ", ".join(options.keys())]
		)
	return {"value": options[label]}


func _load_canvas_item_material(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CANVAS_ITEM_MATERIAL_PATH", "resource_path must be a res:// path")
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty() or not resource_path.begins_with("res://") or "/../" in resource_path or resource_path.ends_with("/.."):
		return Errors.make("INVALID_CANVAS_ITEM_MATERIAL_PATH", "resource_path must stay inside res://")
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "resource_path does not exist: %s" % resource_path)
	var resource := ResourceLoader.load(resource_path)
	if not resource is CanvasItemMaterial:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "resource_path does not load a CanvasItemMaterial resource")
	return {"material": resource as CanvasItemMaterial}


func _duplicate_material(current: CanvasItemMaterial) -> Dictionary:
	var duplicated := current.duplicate(true)
	if not duplicated is CanvasItemMaterial:
		return Errors.make("CANVAS_ITEM_MATERIAL_DUPLICATE_FAILED", "Unable to duplicate the current CanvasItemMaterial safely")
	return {"material": duplicated as CanvasItemMaterial}


func _commit_material_replacement(canvas_item: CanvasItem, scene_root: Node, replacement: Material, action_name: String) -> void:
	var old_material: Material = canvas_item.material
	_undo_redo.create_action("Godot 2D MCP: %s" % action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	_undo_redo.add_do_property(canvas_item, "material", replacement)
	if replacement != null:
		_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_property(canvas_item, "material", old_material)
	if old_material != null:
		_undo_redo.add_undo_reference(old_material)
	_undo_redo.commit_action()


func _response(canvas_item: CanvasItem, scene_root: Node) -> Dictionary:
	var material: Material = canvas_item.material
	var canvas_material := material as CanvasItemMaterial
	return {
		"path": ScenePath.from_node(canvas_item, scene_root),
		"type": canvas_item.get_class(),
		"material": _resource_info(material),
		"configuration": null if canvas_material == null else _serialize_configuration(canvas_material),
		"supported_properties": MATERIAL_PROPERTIES if canvas_material == null else MATERIAL_PROPERTIES.duplicate(),
		"blend_modes": BLEND_MODES.keys(),
		"light_modes": LIGHT_MODES.keys(),
	}


func _resource_info(resource: Resource) -> Dictionary:
	return {
		"assigned": resource != null,
		"type": "" if resource == null else resource.get_class(),
		"resource_path": "" if resource == null else resource.resource_path,
		"origin": "none" if resource == null else ("external" if not resource.resource_path.is_empty() else "embedded"),
		"is_canvas_item_material": resource is CanvasItemMaterial,
	}


func _serialize_configuration(material: CanvasItemMaterial) -> Dictionary:
	return {
		"blend_mode": _enum_name(BLEND_MODES, material.blend_mode),
		"light_mode": _enum_name(LIGHT_MODES, material.light_mode),
		"particles_animation": material.particles_animation,
		"particles_anim_h_frames": material.particles_anim_h_frames,
		"particles_anim_v_frames": material.particles_anim_v_frames,
		"particles_anim_loop": material.particles_anim_loop,
	}


func _configuration_matches(first: CanvasItemMaterial, second: CanvasItemMaterial) -> bool:
	return _serialize_configuration(first) == _serialize_configuration(second)


func _enum_name(options: Dictionary, value: int) -> String:
	for name in options:
		if options[name] == value:
			return name
	return ""


func _unchanged_response(response: Dictionary) -> Dictionary:
	response["changed"] = false
	response["undoable"] = false
	return response
