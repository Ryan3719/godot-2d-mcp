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

const NODE_BASELINE_SUPPORT := {
	"create": true,
	"inspect_properties": true,
	"set_properties": true,
	"scene_structure": true,
}

const RESOURCE_BASELINE_SUPPORT := {
	"project_resource_reference": true,
	"embedded_authoring": false,
}

# Keep this catalog explicit: it documents the 2D resources deliberately in scope,
# rather than pretending every Resource returned by ClassDB has 2D authoring support.
const RESOURCE_COVERAGE_CATALOG := [
	{
		"base_type": "Shape2D",
		"category": "physics",
		"tools": ["collision_shape_get", "collision_shape_set", "collision_shape_clear"],
	},
	{
		"base_type": "NavigationPolygon",
		"category": "navigation",
		"tools": [
			"navigation_polygon_get", "navigation_polygon_create",
			"navigation_polygon_geometry_set", "navigation_polygon_outline_set",
			"navigation_polygon_outline_remove", "navigation_polygon_make_from_outlines",
			"navigation_polygon_bake_request", "navigation_polygon_bake_result_get",
			"navigation_polygon_clear",
		],
	},
	{
		"base_type": "TileSet",
		"category": "tile_map",
		"tools": [
			"tile_set_get", "tile_set_layers_get", "tile_set_create", "tile_set_clear",
			"tile_set_atlas_source_create", "tile_set_atlas_tile_create",
			"tile_set_physics_layer_create", "tile_set_navigation_layer_create",
			"tile_set_occlusion_layer_create", "tile_set_custom_data_layer_create",
			"tile_set_layer_set", "tile_set_layer_remove", "tile_set_terrain_set_create",
			"tile_set_terrain_create", "tile_set_terrain_set_remove", "tile_set_terrain_remove",
			"tile_set_atlas_alternative_create", "tile_set_atlas_tile_get",
			"tile_set_atlas_tile_terrain_set", "tile_set_atlas_tile_custom_data_set",
			"tile_set_atlas_tile_collision_set", "tile_set_atlas_tile_navigation_set",
			"tile_set_atlas_tile_occlusion_set",
		],
	},
	{
		"base_type": "TileSetSource",
		"category": "tile_map",
		"tools": ["tile_set_atlas_source_create", "tile_set_atlas_tile_create"],
	},
	{
		"base_type": "Curve2D",
		"category": "path",
		"tools": [
			"path_2d_get", "path_2d_curve_set", "path_2d_curve_point_insert",
			"path_2d_curve_point_set", "path_2d_curve_point_remove", "path_2d_curve_clear",
		],
	},
	{
		"base_type": "Curve",
		"category": "visual",
		"tools": ["line_2d_get", "line_2d_set"],
	},
	{
		"base_type": "OccluderPolygon2D",
		"category": "lighting",
		"tools": ["light_occluder_2d_get", "light_occluder_2d_set", "tile_set_atlas_tile_occlusion_set"],
	},
	{
		"base_type": "AudioStream",
		"category": "audio",
		"tools": ["audio_stream_player_2d_get", "audio_stream_player_2d_set"],
	},
	{
		"base_type": "ParticleProcessMaterial",
		"category": "particles",
		"tools": [
			"particle_process_material_2d_get", "particle_process_material_2d_create",
			"particle_process_material_2d_set", "particle_process_material_2d_curve_get",
			"particle_process_material_2d_curve_bind", "particle_process_material_2d_curve_set",
			"particle_process_material_2d_curve_clear", "particle_process_material_2d_gradient_get",
			"particle_process_material_2d_gradient_bind", "particle_process_material_2d_gradient_set",
			"particle_process_material_2d_gradient_clear",
		],
	},
	{
		"base_type": "CurveTexture",
		"category": "particles",
		"tools": [
			"particle_process_material_2d_curve_get", "particle_process_material_2d_curve_bind",
			"particle_process_material_2d_curve_set", "particle_process_material_2d_curve_clear",
			"cpu_particles_2d_curve_get", "cpu_particles_2d_curve_bind",
			"cpu_particles_2d_curve_set", "cpu_particles_2d_curve_clear",
		],
	},
	{
		"base_type": "GradientTexture1D",
		"category": "particles",
		"tools": [
			"particle_process_material_2d_gradient_get", "particle_process_material_2d_gradient_bind",
			"particle_process_material_2d_gradient_set", "particle_process_material_2d_gradient_clear",
			"cpu_particles_2d_gradient_get", "cpu_particles_2d_gradient_bind",
			"cpu_particles_2d_gradient_set", "cpu_particles_2d_gradient_clear",
		],
	},
	{
		"base_type": "Gradient",
		"category": "particles",
		"tools": [
			"particle_process_material_2d_gradient_set", "cpu_particles_2d_gradient_set",
			"line_2d_get", "line_2d_set",
		],
	},
	{
		"base_type": "CanvasItemMaterial",
		"category": "material",
		"tools": [
			"canvas_item_material_get", "canvas_item_material_create", "canvas_item_material_bind",
			"canvas_item_material_set", "canvas_item_material_clear",
		],
	},
	{
		"base_type": "ShaderMaterial",
		"category": "material",
		"tools": [
			"canvas_item_shader_get", "canvas_item_shader_create", "canvas_item_shader_bind",
			"canvas_item_shader_set", "canvas_item_shader_uniforms_set",
			"canvas_item_shader_uniforms_clear", "canvas_item_shader_clear",
		],
	},
	{
		"base_type": "Shader",
		"category": "shader",
		"tools": ["canvas_item_shader_create", "canvas_item_shader_set"],
	},
	{
		"base_type": "Theme",
		"category": "ui",
		"tools": [
			"control_theme_get", "control_theme_create", "control_theme_assign",
			"control_theme_defaults_set", "control_theme_defaults_clear",
			"control_theme_item_upsert", "control_theme_item_clear",
		],
	},
	{
		"base_type": "StyleBox",
		"category": "ui",
		"tools": [
			"control_get_styleboxes", "control_stylebox_flat_upsert",
			"control_stylebox_override_clear", "control_theme_item_upsert",
		],
	},
	{
		"base_type": "Font",
		"category": "ui",
		"tools": ["control_theme_defaults_set", "control_theme_item_upsert"],
	},
	{
		"base_type": "ButtonGroup",
		"category": "ui",
		"tools": ["button_2d_get", "button_2d_set"],
	},
	{
		"base_type": "Shortcut",
		"category": "input",
		"tools": ["button_2d_get", "button_2d_set"],
	},
	{
		"base_type": "Texture2D",
		"category": "visual",
		"tools": [
			"node_set_properties", "control_theme_item_upsert", "sprite_2d_get", "sprite_2d_set",
			"line_2d_get", "line_2d_set", "polygon_2d_get", "polygon_2d_set",
			"sprite_frames_get", "sprite_frames_animation_upsert",
			"button_2d_get", "button_2d_set",
		],
	},
	{
		"base_type": "SpriteFrames",
		"category": "visual",
		"tools": [
			"animated_sprite_2d_get", "animated_sprite_2d_set", "sprite_frames_get",
			"sprite_frames_animation_upsert", "sprite_frames_animation_rename",
			"sprite_frames_animation_remove",
		],
	},
	{
		"base_type": "LabelSettings",
		"category": "ui",
		"tools": ["node_set_properties"],
	},
]

const NODE_SEMANTIC_CATALOG := [
	{
		"base_type": "CanvasItem",
		"tools": [
			"canvas_item_material_get", "canvas_item_material_create", "canvas_item_material_bind",
			"canvas_item_material_set", "canvas_item_material_clear", "canvas_item_shader_get",
			"canvas_item_shader_create", "canvas_item_shader_bind", "canvas_item_shader_set",
			"canvas_item_shader_uniforms_set", "canvas_item_shader_uniforms_clear",
			"canvas_item_shader_clear",
		],
	},
	{
		"base_type": "Control",
		"tools": [
			"control_get_layout", "control_set_layout", "control_set_layout_preset",
			"control_get_styleboxes", "control_stylebox_flat_upsert",
			"control_stylebox_override_clear", "control_theme_get", "control_theme_create",
			"control_theme_assign", "control_theme_defaults_set", "control_theme_defaults_clear",
			"control_theme_item_upsert", "control_theme_item_clear",
		],
	},
	{
		"base_type": "Container",
		"tools": ["container_2d_get", "container_2d_set", "container_child_layout_set"],
	},
	{
		"base_type": "TabContainer",
		"tools": ["tab_container_items_get", "tab_container_item_set"],
	},
	{
		"base_type": "BaseButton",
		"tools": ["button_2d_get", "button_2d_set"],
	},
	{
		"base_type": "OptionButton",
		"tools": ["button_menu_items_get", "button_menu_items_set", "button_menu_items_clear"],
	},
	{
		"base_type": "MenuButton",
		"tools": ["button_menu_items_get", "button_menu_items_set", "button_menu_items_clear"],
	},
	{
		"base_type": "AnimationPlayer",
		"tools": [
			"animation_list", "animation_get", "animation_create", "animation_delete",
			"animation_track_upsert", "animation_audio_track_upsert", "animation_track_delete",
			"animation_key_upsert",
			"animation_key_delete",
		],
	},
	{
		"base_type": "CollisionShape2D",
		"tools": ["collision_shape_get", "collision_shape_set", "collision_shape_clear"],
	},
	{
		"base_type": "CollisionObject2D",
		"tools": ["collision_object_get_layers", "collision_object_set_layers"],
	},
	{"base_type": "Area2D", "tools": ["area_2d_get", "area_2d_set"]},
	{
		"base_type": "PhysicsBody2D",
		"tools": ["physics_body_2d_get", "physics_body_2d_set"],
	},
	{"base_type": "Joint2D", "tools": ["joint_2d_get", "joint_2d_set"]},
	{"base_type": "RayCast2D", "tools": ["ray_cast_2d_get", "ray_cast_2d_set"]},
	{
		"base_type": "ShapeCast2D",
		"tools": ["shape_cast_2d_get", "shape_cast_2d_set", "shape_cast_2d_shape_clear"],
	},
	{
		"base_type": "NavigationRegion2D",
		"tools": [
			"navigation_2d_get", "navigation_2d_set", "navigation_polygon_get",
			"navigation_polygon_create", "navigation_polygon_geometry_set",
			"navigation_polygon_outline_set", "navigation_polygon_outline_remove",
			"navigation_polygon_make_from_outlines", "navigation_polygon_clear",
		],
	},
	{
		"base_type": "NavigationAgent2D",
		"tools": ["navigation_2d_get", "navigation_2d_set"],
	},
	{
		"base_type": "NavigationObstacle2D",
		"tools": ["navigation_2d_get", "navigation_2d_set"],
	},
	{
		"base_type": "NavigationLink2D",
		"tools": ["navigation_2d_get", "navigation_2d_set"],
	},
	{"base_type": "Camera2D", "tools": ["camera_2d_get", "camera_2d_set"]},
	{"base_type": "Parallax2D", "tools": ["parallax_2d_get", "parallax_2d_set"]},
	{"base_type": "CanvasLayer", "tools": ["canvas_layer_get", "canvas_layer_set"]},
	{
		"base_type": "Path2D",
		"tools": [
			"path_2d_get", "path_2d_curve_set", "path_2d_curve_point_insert",
			"path_2d_curve_point_set", "path_2d_curve_point_remove", "path_2d_curve_clear",
		],
	},
	{
		"base_type": "Skeleton2D",
		"tools": [
			"skeleton_2d_get", "skeleton_2d_bone_create", "skeleton_2d_reset_to_rest",
			"skeleton_2d_make_rest_from_current",
		],
	},
	{"base_type": "Bone2D", "tools": ["bone_2d_get", "bone_2d_set"]},
	{
		"base_type": "AudioStreamPlayer2D",
		"tools": [
			"audio_stream_player_2d_get", "audio_stream_player_2d_set",
			"runtime_audio_stream_player_2d_control",
			"runtime_audio_stream_player_2d_control_result_get",
		],
	},
	{
		"base_type": "GPUParticles2D",
		"tools": [
			"gpu_particles_2d_get", "gpu_particles_2d_set", "particle_process_material_2d_get",
			"particle_process_material_2d_create", "particle_process_material_2d_set",
		],
	},
	{
		"base_type": "CPUParticles2D",
		"tools": [
			"cpu_particles_2d_get", "cpu_particles_2d_set", "cpu_particles_2d_curve_get",
			"cpu_particles_2d_curve_bind", "cpu_particles_2d_curve_set",
			"cpu_particles_2d_curve_clear", "cpu_particles_2d_gradient_get",
			"cpu_particles_2d_gradient_bind", "cpu_particles_2d_gradient_set",
			"cpu_particles_2d_gradient_clear",
		],
	},
	{
		"base_type": "Light2D",
		"tools": ["light_2d_get", "light_2d_set"],
	},
	{
		"base_type": "Sprite2D",
		"tools": ["sprite_2d_get", "sprite_2d_set"],
	},
	{
		"base_type": "AnimatedSprite2D",
		"tools": [
			"animated_sprite_2d_get", "animated_sprite_2d_set", "sprite_frames_get",
			"sprite_frames_animation_upsert", "sprite_frames_animation_rename",
			"sprite_frames_animation_remove",
		],
	},
	{
		"base_type": "Line2D",
		"tools": ["line_2d_get", "line_2d_set"],
	},
	{
		"base_type": "Polygon2D",
		"tools": ["polygon_2d_get", "polygon_2d_set"],
	},
	{
		"base_type": "LightOccluder2D",
		"tools": ["light_occluder_2d_get", "light_occluder_2d_set"],
	},
	{
		"base_type": "TileMapLayer",
		"tools": [
			"tile_map_layer_get", "tile_map_layer_cells_get", "tile_set_get",
		"tile_set_layers_get", "tile_map_layer_cells_set", "tile_map_layer_cells_clear",
		"tile_map_layer_terrain_paint", "tile_set_create", "tile_set_clear", "tile_set_atlas_source_create",
		"tile_set_atlas_tile_create", "tile_set_physics_layer_create",
		"tile_set_navigation_layer_create", "tile_set_occlusion_layer_create",
		"tile_set_custom_data_layer_create", "tile_set_layer_set", "tile_set_layer_remove",
		"tile_set_terrain_set_create", "tile_set_terrain_create", "tile_set_terrain_set_remove",
		"tile_set_terrain_remove", "tile_set_atlas_alternative_create",
			"tile_set_atlas_tile_terrain_set", "tile_set_atlas_tile_custom_data_set",
			"tile_set_atlas_tile_collision_set", "tile_set_atlas_tile_navigation_set",
			"tile_set_atlas_tile_occlusion_set",
		],
	},
]

const SEMANTIC_SMOKE_COVERED_CLASSES := {
	"Button": true,
	"TextureButton": true,
	"LinkButton": true,
	"OptionButton": true,
	"MenuButton": true,
	"HBoxContainer": true,
	"GridContainer": true,
	"AspectRatioContainer": true,
	"HFlowContainer": true,
	"HSplitContainer": true,
	"ScrollContainer": true,
	"TabContainer": true,
	"SubViewportContainer": true,
	"Area2D": true,
	"StaticBody2D": true,
	"AnimatableBody2D": true,
	"CharacterBody2D": true,
	"RigidBody2D": true,
	"CollisionShape2D": true,
	"PinJoint2D": true,
	"GrooveJoint2D": true,
	"DampedSpringJoint2D": true,
	"RayCast2D": true,
	"ShapeCast2D": true,
	"NavigationRegion2D": true,
	"NavigationAgent2D": true,
	"NavigationObstacle2D": true,
	"NavigationLink2D": true,
	"NavigationPolygon": true,
	"Path2D": true,
	"Skeleton2D": true,
	"Bone2D": true,
	"AudioStreamPlayer2D": true,
	"GPUParticles2D": true,
	"CPUParticles2D": true,
	"Camera2D": true,
	"Parallax2D": true,
	"CanvasLayer": true,
	"PointLight2D": true,
	"DirectionalLight2D": true,
	"LightOccluder2D": true,
	"Sprite2D": true,
	"AnimatedSprite2D": true,
	"Line2D": true,
	"Polygon2D": true,
	"TileMapLayer": true,
	"Theme": true,
	"StyleBoxFlat": true,
	"ParticleProcessMaterial": true,
	"CanvasItemMaterial": true,
	"ShaderMaterial": true,
}


static func is_supported_node_class(type_name: StringName) -> bool:
	var class_string := String(type_name)
	if not ClassDB.class_exists(type_name) or not ClassDB.can_instantiate(type_name):
		return false
	if _is_editor_only_class(type_name):
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


static func _is_editor_only_class(type_name: StringName) -> bool:
	var api_type := ClassDB.class_get_api_type(type_name)
	return api_type == ClassDB.API_EDITOR or api_type == ClassDB.API_EDITOR_EXTENSION


static func category(type_name: StringName) -> String:
	var class_string := String(type_name)
	if class_string == "Control" or ClassDB.is_parent_class(type_name, "Control"):
		return "ui"
	if class_string == "Node2D" or ClassDB.is_parent_class(type_name, "Node2D"):
		return "node_2d"
	if class_string.ends_with("2D"):
		return "helper_2d"
	return "support"


static func coverage_kind(type_name: StringName) -> String:
	if is_supported_node_class(type_name):
		return "node"
	if is_audited_resource_class(type_name):
		return "resource"
	return ""


static func is_audited_resource_class(type_name: StringName) -> bool:
	if not ClassDB.class_exists(type_name):
		return false
	if type_name != &"Resource" and not ClassDB.is_parent_class(type_name, &"Resource"):
		return false
	return not _matching_resource_catalog_entry(type_name).is_empty()


static func coverage_category(type_name: StringName, kind: String) -> String:
	if kind == "node":
		return category(type_name)
	var entry := _matching_resource_catalog_entry(type_name)
	return str(entry.get("category", "resource"))


static func coverage_base_support(kind: String) -> Dictionary:
	if kind == "node":
		return NODE_BASELINE_SUPPORT.duplicate(true)
	return RESOURCE_BASELINE_SUPPORT.duplicate(true)


static func coverage_semantic_tools(type_name: StringName, kind: String) -> Array[String]:
	var catalog: Array = NODE_SEMANTIC_CATALOG if kind == "node" else RESOURCE_COVERAGE_CATALOG
	var tools: Array[String] = []
	for entry_value in catalog:
		var entry: Dictionary = entry_value
		if not _matches_type(type_name, StringName(entry["base_type"])):
			continue
		for tool_value in entry["tools"]:
			var tool_name := str(tool_value)
			if tool_name not in tools:
				tools.append(tool_name)
	return tools


static func coverage_test_status(type_name: StringName) -> String:
	return "semantic_smoke" if SEMANTIC_SMOKE_COVERED_CLASSES.has(String(type_name)) else "not_directly_smoke_covered"


static func _matching_resource_catalog_entry(type_name: StringName) -> Dictionary:
	for entry_value in RESOURCE_COVERAGE_CATALOG:
		var entry: Dictionary = entry_value
		if _matches_type(type_name, StringName(entry["base_type"])):
			return entry
	return {}


static func _matches_type(type_name: StringName, base_type: StringName) -> bool:
	return type_name == base_type or ClassDB.is_parent_class(type_name, base_type)
