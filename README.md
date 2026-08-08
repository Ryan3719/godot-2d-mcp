# Godot 2D MCP

Godot 2D MCP connects Codex, Claude Code, and other MCP clients to a live Godot editor. The project is designed for comprehensive Godot 2D authoring while keeping editor mutations on Godot's main thread and inside its undo/redo system.

The current `0.64.0` preview adds persistent scene node metadata: agents can inspect the metadata Godot will serialize into a `.tscn`, then set, replace, or remove a validated JSON value through normal scene undo/redo. Editor-only metadata and unsafe object-reference writes are deliberately excluded. It retains persistent node groups, scene-persistent flat `OptionButton` and `MenuButton` authoring, native standalone `Shortcut` resource authoring, project-resource management for other audited 2D families, controlled native runtime Tween workflows, one-level nested `AnimationPlayer` tracks, PackedScene instance overrides, persistent Bezier and safe method tracks, Godot Input Map authoring, runtime multi-touch input, paginated ClassDB reflection, versioned coverage snapshots and compatibility diffs, real Godot 4.7 lifecycle validation, runtime performance sampling, PNG assertions, one-call runtime tests, NavigationPolygon baking, runtime audio control, strict typed containers, and broad semantic tooling. Editor-only ClassDB types remain excluded from game-scene authoring.

## Current capabilities

- Streamable HTTP and stdio MCP transports through FastMCP.
- Reconnecting loopback WebSocket connection from a Godot EditorPlugin.
- Multiple Godot editor sessions with explicit session activation.
- Structured, versioned request and response protocol.
- `session_list` and `session_activate`.
- `editor_get_state`.
- `input_map_get`, `input_map_action_upsert`, `input_map_action_delete`, `input_map_undo`, and `input_map_redo` for persistent project Input Map authoring with keyboard, mouse-button, joypad-button, and joypad-axis bindings.
- `shortcut_get`, `shortcut_create`, `shortcut_set`, `shortcut_save`, `shortcut_undo`, and `shortcut_redo` for native standalone `Shortcut` resources. They reuse the Input Map event contract, require at least one binding on create, permit an explicit empty list only when clearing an existing Shortcut, and keep undo/redo isolated per resource.
- Paginated `scene_get_hierarchy`.
- Runtime `class_search` filtered by the centralized 2D type policy.
- `class_2d_coverage` derives a paginated 2D node/resource inventory from the running Godot `ClassDB`, separating generic support, semantic tools, and direct smoke-test status. `class_2d_coverage_snapshot` returns the complete versioned inventory, and `class_2d_coverage_diff` compares a saved snapshot against the active Godot build.
- `class_2d_describe` provides paginated runtime reflection for a supported 2D class: inheritance, public properties, methods, signals, and enums.
- `resource_get`, `resource_create`, `resource_set_properties`, `resource_save`, `resource_undo`, and `resource_redo` provide a typed project-resource workflow for audited 2D families. Creation and mutation are limited to standalone project `.tres`/`.res` resources; create makes missing parent directories below `res://`, updates remain in memory until `resource_save`, and undo/redo is isolated per resource. Imported assets, `Shader`, `ShaderMaterial`, and `Shortcut` remain behind their specialized safe tools.
- `sprite_2d_get` and `sprite_2d_set` for `Sprite2D` textures, frame grids, regions, flips, centering, and offsets.
- `line_2d_get` and `line_2d_set` for `Line2D` points, stroke modes, caps, joints, colors, and existing project-local Curve, Gradient, and Texture2D resources.
- `polygon_2d_get` and `polygon_2d_set` for bounded, non-degenerate `Polygon2D` geometry, UVs, vertex colors, texture mapping, inversion, and offsets.
- `animated_sprite_2d_get` and `animated_sprite_2d_set` for `AnimatedSprite2D` frame-resource assignment, selected animation, autoplay, frame, timing, scale, flipping, centering, and offset configuration.
- `sprite_frames_get`, `sprite_frames_animation_upsert`, `sprite_frames_animation_rename`, and `sprite_frames_animation_remove` for paginated frame inspection and safe `SpriteFrames` animation authoring with existing project-local textures.
- `button_2d_get` and `button_2d_set` for all `BaseButton` interaction state, including toggle mode, action timing, accepted mouse buttons, shortcut and ButtonGroup references. `Button` descendants add text, icon, wrapping, direction, and alignment configuration; `TextureButton` adds normal, pressed, hover, disabled, and focused textures, click masks, stretch mode, and flips; `LinkButton` adds a URI, underline mode, truncation behavior, ellipsis text, text direction, and language.
- `button_menu_items_get`, `button_menu_items_set`, and `button_menu_items_clear` for paginated, undoable flat `OptionButton` and `MenuButton` menu authoring. Both expose only scene-persistent item fields: text, ID, project-local icon, disabled state, and separators; `MenuButton` additionally supports checked check and radio items. Nested submenu trees, per-item Shortcut resources, and all runtime-only PopupMenu state remain outside this workflow.
- `node_get_properties` with property metadata and JSON-safe values.
- `node_groups_get`, `node_group_add`, and `node_group_remove` for scene-persistent Godot node groups. Reads use a packed scene snapshot so runtime-only and Godot-internal groups do not appear as saveable state; writes require a locally owned scene node and participate in scene undo/redo.
- `node_metadata_get`, `node_metadata_set`, and `node_metadata_remove` for scene-persistent node metadata. Reads use packed scene properties as the persistence boundary; writes accept one bounded JSON value under a non-internal ASCII identifier, require a locally owned scene node, and participate in scene undo/redo.
- `node_get_signals` with typed signal arguments and scene connection metadata.
- `animation_list` and `animation_get` for animation-library, track, keyframe, and target inspection.
- `control_get_layout`, `control_set_layout`, and `control_set_layout_preset` for safe Control anchors, offsets, and named layout presets.
- `container_2d_get`, `container_2d_set`, and `container_child_layout_set` for supported Container behavior and direct Control-child layout constraints. Box, Grid, Center, AspectRatio, Flow, Split, Scroll, Tab, and SubViewport containers return a type-specific property catalog with readable enum values; child flags use `fill`, `expand`, `shrink_begin`, `shrink_center`, and `shrink_end`.
- `tab_container_items_get` and `tab_container_item_set` for paginated TabContainer item inspection and atomic title, tooltip, project-local icon, icon-width, disabled/hidden, JSON metadata, and close-button-icon updates on direct Control children. Reorder tabs with `node_move`.
- `control_get_styleboxes`, `control_stylebox_flat_upsert`, and `control_stylebox_override_clear` for local `StyleBoxFlat` theme overrides.
- `control_theme_get`, `control_theme_create`, and `control_theme_assign` for inspecting, creating, attaching, detaching, and undoing Control Theme assignments.
- `control_theme_defaults_set` and `control_theme_defaults_clear` for embedded Theme default font, font size, and base scale configuration.
- `control_theme_item_upsert` and `control_theme_item_clear` for embedded Theme colors, constants, font sizes, fonts, icons, and `StyleBoxFlat` items.
- `collision_shape_get`, `collision_shape_set`, and `collision_shape_clear` for all built-in `Shape2D` resources on `CollisionShape2D` nodes.
- `collision_object_get_layers` and `collision_object_set_layers` for `Area2D`/`PhysicsBody2D` collision layers and masks expressed as layer numbers 1 through 32.
- `area_2d_get` and `area_2d_set` for Area2D monitoring, priority, gravity, and damping overrides using readable enum names.
- `physics_body_2d_get` and `physics_body_2d_set` for `StaticBody2D`, `AnimatableBody2D`, `CharacterBody2D`, and `RigidBody2D` behavior; Character platform layers use 1 through 32 layer-number arrays.
- `joint_2d_get` and `joint_2d_set` for `PinJoint2D`, `GrooveJoint2D`, and `DampedSpringJoint2D`, with stable MCP node paths translated to Godot-relative joint endpoints.
- `ray_cast_2d_get` and `ray_cast_2d_set` for persistent RayCast2D query behavior and collision-mask layer numbers.
- `shape_cast_2d_get`, `shape_cast_2d_set`, and `shape_cast_2d_shape_clear` for ShapeCast2D behavior and independent built-in `Shape2D` resources.
- `navigation_2d_get` and `navigation_2d_set` for `NavigationRegion2D`, `NavigationAgent2D`, `NavigationObstacle2D`, and `NavigationLink2D` configuration, with navigation and avoidance bitfields expressed as 1 through 32 layer-number arrays.
- `navigation_polygon_get`, `navigation_polygon_create`, `navigation_polygon_geometry_set`, `navigation_polygon_outline_set`, `navigation_polygon_outline_remove`, `navigation_polygon_make_from_outlines`, `navigation_polygon_bake_request`, `navigation_polygon_bake_result_get`, and `navigation_polygon_clear` for independent `NavigationPolygon` resources attached to `NavigationRegion2D`, including asynchronous baking from scene-source geometry.
- `camera_2d_get` and `camera_2d_set` for Camera2D framing, drag margins, limits, smoothing, readable anchor/process enums, zoom, and `SubViewport` binding.
- `parallax_2d_get` and `parallax_2d_set` for `Parallax2D` scroll behavior, limits, and repeat configuration.
- `canvas_layer_get` and `canvas_layer_set` for CanvasLayer viewport binding, drawing order, follow behavior, transform, and visibility.
- `path_2d_get`, `path_2d_curve_set`, `path_2d_curve_point_insert`, `path_2d_curve_point_set`, `path_2d_curve_point_remove`, and `path_2d_curve_clear` for paginated `Curve2D` inspection and independent embedded Bézier curve authoring on `Path2D`.
- `skeleton_2d_get`, `bone_2d_get`, `skeleton_2d_bone_create`, `bone_2d_set`, `skeleton_2d_reset_to_rest`, and `skeleton_2d_make_rest_from_current` for safe `Skeleton2D` hierarchy authoring, per-bone rest configuration, and whole-skeleton rest-pose workflows.
- `audio_stream_player_2d_get` and `audio_stream_player_2d_set` for existing `AudioStream` binding, bus routing, volume, pitch, spatial attenuation, area layers, polyphony, autoplay, and Godot's stream/sample playback type on `AudioStreamPlayer2D`.
- `runtime_audio_stream_player_2d_control` and `runtime_audio_stream_player_2d_control_result_get` for bounded state queries, play, stop, and seek actions on a running local `AudioStreamPlayer2D`.
- `runtime_tween_start`, `runtime_tween_result_get`, and `runtime_tween_stop` for bounded native property tweens on a running local `CanvasItem`. Tracks support numeric, `Vector2`, `Vector2i`, `Rect2`, `Rect2i`, `Transform2D`, and `Color` values, plus `Vector2` and `Color` components; arbitrary callbacks, methods, resources, and script-defined properties are excluded.
- `runtime_performance_sample_request` and `runtime_performance_sample_result_get` for bounded FPS, frame-delta, memory, object-count, and draw-call sampling from the running game process.
- `runtime_screenshot_assert` for dependency-free local PNG dimension, pixel, region-mean, and color-presence assertions.
- `runtime_test_run` for bounded scene launch, runtime connection, optional input, performance sampling, PNG assertions, and automatic stop cleanup.
- `gpu_particles_2d_get` and `gpu_particles_2d_set` for persistent `GPUParticles2D` emission, timing, random seed, drawing, texture/material bindings, sub emitters, collision scale, and trails.
- `cpu_particles_2d_get` and `cpu_particles_2d_set` for persistent `CPUParticles2D` emission geometry, motion, drawing, color, animation offsets, and existing `Texture2D` bindings.
- `cpu_particles_2d_curve_get`, `cpu_particles_2d_curve_bind`, `cpu_particles_2d_curve_set`, and `cpu_particles_2d_curve_clear` for all `CPUParticles2D` parameter Curve slots, with copy-on-write embedded edits.
- `cpu_particles_2d_gradient_get`, `cpu_particles_2d_gradient_bind`, `cpu_particles_2d_gradient_set`, and `cpu_particles_2d_gradient_clear` for `CPUParticles2D` color and initial-color Gradient ramps, with copy-on-write embedded edits.
- `particle_process_material_2d_get`, `particle_process_material_2d_create`, and `particle_process_material_2d_set` for safe embedded `ParticleProcessMaterial` creation and copy-on-write 2D particle simulation configuration.
- `particle_process_material_2d_curve_get`, `particle_process_material_2d_curve_bind`, `particle_process_material_2d_curve_set`, and `particle_process_material_2d_curve_clear` for every scalar `CurveTexture` slot used by `GPUParticles2D` ParticleProcessMaterial.
- `particle_process_material_2d_gradient_get`, `particle_process_material_2d_gradient_bind`, `particle_process_material_2d_gradient_set`, and `particle_process_material_2d_gradient_clear` for ParticleProcessMaterial `GradientTexture1D` color ramps.
- `canvas_item_material_get`, `canvas_item_material_create`, `canvas_item_material_bind`, `canvas_item_material_set`, and `canvas_item_material_clear` for safe `CanvasItemMaterial` authoring on any local 2D `CanvasItem`.
- `canvas_item_shader_get`, `canvas_item_shader_create`, `canvas_item_shader_bind`, `canvas_item_shader_set`, `canvas_item_shader_uniforms_set`, `canvas_item_shader_uniforms_clear`, and `canvas_item_shader_clear` for safe `canvas_item` `ShaderMaterial` source and uniform authoring on any local 2D `CanvasItem`.
- `light_2d_get` and `light_2d_set` for semantic `PointLight2D` and `DirectionalLight2D` configuration, including colors, blend modes, shadows, cull-mask layer arrays, normal-map height, PointLight textures, and DirectionalLight shadow distance.
- `light_occluder_2d_get` and `light_occluder_2d_set` for independent `LightOccluder2D` masks, SDF collision, and embedded `OccluderPolygon2D` replacement or clearing.
- `tile_map_layer_get`, `tile_map_layer_cells_get`, `tile_set_get`, `tile_set_layers_get`, `tile_set_atlas_tile_get`, `tile_set_create`, `tile_set_clear`, `tile_set_atlas_source_create`, `tile_set_atlas_tile_create`, `tile_set_physics_layer_create`, `tile_set_navigation_layer_create`, `tile_set_occlusion_layer_create`, `tile_set_custom_data_layer_create`, `tile_set_layer_set`, `tile_set_layer_remove`, `tile_set_terrain_set_create`, `tile_set_terrain_create`, `tile_set_terrain_set_remove`, `tile_set_terrain_remove`, `tile_set_atlas_alternative_create`, `tile_set_atlas_tile_terrain_set`, `tile_set_atlas_tile_custom_data_set`, `tile_set_atlas_tile_collision_set`, `tile_set_atlas_tile_navigation_set`, `tile_set_atlas_tile_occlusion_set`, `tile_map_layer_cells_set`, `tile_map_layer_terrain_paint`, and `tile_map_layer_cells_clear` for embedded `TileSet` and `TileSetAtlasSource` authoring on `TileMapLayer`.
- `node_create`, `node_script_bind`, `node_script_clear`, `node_instance_scene`, `packed_scene_instance_get`, `packed_scene_instance_editable_children_enable`, `node_set_properties`, `node_delete`, `node_rename`, `node_duplicate`, `node_reparent`, and `node_move` with scene-file guards; generic property writes safely bind project resources through typed `resource_path` references.
- `signal_connect` and `signal_disconnect` for persistent local-node connections, including bounded JSON binding arguments, deferred, and one-shot options.
- `animation_create`, `animation_delete`, `animation_track_upsert`, `animation_audio_track_upsert`, `animation_bezier_track_upsert`, `animation_method_track_upsert`, `animation_nested_track_upsert`, `animation_track_delete`, `animation_key_upsert`, and `animation_key_delete` for scene-embedded 2D/UI property, AudioStreamPlayer2D, controlled numeric Bezier, safe native-method, and one-level nested-animation authoring.
- Scene-local `NodePath` property and built-in `AnimationPlayer` track migration during rename and reparent.
- Reparenting preserves global placement for `Node2D` and `Control` by default.
- `scene_undo`, `scene_redo`, and `scene_save` through Godot editor APIs.
- `scene_create` creates and opens a previously absent project-local `.tscn` with a supported built-in 2D/UI root; `scene_open` audits an existing project `PackedScene` before opening it and rejects any unsupported or 3D subtree.
- Atomic multi-property updates registered with `EditorUndoRedoManager`.
- Strict 2D Variant conversion for `Vector2`, `Vector2i`, `Rect2`, `Rect2i`, `Transform2D`, `Color`, typed arrays, typed dictionaries, and common packed arrays.
- Real Godot 4.7 smoke coverage for every currently allowed 2D node's generic lifecycle (create, inspect, save/reopen, delete, undo, redo), plus create, update, signals, animation authoring and binding, Control and Container layout, StyleBoxFlat overrides, cameras, parallax, canvas layers, viewport bindings, rename, duplicate, reparent, reorder, animation-track migration, and save.

See [the initial implementation plan](docs/INITIAL_PLAN.md) for the complete 2D scope and roadmap.

## Architecture

```text
MCP client
   |
   | stdio or Streamable HTTP
   v
Python FastMCP server
   |
   | loopback WebSocket RPC
   v
Godot EditorPlugin
   |
   v
EditorInterface / ClassDB / scene tree
```

The Python process owns MCP, validation, session routing, and request correlation. The Godot plugin owns editor API calls and drains commands from `_process()` with a bounded frame budget.

## Coverage Audit

Call `class_2d_coverage` before choosing a new 2D implementation batch. It accepts `scope` (`all`, `node`, or `resource`), a case-insensitive `query`, and standard pagination. Every entry states whether the current engine can instantiate it, which generic baseline is available, its specialized MCP tools, and whether that exact class has direct semantic smoke coverage. `semantic` means a dedicated workflow exists, not that every public Godot property is exposed; `generic` means only the controlled node read/write and scene-structure workflow is available. Resource entries are an intentionally scoped 2D inventory and `project_resource_reference` only means an existing project resource can be type-checked and bound to a compatible property. Call `class_2d_coverage_snapshot` to obtain one complete, paginated-server-side snapshot with engine metadata; retain that exact result as a baseline. Later call `class_2d_coverage_diff(baseline=...)` against another active editor to receive added, removed, changed, and breaking changes. Breaking changes include a removed class, loss of instantiability or generic capability, a removed semantic tool, and parent/kind changes. Editor-only ClassDB types are deliberately absent because they cannot be serialized safely into gameplay scenes.

## Class API Reflection

Call `class_2d_describe(type_name=..., section=...)` after selecting a supported type. It only exposes types admitted by the same runtime 2D policy as authoring tools. `section` is one of `overview`, `properties`, `methods`, `signals`, or `enums`. Every response includes the class kind, category, parent, complete inheritance chain, instantiability, and Godot API type. Property entries include declared type, class name, hint metadata, read-only status, and getter/setter names. Method and signal entries include typed arguments, the count of trailing default arguments, and flags; enum entries include their integer constants. Results are sorted by name and use `offset` with `limit` (1 through 500); agents must request subsequent pages when `has_more` is true. This is reflection, not an unrestricted invocation surface: use the dedicated authoring tools or controlled generic property workflow to mutate scenes.

## Project Input Map

Call `input_map_get` before changing a project action. `input_map_action_upsert` creates an action when it is absent, or atomically replaces its entire binding list when `replace_existing: true` is explicit. Supplying no `deadzone` on a replacement preserves the current value; a new action defaults to `0.2`. Bindings use `key` (exactly one of `keycode`, `physical_keycode`, `key_label`, or `unicode`, with optional modifiers), `mouse_button` (buttons 1 through 9), `joypad_button` (buttons 0 through 127), or `joypad_motion` (axes 0 through 9 with a non-zero value from `-1` through `1`). `device: -1` means all devices. Input actions in Godot's reserved `ui_*` namespace are read-only through MCP. `input_map_action_delete` requires `confirm: true`; use `input_map_undo` and `input_map_redo` immediately after an MCP Input Map mutation. These tools save `project.godot` synchronously and never require `scene_save`.

## Shortcut Resources

Use `shortcut_create(resource_path="res://input/save.tres", events=[...])` to create a native project-local `Shortcut`; the initial list must contain at least one event. `shortcut_get` returns the ordered serialized bindings and Godot's display text. `shortcut_set` atomically replaces the whole list, including an explicit empty list when clearing a Shortcut. Changes remain in memory until `shortcut_save`; `shortcut_undo` and `shortcut_redo` only affect the specified Shortcut resource. These tools accept only standalone `.tres`/`.res` files under `res://` and reject imported or scripted resources. Bind a saved Shortcut to a `BaseButton` with `button_2d_set` and its existing `shortcut_path` field.

## Editing workflow

Call `editor_get_state` and `scene_get_hierarchy` before editing. Pass the returned `current_scene` as `scene_file` when calling write tools to reject commands if the user switches scenes between inspection and mutation.

Use `scene_create(scene_path="res://scenes/main.tscn", root_type="Node2D", root_name="Main")` to start a scene from scratch. Creation never overwrites an existing path and only writes a project-local `.tscn`; missing parent folders are created under `res://`. `scene_open` accepts only existing project `.tscn` or `.scn` resources after checking that their complete instantiated tree satisfies the 2D policy. Both operations leave the selected scene open for subsequent node edits.

Compound property values use JSON shapes inferred from the target Godot property:

```json
{
  "position": {"x": 120, "y": 64},
  "modulate": {"r": 1, "g": 0.5, "b": 0.25, "a": 1}
}
```

For any public property Godot declares as a `Resource`, `node_set_properties` also accepts a project-local reference. The plugin loads it through Godot, verifies the declared resource class, and only binds the result; it never modifies the external resource. Use `null` to clear an optional resource assignment.

```json
{
  "texture": {"resource_path": "res://art/player.svg"}
}
```

`node_get_properties` reports a `container_type` descriptor for typed arrays and dictionaries. `node_set_properties` converts every item to that declared type before applying the batch. `Dictionary[String, T]` and `Dictionary[StringName, T]` use a JSON object; dictionaries with any other key type use `{"entries": [{"key": ..., "value": ...}]}` so key types survive JSON serialization. Typed object containers only accept `null` or verified project-local `Resource` references, never scene-object references or script-constrained values.

Use `node_groups_get(path=...)` before changing groups. It reports only groups that Godot will serialize into the active `.tscn`; it intentionally excludes runtime-only memberships and Godot internal groups. `node_group_add(path=..., group=...)` and `node_group_remove(path=..., group=...)` always use persistent membership, validate a trimmed non-internal group name up to 128 characters, and create one normal scene undo action. They only edit a node owned by the current scene. An instanced PackedScene's internal node must be edited in its source scene; a runtime-only group with the same name is rejected rather than silently replaced. Call `scene_save` to persist a successful change.

Use `node_metadata_get(path=...)` to inspect only metadata stored in the active scene's packed representation. `node_metadata_set(path=..., key=..., value=...)` creates or replaces one entry; `node_metadata_remove(path=..., key=...)` deletes it. Keys must be non-internal ASCII identifiers up to 128 characters. Values must be non-null finite JSON primitives, arrays, or objects with up to 128 items and eight levels of nesting. This deliberately excludes resource references, scene-node references, scripts, and other object values that cannot be represented safely across MCP and scene saves. These writes only target nodes owned by the current scene and use one normal scene undo action; call `scene_save` to persist the result.

Use the dedicated drawing tools when editing `Sprite2D`, `Line2D`, or `Polygon2D`. They expose only stable, high-value properties and validate frame grids, finite bounded points, polygon area/triangulation, UV and vertex-color cardinality, readable draw enums, and project-local resource types before creating one undo transaction. `texture_path`, `width_curve_path`, and `gradient_path` accept an existing `res://` resource path or an empty string to clear the assignment; the external resource is never modified. For frame animation, use `animated_sprite_2d_set` to assign an existing `SpriteFrames` resource and use the `sprite_frames_*` tools to inspect or author animations. Upserting, renaming, or removing an animation always replaces the assigned `SpriteFrames` with an embedded copy, so edits cannot leak into an external or shared resource.

Use `node_instance_scene` to add an existing project `PackedScene` below a locally owned parent. It only accepts a complete 2D/UI subtree and preserves the instance boundary: the instance root belongs to the current scene while its internal owners remain unchanged. Call `packed_scene_instance_get` to inspect its source, override count, and Editable Children state. `packed_scene_instance_editable_children_enable` explicitly enables the editor-supported override mode; after that, `node_set_properties` can persist public-property overrides on internal nodes. Instance-root rename, duplicate, and reparent preserve any scene-local override children without flattening the instance. Internal structural edits, script changes, signal changes, and specialized semantic handlers remain source-scene workflows.

Node changes mark the scene as unsaved and participate in the active scene's normal Godot undo history. Only `scene_save` writes the `.tscn` file.

For reusable 2D resources, use `resource_create` with an unused `res://` `.tres` or `.res` path, then inspect the returned public property metadata with `resource_get`. `resource_set_properties` accepts the same JSON-safe typed values as node properties and records one resource-scoped undo action. Call `resource_save` after a successful update to persist it. This generic path only covers the audited resource families and never writes imported assets, `Shader`, `ShaderMaterial`, or `Shortcut`; keep using the dedicated shader, Shortcut, and scene-embedded resource tools for those workflows.

`node_create` creates built-in `ClassDB` node types and accepts an optional `script_path` to attach an existing compatible gameplay script in the same undo transaction. `node_script_bind` attaches a compatible existing project script to a local node, with `replace_existing: true` required to replace one; `node_script_clear` explicitly detaches it. These tools only load existing `res://` Script resources whose native base type is supported by the 2D policy and compatible with the target node. `@tool` scripts are deliberately rejected because attaching them could execute project code inside the editor. `node_instance_scene` adds existing project scenes without flattening them. `node_duplicate` and `node_reparent` also accept a complete supported 2D/UI instance root: copied roots retain their original `scene_path`, and scene-local override descendants retain local ownership. Editing a PackedScene descendant is limited to public-property updates through `node_set_properties` after Editable Children is explicitly enabled; internal structural edits, script changes, signal changes, and specialized semantic handlers remain source-scene workflows. Other structure edits reject operations that cross a PackedScene boundary or contain unsupported 3D nodes, deletions that would leave direct `NodePath` or animation-track references dangling, and renames or reparents requiring changes to external animation resources. Animation tools edit only scene-embedded `AnimationLibrary` and `Animation` resources. They support local 2D/UI property value tracks, audio tracks that target a local `AudioStreamPlayer2D` and read existing project `AudioStream` resources, Bezier tracks for a direct writable float property or a writable `Vector2`/`Color` component on a local policy-supported node, method tracks on local un-scripted native nodes, and one-level nested tracks that cue an existing animation or `[stop]` on a local un-scripted `AnimationPlayer`. Nested tracks reject self-reference, nesting within the target animation, external libraries, scripted players, and target animations that use unsupported track types. Runtime Tween tools run only on a local `CanvasItem` and only affect native numeric, transform, and color properties; they do not write the scene, invoke callbacks, call methods, or expose resource or script-defined properties. Method tracks are limited to show/hide, AnimationPlayer play/play_backwards/pause/stop/queue, AudioStreamPlayer2D play/stop, AnimatedSprite2D play/pause/stop, and 2D particle restart; arbitrary methods, scripted targets, external animation libraries and animations, and imported tracks remain out of scope. Layout tools reject Controls managed by a parent `Container`. Style tools create isolated local `StyleBoxFlat` overrides instead of changing shared Theme or external resources. Theme tools can assign an external `res://` Theme but deliberately never mutate it; only scene-embedded Themes are editable. Font items accept an existing project `Font` resource or an embedded `SystemFont` family list, while icon items only bind an existing project `Texture2D`. Collision shape tools replace an existing `Shape2D` with an independent built-in resource rather than mutating an external or shared resource. Collision layer tools apply only to local `CollisionObject2D` nodes. Signal tools only connect methods that already exist; they never generate or modify user script callbacks.

`node_rename` and `node_reparent` migrate direct scene-local `NodePath` properties plus tracks stored in built-in `AnimationPlayer` animations. The returned migration counts make that work visible to the caller. `node_reparent` accepts an optional sibling `index` and defaults `keep_global_transform` to `true`; set it to `false` when the node should inherit its new parent's visual transform instead.

For a button animation, use `animation_create` on an `AnimationPlayer`, then call `animation_track_upsert` with the button path, `scale` or `modulate` property, and typed keyframes. Finish by connecting `pressed`, `mouse_entered`, or `mouse_exited` to the existing `AnimationPlayer.play` method with `binds: ["animation_name"]`. Both animation edits and connections are persistent, saved in the scene, and support undo/redo.

For a standalone Control, call `control_set_layout_preset` for a named placement such as `full_rect`, or use `control_set_layout` with exact `anchors` and `offsets`. `control_stylebox_flat_upsert` then applies `bg_color`, borders, corner radii, shadows, and other public `StyleBoxFlat` properties to a local state such as a Button's `normal` or `hover` style. For a Container, first call `container_2d_get`, then use `container_2d_set` for its supported behavior and `container_child_layout_set` for one direct Control child. Child constraints are deliberately limited to minimum size, size flags, and stretch ratio because anchors and offsets are owned by the parent. The tool rejects non-direct children and PackedScene boundaries. For a TabContainer, inspect its direct Control children with `tab_container_items_get`, update one by its stable child path with `tab_container_item_set`, and use `node_move` to reorder items. Tab icons and close-button icons must be existing project-local `Texture2D` resources; empty paths explicitly clear them.

Use `button_2d_get` before `button_2d_set` on any `BaseButton` descendant. `button_pressed: true` requires `toggle_mode: true`; `button_mask` uses `left`, `right`, and `middle`; `action_mode` uses `press` or `release`. `button_group_path`, `shortcut_path`, button icons, and `TextureButton` textures only bind existing project-local resources and can be cleared with an empty string. Use `button_menu_items_get` before replacing a flat `OptionButton` or `MenuButton` collection. Menu item writes accept only fields that survive a Godot scene save: `kind`, `text`, `id`, `icon_path`, and `disabled`, plus `checked` for MenuButton `check` and `radio` items. `button_menu_items_set` replaces the supplied complete list in one undoable transaction; `button_menu_items_clear` is the explicit destructive empty-list operation. Menus containing nested submenus, per-item Shortcuts, or other runtime-only PopupMenu state are read-only and rejected by write tools to prevent data loss.

For reusable UI styling, call `control_theme_create` on a locally owned parent Control, then set defaults with `control_theme_defaults_set` and add entries using `control_theme_item_upsert`. A Button color entry uses `item_type: "color"`, `theme_type: "Button"`, and `name: "font_color"`; a system font uses `{"source": "system", "families": ["sans-serif"]}`. Icons must be an existing project texture path such as `res://ui/play.svg`. Theme items cascade normally through the Control subtree. `control_theme_assign` may attach an external `res://` Theme, but it is inspection-only through this MCP so external resource files cannot be mutated accidentally.

For a `StaticBody2D`, `CharacterBody2D`, `RigidBody2D`, or `Area2D`, create a locally owned `CollisionShape2D` child and call `collision_shape_set`. Shape names are `circle`, `rectangle`, `capsule`, `segment`, `separation_ray`, `world_boundary`, `convex_polygon`, and `concave_polygon`; every required geometry property must be supplied. `collision_object_set_layers` accepts human-readable lists such as `layers: [2, 5]` and `masks: [1, 3]`. It atomically maps them to Godot's 32-bit collision flags and can be undone from the editor history.

Use `area_2d_set` for environment behavior such as `gravity_space_override: "replace"`, `gravity_direction: {"x": 0, "y": 1}`, and readable damp override modes. Use `physics_body_2d_set` for body-specific behavior only; its `supported_properties` response prevents invalid cross-type fields. `CharacterBody2D` platform-layer properties accept arrays such as `platform_floor_layers: [1, 3]`, not raw bitmasks. `joint_2d_set` accepts `node_a_path` and `node_b_path` from `scene_get_hierarchy`, converts them to paths relative to the joint, and verifies both endpoints are distinct `PhysicsBody2D` nodes. Pin joints support limits and motors, Groove joints expose length and offset, and DampedSpring joints expose length, rest length, stiffness, and damping.

Use `ray_cast_2d_set` with `target_position`, filter flags, and `masks: [2, 4]` to author a persistent RayCast2D. `shape_cast_2d_set` accepts the same filtering configuration plus an optional `shape_type` and `shape_properties`, for example `shape_type: "circle"` and `shape_properties: {"radius": 16}`. Shape resources are independent built-in resources, so shared or external `Shape2D` files are never mutated. Static editor scenes have no simulated physics tick, therefore these tools author query configuration rather than claiming runtime hit results; runtime sampling belongs to the later play-mode integration.

Use `navigation_2d_set` on each navigation node type and first inspect `supported_properties` from `navigation_2d_get`. `navigation_layers`, `avoidance_layers`, and `avoidance_mask` use arrays such as `[1, 3]`; no raw bitmask arithmetic is needed. The tool validates costs, path and avoidance limits, and prevents enabling obstacle carving without enabling navigation-mesh influence. For a Region, first call `navigation_polygon_create`, then either use `navigation_polygon_geometry_set` with shared vertex arrays and convex polygon index arrays, or append outlines with `navigation_polygon_outline_set` and call `navigation_polygon_make_from_outlines`. Geometry and outlines are copied into a new embedded resource for each change, so external and shared NavigationPolygon resources are never edited in place. `navigation_polygon_outline_remove` and `navigation_polygon_clear` are undoable destructive operations. To bake from scene geometry, the polygon needs at least one enclosing outline and `source_geometry_mode: root_node_children`; call `navigation_polygon_bake_request` with an optional current-scene `source_root_path` (empty means the scene root), then poll `navigation_polygon_bake_result_get`. Bake settings are restricted to `agent_radius`, `cell_size`, `border_size`, `baking_rect`, `baking_rect_offset`, `sample_partition_type`, `parsed_geometry_type`, and `parsed_collision_layers`. The plugin parses source geometry on the editor thread and bakes in Godot's background task; it only commits a copied result in one UndoRedo action when the original polygon and edited scene are unchanged. Completed requests are `ready`; changed or freed targets return `stale` and are never overwritten. Godot has no public cancellation API for a bake request.

Create `PointLight2D`, `DirectionalLight2D`, and `LightOccluder2D` with `node_create`, then call their `*_get` tool before configuration. `light_2d_set` uses readable `blend_mode` (`add`, `subtract`, `mix`) and `shadow_filter` (`none`, `pcf5`, `pcf13`) values; `range_item_cull_layers` and `shadow_item_cull_layers` are arrays of layer numbers instead of raw masks. A Point light also accepts `texture_path` with an existing `res://` `Texture2D`, `offset`, and `texture_scale`; passing an empty `texture_path` clears its texture. A Directional light supports `max_distance`, and its `height` is constrained to 0 through 1. `light_occluder_2d_set` accepts `layers`, `sdf_collision`, and one closed or open `{points, closed, cull_mode}` polygon; `clear: true` detaches it. Polygon replacement always creates an independent embedded resource, so shared or external occluders are never mutated in place.

Create `Camera2D`, `Parallax2D`, `CanvasLayer`, and optionally `SubViewport` with `node_create`, then inspect them through their `*_get` tools. `camera_2d_set` accepts readable `anchor_mode` (`fixed_top_left`, `drag_center`) and `process_callback` (`physics`, `idle`) values, bounded drag margins and offsets, valid limits, positive zoom, and an optional `custom_viewport_path`. `parallax_2d_set` validates scroll limits, non-negative `repeat_size`, and repeat counts. `canvas_layer_set` supports viewport binding, layer order, follow settings, transform, and visibility; `transform` cannot be combined with `offset`, `rotation`, or `scale` in one request. For Camera2D and CanvasLayer, set `custom_viewport_path` to an empty string to return to the default viewport. Bindings must point to a `Viewport` or `SubViewport` in the current scene.

Create `Path2D` with `node_create`, then call `path_2d_get` to inspect its Curve2D and paginated Bézier points. Use `path_2d_curve_set` to replace the entire curve with up to 512 `{position, in, out}` points and a bounded `bake_interval`; omitted handles default to zero. `path_2d_curve_point_insert`, `path_2d_curve_point_set`, and `path_2d_curve_point_remove` operate on individual point indexes, while `path_2d_curve_clear` detaches the curve. Every write binds a copied, embedded Curve2D rather than modifying a shared or external resource, and each action is independently undoable.

Create a `Skeleton2D` with `node_create`, then create every `Bone2D` through `skeleton_2d_bone_create`. That tool assigns a valid identity or supplied `rest` transform before the bone enters the scene, supports an optional parent Bone2D path in the same skeleton, and creates local manual display geometry. Use `skeleton_2d_get` and `bone_2d_get` to inspect hierarchy and rest data. `bone_2d_set` updates one valid bone's `rest`, automatic-length switch, manual `length`, and `angle_degrees` atomically; manual geometry requires automatic calculation to be disabled. `skeleton_2d_reset_to_rest` applies existing rest transforms, while destructive `skeleton_2d_make_rest_from_current` replaces every rest pose from current local transforms. All operations reject PackedScene boundaries and support undo/redo.

Create `AudioStreamPlayer2D` with `node_create`, call `audio_stream_player_2d_get`, then configure it with `audio_stream_player_2d_set`. `stream_path` accepts an existing project `res://` `AudioStream` resource, while an empty string clears the binding; external resources are only referenced and never modified. The response lists usable buses, and `area_layers` uses human-readable values 1 through 32. Editing supports `volume_db`, `pitch_scale`, `autoplay`, `max_distance`, `attenuation`, `panning_strength`, `max_polyphony`, `bus`, and `playback_type` (`default`, `stream`, or `sample`) in one undoable transaction. In play mode, call `runtime_audio_stream_player_2d_control` with an absolute path rooted at the running scene and one of `get`, `play`, `stop`, or `seek`; `seek` requires `position_seconds`, while `play` accepts it optionally. Poll `runtime_audio_stream_player_2d_control_result_get` with the returned request ID. The result includes playback state, position, and stream metadata. The runtime bridge only permits `AudioStreamPlayer2D`, never arbitrary node methods.

Create `GPUParticles2D` with `node_create`, then use `gpu_particles_2d_get` before calling `gpu_particles_2d_set`. The semantic tool covers emission count and ratio, lifetime, preprocessing, time scale, one-shot/randomness/fixed-seed controls, interpolation, visibility rect, local coordinates, draw order, collision base size, and trail configuration. `texture_path` and `process_material_path` bind existing project `Texture2D` and `ParticleProcessMaterial`/`ShaderMaterial` resources, while empty strings clear them; these resources are never modified. `sub_emitter_path` binds another `GPUParticles2D` from the active scene using its stable node path, or clears it with an empty string. All supplied properties are applied in a single undoable transaction.

Create `CPUParticles2D` with `node_create`, then use `cpu_particles_2d_get` before calling `cpu_particles_2d_set`. The semantic tool covers emission amount and timing, fixed-seed controls, local drawing order, point/normal/color emission arrays, sphere/rectangle/ring geometry, direction, gravity, velocity, acceleration, damping, angle, scale, hue, animation offsets, and color. `texture_path` only binds an existing project `Texture2D`; an empty string clears it, and the resource is never modified. Every supplied property is applied in one undoable transaction.

Use `cpu_particles_2d_curve_get` to inspect any of the 14 parameter curves: `initial_velocity`, `angular_velocity`, `orbit_velocity`, `linear_accel`, `radial_accel`, `tangential_accel`, `damping`, `angle`, `scale_amount`, `scale_x`, `scale_y`, `hue_variation`, `anim_speed`, or `anim_offset`. `cpu_particles_2d_curve_bind` only attaches an existing project `Curve`; `cpu_particles_2d_curve_set` creates or duplicates an embedded Curve before applying bounded domain, range, bake-resolution, and point/tangent updates; `cpu_particles_2d_curve_clear` detaches it. `cpu_particles_2d_gradient_*` provides the same inspect, bind, copy-on-write edit, and clear workflow for `color` and `initial_color` ramps, including color stops and interpolation settings. External and shared Curve/Gradient resources are never modified in place, and every binding or replacement supports undo/redo.

Call `particle_process_material_2d_get` to inspect the material bound to a `GPUParticles2D`. `particle_process_material_2d_create` adds a new embedded 2D material and requires `replace_existing: true` before replacing an assigned material. `particle_process_material_2d_set` copies the assigned `ParticleProcessMaterial`, applies core 2D emission geometry, velocity, gravity, acceleration, scale, color, turbulence, collision, sub-emitter, and particle-flag settings to the copy, then atomically rebinds it. This preserves both external and shared material resources. The `inherit_emitter_scale` flag is exposed only on Godot versions that report it at runtime.

Use `particle_process_material_2d_curve_*` for scalar CurveTexture slots: `angle`, `angular_velocity`, `orbit_velocity`, `radial_velocity`, `velocity_limit`, `linear_accel`, `radial_accel`, `tangential_accel`, `damping`, `scale`, `scale_over_velocity`, `alpha`, `emission`, `hue_variation`, `anim_speed`, `anim_offset`, and `turbulence_influence_over_life`. Curve edits expose texture width/mode and the nested Curve domain, range, bake resolution, points, and tangent modes. `particle_process_material_2d_gradient_*` supplies the same inspect, bind, copy-on-write edit, and clear workflow for `color` and `initial_color`, including GradientTexture1D width/HDR and nested gradient stops/interpolation. Every mutation first copies the ParticleProcessMaterial and then copies the selected nested texture and Curve/Gradient before replacement, so external or shared resources at every level remain untouched and undo/redo remains complete.

Use `canvas_item_material_get` on any local `CanvasItem` such as `Node2D`, `Control`, `Sprite2D`, `Polygon2D`, or `Line2D`. `canvas_item_material_create` creates a new embedded material and requires `replace_existing: true` before replacing an assigned `ShaderMaterial` or other material. `canvas_item_material_bind` only attaches an existing project `CanvasItemMaterial`; it never edits that resource. `canvas_item_material_set` duplicates the assigned CanvasItemMaterial before applying blend mode (`mix`, `add`, `subtract`, `multiply`, `premultiplied_alpha`), light mode (`normal`, `unshaded`, `light_only`), and particle atlas animation settings. `canvas_item_material_clear` detaches the material. Every assignment and copy-on-write replacement is independently undoable.

Use `canvas_item_shader_get` before assigning a 2D shader to any local `CanvasItem`; it returns every Godot-discovered uniform, its runtime type, hint, current material override, and a `supported` flag. `canvas_item_shader_create` builds an embedded `ShaderMaterial` and `Shader`, and requires `replace_existing: true` when a material is already assigned. `canvas_item_shader_bind` only attaches an existing project `ShaderMaterial` whose Godot-parsed shader type is `canvas_item`; it never changes that resource. `canvas_item_shader_set` always duplicates the material and replaces the shader with a new embedded `canvas_item` source, so shared or external material and shader resources remain unchanged. `canvas_item_shader_uniforms_set` copies the material before atomically applying declared supported uniform values; `sampler2D` uniforms accept an existing `Texture2D` `res://` path. `canvas_item_shader_uniforms_clear` restores named uniforms to their shader defaults. Source is limited to 65,536 characters and embedded sources cannot use `#include`; bind a project resource for include-based shaders. Godot performs the final shader-type parse, while syntax/compiler diagnostics remain available in the editor's Output panel. `canvas_item_shader_clear` detaches the material. Every assignment and replacement is independently undoable.

For a `TileMapLayer`, call `tile_set_create`, then `tile_set_atlas_source_create` with an existing project `Texture2D` path, followed by `tile_set_atlas_tile_create` for every atlas grid tile used by the layer. `tile_set_layers_get` exposes the TileSet physics/navigation/occlusion layers, custom-data schema, and terrain definitions. Create those definitions before assigning `tile_set_atlas_tile_terrain_set`, `tile_set_atlas_tile_custom_data_set`, collision, navigation, or occlusion geometry; terrain peering directions are checked against the TileSet shape and terrain mode. `tile_set_layer_set` updates one existing physics, navigation, occlusion, or custom-data layer, while `tile_set_layer_remove`, `tile_set_terrain_remove`, and `tile_set_terrain_set_remove` remove and reindex their respective definitions. `tile_set_atlas_tile_collision_set` atomically replaces every collision polygon on one physics layer and accepts optional one-way settings; an empty polygon list clears the layer. `tile_set_atlas_tile_navigation_set` atomically replaces a navigation layer with vertices and convex polygon indices, or clears it using `clear: true`. `tile_set_atlas_tile_occlusion_set` atomically replaces the `OccluderPolygon2D` resources for one occlusion layer; each polygon can be closed or open and specify its cull mode. `tile_set_atlas_tile_get` reads all three geometry families before mutation. `tile_map_layer_cells_set` accepts bounded, verified `{coords, source_id, atlas_coords, alternative_tile}` objects and rejects undefined source IDs, atlas coordinates, and alternatives. `tile_map_layer_terrain_paint` applies a configured terrain with `connect` or `path`; path coordinates must be adjacent, and the operation snapshots affected neighbor cells for exact undo/redo. Cell reads and source reads are paginated. TileSet resource edits duplicate the resource before replacement so shared or external TileSets are not mutated in place; each direct cell batch and TileSet semantic edit uses one editor undo transaction.

## Requirements

- Godot 4.7 or newer.
- Python 3.11 or newer.
- [`uv`](https://docs.astral.sh/uv/).

Godot 4.7 is the supported baseline. Development also checks forward compatibility against newer Godot versions where available.

## Install the editor plugin

Copy the addon into the target Godot project:

```bash
mkdir -p /path/to/project/addons
cp -R plugin/addons/godot_2d_mcp /path/to/project/addons/
```

Then enable **Godot 2D MCP** under **Project > Project Settings > Plugins**.

The plugin connects to `ws://127.0.0.1:9500` by default. The port can be changed in **Editor Settings > Godot 2D MCP > Server**, or overridden for a process with `GODOT_2D_MCP_WS_PORT`.

## Configure Codex

Use an absolute path to this checkout:

```toml
[mcp_servers.godot_2d_mcp]
command = "uv"
args = [
  "run",
  "--project", "/absolute/path/to/godot-2d-mcp/server",
  "godot-2d-mcp",
  "--transport", "stdio",
]
enabled = true
startup_timeout_sec = 30
tool_timeout_sec = 30
```

The MCP process may start before or after Godot. The plugin reconnects until the local bridge is available.

## Run with Streamable HTTP

```bash
uv run --project server godot-2d-mcp --transport http --host 127.0.0.1 --port 8000
```

Connect compatible MCP clients to `http://127.0.0.1:8000/mcp`.

## Run Scenes

Use `editor_run(mode="current")` to start the saved scene currently open in the editor, `mode="main"` to start the project main scene, or `editor_run(mode="custom", scene_file="res://scenes/game.tscn")` for an existing project `PackedScene`. The command only accepts the request; poll `editor_get_state` until `play_state` becomes `playing` before treating the game as started. Call `editor_stop` to stop the running game, then wait until `editor_get_state` reports `play_state: "stopped"` and `readiness: "ready"` before editing the scene again. `editor_stop` is safe when nothing is running.

## Runtime Feedback

When enabled, the editor plugin registers its owned `Godot2DMcpRuntime` autoload for the lifetime of the plugin. It is removed when the plugin is disabled and never overwrites an existing autoload with that name. This uses Godot's public debugger protocol, so feedback only connects to games launched from the editor. Call `runtime_get_state` after `editor_run` until `connected` is true.

Use `runtime_logs_get` with its `after_sequence` cursor to read logs from the game process. `runtime_screenshot_request` captures the running root viewport; poll `runtime_screenshot_get` for its bounded PNG or JPEG `data_base64` result, or call `runtime_screenshot_view` once ready to return a standard MCP image block for visual inspection. Screenshot bounds are limited to 1024 pixels per side and encoded output is limited to 1 MB to keep the editor bridge responsive. `runtime_screenshot_assert` evaluates completed PNG captures inside the MCP server, with no game-side code execution. It accepts up to 32 strict `dimensions`, `pixel`, `region_mean`, or `color_presence` assertions; colors use 0-255 `r`, `g`, and `b` channels with an optional alpha channel and tolerance.

`runtime_performance_sample_request(duration_seconds)` accepts 0.1 to 30 seconds and returns a request ID. Its result includes actual duration, frame count, estimated FPS, process-frame delta min/mean/max, and Godot `Performance` monitors for FPS, static memory, object count, and draw calls. `runtime_test_run` is the higher-level bounded workflow: it launches `current`, `main`, or a project-local custom scene; waits for both play state and the runtime bridge; optionally injects existing bounded input events; optionally samples performance and captures/asserts a PNG; then stops the scene by default. It never executes arbitrary runtime methods or scripts, has a 3-60 second total timeout, and returns `passed`, `failed`, or structured `error` outcomes.

`runtime_input_send` accepts bounded `action`, `key`, `mouse_button`, `mouse_motion`, `screen_touch`, and `screen_drag` events; poll `runtime_input_result_get` for the game-side acknowledgement. Touch indices are from 0 through 31. `screen_touch` requires `index`, `position`, and `pressed`, with optional `double_tap` and `canceled`. `screen_drag` requires `index`, `position`, and `relative`, and can include screen-relative motion, pressure (0 through 1), tilt (-1 through 1 per axis), and `pen_inverted`; Godot derives drag velocity when it dispatches the event. Events use `Input.parse_input_event`, so they reach Godot's input pipeline but never control the host operating system. `runtime_audio_stream_player_2d_control` accepts only a bounded absolute path below the active scene root and the fixed `get`/`play`/`stop`/`seek` action set; poll its paired result tool until the request leaves `pending`.

## Development

```bash
uv sync --project server --dev
uv run --project server pytest server/tests
uv run --project server ruff check server scripts/godot_smoke.py
uv run --project server python scripts/godot_smoke.py --godot godot
```

The smoke test copies the test project to a temporary directory, launches a real headless Godot editor, and verifies the complete read/write/save loop without modifying the checkout.

## Security

- Network listeners bind to loopback by default.
- There is no arbitrary object call, expression evaluation, or shell tool.
- The 2D type policy rejects Node3D and 3D-only types.
- Request size, command queue, pagination, and execution time are bounded.
- Write tools carry explicit MCP read-only, destructive, and idempotency annotations.
- All current node mutations use Godot's editor undo/redo history.

## License

[MIT](LICENSE)
