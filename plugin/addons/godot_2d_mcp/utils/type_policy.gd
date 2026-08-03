@tool
extends RefCounted

const GENERIC_NODE_ALLOWLIST := {
	"Node": true,
	"Timer": true,
	"AnimationMixer": true,
	"AnimationPlayer": true,
	"AudioStreamPlayer": true,
	"ResourcePreloader": true,
	"CanvasLayer": true,
	"SubViewport": true,
	"Window": true,
}


static func is_supported_node_class(type_name: StringName) -> bool:
	var class_string := String(type_name)
	if not ClassDB.class_exists(type_name) or not ClassDB.can_instantiate(type_name):
		return false
	if class_string == "Node3D" or ClassDB.is_parent_class(type_name, "Node3D"):
		return false
	if class_string.contains("3D"):
		return false
	if not (class_string == "Node" or ClassDB.is_parent_class(type_name, "Node")):
		return false
	if class_string == "CanvasItem" or ClassDB.is_parent_class(type_name, "CanvasItem"):
		return true
	if class_string.ends_with("2D"):
		return true
	return GENERIC_NODE_ALLOWLIST.has(class_string)


static func category(type_name: StringName) -> String:
	var class_string := String(type_name)
	if class_string == "Control" or ClassDB.is_parent_class(type_name, "Control"):
		return "ui"
	if class_string == "Node2D" or ClassDB.is_parent_class(type_name, "Node2D"):
		return "node_2d"
	if class_string.ends_with("2D"):
		return "helper_2d"
	return "support"
