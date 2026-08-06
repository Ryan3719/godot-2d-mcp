@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const DEFAULT_SOURCE := "shader_type canvas_item;\n"
const MAX_SOURCE_LENGTH := 65536
const MAX_UNIFORM_UPDATES := 32
const SUPPORTED_SHADER_TYPE := "canvas_item"

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_canvas_item_shader(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params, false)
	if resolved.has("_error"):
		return resolved
	return _response(resolved["canvas_item"], resolved["scene_root"])


func create_canvas_item_shader(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var replace_result := _parse_replace_existing(params)
	if replace_result.has("_error"):
		return replace_result
	var source_result := _parse_source(params.get("source", DEFAULT_SOURCE))
	if source_result.has("_error"):
		return source_result
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var old_material: Material = canvas_item.material
	if old_material != null and not replace_result["replace_existing"]:
		return Errors.make(
			"CANVAS_ITEM_MATERIAL_ALREADY_ASSIGNED",
			"CanvasItem '%s' already has a %s material" % [canvas_item.name, old_material.get_class()],
			false,
			"Inspect it first or pass replace_existing: true to replace it with an embedded ShaderMaterial."
		)
	var shader_result := _make_canvas_item_shader(source_result["source"])
	if shader_result.has("_error"):
		return shader_result
	var replacement := ShaderMaterial.new()
	replacement.shader = shader_result["shader"]
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		replacement,
		"Create CanvasItem ShaderMaterial on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["created"] = true
	result["replaced_existing"] = old_material != null
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func bind_canvas_item_shader(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var material_result := _load_canvas_item_shader_material(params.get("resource_path", null))
	if material_result.has("_error"):
		return material_result
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var replacement: ShaderMaterial = material_result["material"]
	if canvas_item.material == replacement:
		return _unchanged_response(_response(canvas_item, resolved["scene_root"]))
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		replacement,
		"Bind CanvasItem ShaderMaterial on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["changed"] = true
	result["bound_external_resource"] = not replacement.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_canvas_item_shader(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var source_result := _parse_source(params.get("source", null))
	if source_result.has("_error"):
		return source_result
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var current := canvas_item.material as ShaderMaterial
	if current == null:
		return Errors.make(
			"CANVAS_ITEM_SHADER_MATERIAL_REQUIRED",
			"CanvasItem '%s' has no assigned ShaderMaterial" % canvas_item.name,
			false,
			"Call canvas_item_shader_create or canvas_item_shader_bind first."
		)
	var shader_result := _make_canvas_item_shader(source_result["source"])
	if shader_result.has("_error"):
		return shader_result
	var current_shader: Shader = current.shader
	if current_shader != null and current_shader.code == source_result["source"]:
		return _unchanged_response(_response(canvas_item, resolved["scene_root"]))
	var duplicate_result := _duplicate_material(current, shader_result["shader"])
	if duplicate_result.has("_error"):
		return duplicate_result
	var replacement: ShaderMaterial = duplicate_result["material"]
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		replacement,
		"Update CanvasItem ShaderMaterial on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["changed"] = true
	result["copied_external_material"] = not current.resource_path.is_empty()
	result["copied_external_shader"] = current_shader != null and not current_shader.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_canvas_item_shader_uniforms(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var material_result := _require_canvas_item_shader_material(canvas_item)
	if material_result.has("_error"):
		return material_result
	var current: ShaderMaterial = material_result["material"]
	var updates_result := _parse_uniform_updates(params.get("values", null), material_result["uniforms"])
	if updates_result.has("_error"):
		return updates_result
	var changes := {}
	for uniform_name_value in updates_result["updates"]:
		var uniform_name := str(uniform_name_value)
		var old_value = current.get_shader_parameter(uniform_name)
		var new_value = updates_result["updates"][uniform_name_value]
		if old_value != new_value:
			changes[uniform_name] = new_value
	if changes.is_empty():
		return _unchanged_response(_response(canvas_item, resolved["scene_root"]))
	var duplicate_result := _duplicate_material_preserving_shader(current)
	if duplicate_result.has("_error"):
		return duplicate_result
	var replacement: ShaderMaterial = duplicate_result["material"]
	for uniform_name_value in changes:
		var uniform_name := str(uniform_name_value)
		replacement.set_shader_parameter(uniform_name, changes[uniform_name_value])
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		replacement,
		"Update CanvasItem shader uniforms on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["changed"] = true
	result["updated_uniforms"] = _sorted_keys(changes)
	result["copied_external_material"] = not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_canvas_item_shader_uniforms(params: Dictionary) -> Dictionary:
	var resolved := _resolve_canvas_item(params)
	if resolved.has("_error"):
		return resolved
	var canvas_item: CanvasItem = resolved["canvas_item"]
	var material_result := _require_canvas_item_shader_material(canvas_item)
	if material_result.has("_error"):
		return material_result
	var current: ShaderMaterial = material_result["material"]
	var names_result := _parse_uniform_names(params.get("names", null), material_result["uniforms"])
	if names_result.has("_error"):
		return names_result
	var changed_names: Array[String] = []
	for name_value in names_result["names"]:
		var uniform_name := str(name_value)
		if current.get_shader_parameter(uniform_name) != null:
			changed_names.append(uniform_name)
	if changed_names.is_empty():
		return _unchanged_response(_response(canvas_item, resolved["scene_root"]))
	var duplicate_result := _duplicate_material_preserving_shader(current)
	if duplicate_result.has("_error"):
		return duplicate_result
	var replacement: ShaderMaterial = duplicate_result["material"]
	for uniform_name in changed_names:
		replacement.set_shader_parameter(uniform_name, null)
	_commit_material_replacement(
		canvas_item,
		resolved["scene_root"],
		replacement,
		"Clear CanvasItem shader uniforms on %s" % canvas_item.name
	)
	var result := _response(canvas_item, resolved["scene_root"])
	result["changed"] = true
	result["cleared_uniforms"] = changed_names
	result["copied_external_material"] = not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_canvas_item_shader(params: Dictionary) -> Dictionary:
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
			"Call canvas_item_shader_get to inspect the current material."
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
		return Errors.make("INVALID_CANVAS_ITEM_SHADER", "replace_existing must be a boolean")
	return {"replace_existing": raw_value}


func _parse_source(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CANVAS_ITEM_SHADER_SOURCE", "source must be a string")
	var source: String = raw_value
	if source.strip_edges().is_empty() or source.length() > MAX_SOURCE_LENGTH:
		return Errors.make(
			"INVALID_CANVAS_ITEM_SHADER_SOURCE",
			"source must contain between 1 and %d characters" % MAX_SOURCE_LENGTH
		)
	if "#include" in source:
		return Errors.make(
			"CANVAS_ITEM_SHADER_INCLUDE_UNSUPPORTED",
			"Embedded CanvasItem shader source cannot use #include",
			false,
			"Bind an existing ShaderMaterial resource when the shader depends on project-local includes."
		)
	return {"source": source}


func _make_canvas_item_shader(source: String) -> Dictionary:
	var shader := Shader.new()
	shader.code = source
	if shader.get_mode() != Shader.MODE_CANVAS_ITEM:
		return Errors.make(
			"CANVAS_ITEM_SHADER_REQUIRED",
			"Shader source must declare shader_type canvas_item",
			false,
			"Only 2D canvas_item shaders are supported by this MCP.",
			{"shader_mode": _shader_mode_name(shader.get_mode())}
		)
	return {"shader": shader}


func _require_canvas_item_shader_material(canvas_item: CanvasItem) -> Dictionary:
	var material := canvas_item.material as ShaderMaterial
	if material == null:
		return Errors.make(
			"CANVAS_ITEM_SHADER_MATERIAL_REQUIRED",
			"CanvasItem '%s' has no assigned ShaderMaterial" % canvas_item.name,
			false,
			"Call canvas_item_shader_create or canvas_item_shader_bind first."
		)
	var shader: Shader = material.shader
	if shader == null or shader.get_mode() != Shader.MODE_CANVAS_ITEM:
		return Errors.make(
			"CANVAS_ITEM_SHADER_REQUIRED",
			"CanvasItem '%s' does not have a canvas_item shader" % canvas_item.name,
			false,
			"Use canvas_item_shader_set with a shader_type canvas_item source first."
		)
	return {"material": material, "uniforms": _uniform_info_by_name(shader)}


func _parse_uniform_updates(raw_values: Variant, uniform_infos: Dictionary) -> Dictionary:
	if not raw_values is Dictionary or raw_values.is_empty() or raw_values.size() > MAX_UNIFORM_UPDATES:
		return Errors.make(
			"INVALID_CANVAS_ITEM_SHADER_UNIFORMS",
			"values must be a non-empty object containing at most %d uniforms" % MAX_UNIFORM_UPDATES
		)
	var updates := {}
	for raw_name in raw_values:
		if not raw_name is String:
			return Errors.make("INVALID_CANVAS_ITEM_SHADER_UNIFORM", "uniform names must be strings")
		var uniform_name: String = raw_name
		if not uniform_infos.has(uniform_name):
			return Errors.make(
				"CANVAS_ITEM_SHADER_UNIFORM_NOT_FOUND",
				"Shader does not declare uniform: %s" % uniform_name,
				false,
				"Call canvas_item_shader_get to inspect declared uniforms."
			)
		var value_result := _decode_uniform_value(raw_values[raw_name], uniform_infos[uniform_name])
		if value_result.has("_error"):
			return value_result
		updates[uniform_name] = value_result["value"]
	return {"updates": updates}


func _parse_uniform_names(raw_names: Variant, uniform_infos: Dictionary) -> Dictionary:
	if not raw_names is Array or raw_names.is_empty() or raw_names.size() > MAX_UNIFORM_UPDATES:
		return Errors.make(
			"INVALID_CANVAS_ITEM_SHADER_UNIFORMS",
			"names must be a non-empty array containing at most %d uniforms" % MAX_UNIFORM_UPDATES
		)
	var names: Array[String] = []
	for raw_name in raw_names:
		if not raw_name is String or names.has(raw_name):
			return Errors.make("INVALID_CANVAS_ITEM_SHADER_UNIFORM", "names must contain unique uniform names")
		var uniform_name: String = raw_name
		if not uniform_infos.has(uniform_name):
			return Errors.make(
				"CANVAS_ITEM_SHADER_UNIFORM_NOT_FOUND",
				"Shader does not declare uniform: %s" % uniform_name,
				false,
				"Call canvas_item_shader_get to inspect declared uniforms."
			)
		names.append(uniform_name)
	return {"names": names}


func _decode_uniform_value(raw_value: Variant, property_info: Dictionary) -> Dictionary:
	if raw_value == null:
		return Errors.make(
			"INVALID_CANVAS_ITEM_SHADER_UNIFORM_VALUE",
			"Use canvas_item_shader_uniforms_clear to remove a material override."
		)
	if not _is_supported_uniform_type(property_info):
		return Errors.make(
			"UNSUPPORTED_CANVAS_ITEM_SHADER_UNIFORM_TYPE",
			"Uniform type %s is not supported by this MCP release" % type_string(int(property_info.get("type", TYPE_NIL))),
			false,
			"Inspect canvas_item_shader_get and use a supported uniform type."
		)
	if int(property_info.get("type", TYPE_NIL)) == TYPE_OBJECT:
		return _load_uniform_texture(raw_value)
	var decoded := VariantCodec.decode(raw_value, property_info, null)
	if decoded.has("_error"):
		return decoded
	return {"value": decoded["value"]}


func _load_uniform_texture(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CANVAS_ITEM_SHADER_UNIFORM_TEXTURE", "Texture2D uniforms must be res:// paths")
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty() or not resource_path.begins_with("res://") or "/../" in resource_path or resource_path.ends_with("/.."):
		return Errors.make("INVALID_CANVAS_ITEM_SHADER_UNIFORM_TEXTURE", "Texture2D uniform paths must stay inside res://")
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "Texture2D uniform path does not exist: %s" % resource_path)
	var resource := ResourceLoader.load(resource_path)
	if not resource is Texture2D:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "Texture2D uniform path does not load a Texture2D resource")
	return {"value": resource as Texture2D}


func _load_canvas_item_shader_material(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CANVAS_ITEM_SHADER_PATH", "resource_path must be a res:// path")
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty() or not resource_path.begins_with("res://") or "/../" in resource_path or resource_path.ends_with("/.."):
		return Errors.make("INVALID_CANVAS_ITEM_SHADER_PATH", "resource_path must stay inside res://")
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "resource_path does not exist: %s" % resource_path)
	var resource := ResourceLoader.load(resource_path)
	if not resource is ShaderMaterial:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "resource_path does not load a ShaderMaterial resource")
	var material := resource as ShaderMaterial
	var shader: Shader = material.shader
	if shader == null or shader.get_mode() != Shader.MODE_CANVAS_ITEM:
		return Errors.make(
			"CANVAS_ITEM_SHADER_REQUIRED",
			"resource_path must load a ShaderMaterial with a canvas_item shader",
			false,
			"Only 2D canvas_item shaders are supported by this MCP."
		)
	return {"material": material}


func _duplicate_material(current: ShaderMaterial, shader: Shader) -> Dictionary:
	var duplicated := current.duplicate(true)
	if not duplicated is ShaderMaterial:
		return Errors.make("CANVAS_ITEM_SHADER_MATERIAL_DUPLICATE_FAILED", "Unable to duplicate the current ShaderMaterial safely")
	var material := duplicated as ShaderMaterial
	material.shader = shader
	return {"material": material}


func _duplicate_material_preserving_shader(current: ShaderMaterial) -> Dictionary:
	var duplicated := current.duplicate(false)
	if not duplicated is ShaderMaterial:
		return Errors.make("CANVAS_ITEM_SHADER_MATERIAL_DUPLICATE_FAILED", "Unable to duplicate the current ShaderMaterial safely")
	return {"material": duplicated as ShaderMaterial}


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
	var shader_material := material as ShaderMaterial
	var shader: Shader = null if shader_material == null else shader_material.shader
	return {
		"path": ScenePath.from_node(canvas_item, scene_root),
		"type": canvas_item.get_class(),
		"material": _material_info(material),
		"shader": _shader_info(shader),
		"uniforms": [] if shader_material == null or shader == null else _serialize_uniforms(shader_material, shader),
		"supported_shader_type": SUPPORTED_SHADER_TYPE,
		"source_limit": MAX_SOURCE_LENGTH,
		"embedded_source_supports_includes": false,
	}


func _material_info(resource: Resource) -> Dictionary:
	return {
		"assigned": resource != null,
		"type": "" if resource == null else resource.get_class(),
		"resource_path": "" if resource == null else resource.resource_path,
		"origin": "none" if resource == null else ("external" if not resource.resource_path.is_empty() else "embedded"),
		"is_shader_material": resource is ShaderMaterial,
	}


func _shader_info(shader: Shader) -> Dictionary:
	var source := "" if shader == null else shader.code
	return {
		"assigned": shader != null,
		"resource_path": "" if shader == null else shader.resource_path,
		"origin": "none" if shader == null else ("external" if not shader.resource_path.is_empty() else "embedded"),
		"mode": "" if shader == null else _shader_mode_name(shader.get_mode()),
		"is_canvas_item": shader != null and shader.get_mode() == Shader.MODE_CANVAS_ITEM,
		"source": source,
		"source_length": source.length(),
	}


func _uniform_info_by_name(shader: Shader) -> Dictionary:
	var result := {}
	for raw_info in shader.get_shader_uniform_list():
		if not raw_info is Dictionary:
			continue
		var property_info: Dictionary = raw_info
		var uniform_name := str(property_info.get("name", ""))
		if not uniform_name.is_empty():
			result[uniform_name] = property_info
	return result


func _serialize_uniforms(material: ShaderMaterial, shader: Shader) -> Array:
	var uniform_infos := _uniform_info_by_name(shader)
	var names := _sorted_keys(uniform_infos)
	var result: Array = []
	for uniform_name_value in names:
		var uniform_name := str(uniform_name_value)
		var property_info: Dictionary = uniform_infos[uniform_name]
		var current_value = material.get_shader_parameter(uniform_name)
		result.append({
			"name": uniform_name,
			"type": type_string(int(property_info.get("type", TYPE_NIL))),
			"hint": int(property_info.get("hint", PROPERTY_HINT_NONE)),
			"hint_string": str(property_info.get("hint_string", "")),
			"value": VariantCodec.serialize(current_value),
			"has_override": current_value != null,
			"supported": _is_supported_uniform_type(property_info),
		})
	return result


func _is_supported_uniform_type(property_info: Dictionary) -> bool:
	var property_type := int(property_info.get("type", TYPE_NIL))
	return property_type in [
		TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_VECTOR2, TYPE_VECTOR2I, TYPE_RECT2, TYPE_RECT2I,
		TYPE_TRANSFORM2D, TYPE_COLOR, TYPE_ARRAY, TYPE_DICTIONARY, TYPE_PACKED_BYTE_ARRAY,
		TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_INT64_ARRAY, TYPE_PACKED_FLOAT32_ARRAY,
		TYPE_PACKED_FLOAT64_ARRAY, TYPE_PACKED_STRING_ARRAY, TYPE_PACKED_VECTOR2_ARRAY,
		TYPE_PACKED_COLOR_ARRAY, TYPE_OBJECT,
	]


func _sorted_keys(values: Dictionary) -> Array:
	var names: Array = values.keys()
	names.sort()
	return names


func _shader_mode_name(mode: Shader.Mode) -> String:
	var modes := {
		Shader.MODE_SPATIAL: "spatial",
		Shader.MODE_CANVAS_ITEM: "canvas_item",
		Shader.MODE_PARTICLES: "particles",
		Shader.MODE_SKY: "sky",
		Shader.MODE_FOG: "fog",
		5: "texture_blit",
	}
	return modes.get(mode, "unknown")


func _unchanged_response(response: Dictionary) -> Dictionary:
	response["changed"] = false
	response["undoable"] = false
	return response
