# Godot 2D MCP

Godot 2D MCP connects Codex, Claude Code, and other MCP clients to a live Godot editor. The project is designed for comprehensive Godot 2D authoring while keeping editor mutations on Godot's main thread and inside its undo/redo system.

The current `0.31.0` preview adds game-process logs, viewport screenshots, and input simulation alongside safe editor run and stop control, `canvas_item` `ShaderMaterial` uniform authoring, source, `CanvasItemMaterial`, `ParticleProcessMaterial` CurveTexture/GradientTexture1D, and `CPUParticles2D` Curve/Gradient resources for scene, signal, animation, UI, Theme, collision, query, navigation, lighting, TileMap, viewport composition, path, skeleton, audio, and particle-node editing. Agents can configure 2D rendering, run a scene, inspect real game output, and verify rendered pixels while retaining Godot-native undo and save behavior.

## Current capabilities

- Streamable HTTP and stdio MCP transports through FastMCP.
- Reconnecting loopback WebSocket connection from a Godot EditorPlugin.
- Multiple Godot editor sessions with explicit session activation.
- Structured, versioned request and response protocol.
- `session_list` and `session_activate`.
- `editor_get_state`.
- Paginated `scene_get_hierarchy`.
- Runtime `class_search` filtered by the centralized 2D type policy.
- `node_get_properties` with property metadata and JSON-safe values.
- `node_get_signals` with typed signal arguments and scene connection metadata.
- `animation_list` and `animation_get` for animation-library, track, keyframe, and target inspection.
- `control_get_layout`, `control_set_layout`, and `control_set_layout_preset` for safe Control anchors, offsets, and named layout presets.
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
- `navigation_polygon_get`, `navigation_polygon_create`, `navigation_polygon_geometry_set`, `navigation_polygon_outline_set`, `navigation_polygon_outline_remove`, `navigation_polygon_make_from_outlines`, and `navigation_polygon_clear` for independent `NavigationPolygon` resources attached to `NavigationRegion2D`.
- `camera_2d_get` and `camera_2d_set` for Camera2D framing, drag margins, limits, smoothing, readable anchor/process enums, zoom, and `SubViewport` binding.
- `parallax_2d_get` and `parallax_2d_set` for `Parallax2D` scroll behavior, limits, and repeat configuration.
- `canvas_layer_get` and `canvas_layer_set` for CanvasLayer viewport binding, drawing order, follow behavior, transform, and visibility.
- `path_2d_get`, `path_2d_curve_set`, `path_2d_curve_point_insert`, `path_2d_curve_point_set`, `path_2d_curve_point_remove`, and `path_2d_curve_clear` for paginated `Curve2D` inspection and independent embedded Bézier curve authoring on `Path2D`.
- `skeleton_2d_get`, `bone_2d_get`, `skeleton_2d_bone_create`, `bone_2d_set`, `skeleton_2d_reset_to_rest`, and `skeleton_2d_make_rest_from_current` for safe `Skeleton2D` hierarchy authoring, per-bone rest configuration, and whole-skeleton rest-pose workflows.
- `audio_stream_player_2d_get` and `audio_stream_player_2d_set` for existing `AudioStream` binding, bus routing, volume, pitch, spatial attenuation, area layers, polyphony, autoplay, and Godot's stream/sample playback type on `AudioStreamPlayer2D`.
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
- `tile_map_layer_get`, `tile_map_layer_cells_get`, `tile_set_get`, `tile_set_layers_get`, `tile_set_atlas_tile_get`, `tile_set_create`, `tile_set_clear`, `tile_set_atlas_source_create`, `tile_set_atlas_tile_create`, `tile_set_physics_layer_create`, `tile_set_navigation_layer_create`, `tile_set_occlusion_layer_create`, `tile_set_custom_data_layer_create`, `tile_set_terrain_set_create`, `tile_set_terrain_create`, `tile_set_atlas_alternative_create`, `tile_set_atlas_tile_terrain_set`, `tile_set_atlas_tile_custom_data_set`, `tile_set_atlas_tile_collision_set`, `tile_set_atlas_tile_navigation_set`, `tile_set_atlas_tile_occlusion_set`, `tile_map_layer_cells_set`, and `tile_map_layer_cells_clear` for embedded `TileSet` and `TileSetAtlasSource` authoring on `TileMapLayer`.
- `node_create`, `node_set_properties`, `node_delete`, `node_rename`, `node_duplicate`, `node_reparent`, and `node_move` with scene-file guards.
- `signal_connect` and `signal_disconnect` for persistent local-node connections, including bounded JSON binding arguments, deferred, and one-shot options.
- `animation_create`, `animation_delete`, `animation_track_upsert`, `animation_track_delete`, `animation_key_upsert`, and `animation_key_delete` for scene-embedded 2D/UI property animation.
- Scene-local `NodePath` property and built-in `AnimationPlayer` track migration during rename and reparent.
- Reparenting preserves global placement for `Node2D` and `Control` by default.
- `scene_undo`, `scene_redo`, and `scene_save` through Godot editor APIs.
- Atomic multi-property updates registered with `EditorUndoRedoManager`.
- Strict 2D Variant conversion for `Vector2`, `Vector2i`, `Rect2`, `Rect2i`, `Transform2D`, `Color`, arrays, dictionaries, and common packed arrays.
- Real Godot 4.7 smoke coverage for create, update, signals, animation authoring and binding, Control layout, StyleBoxFlat overrides, cameras, parallax, canvas layers, viewport bindings, rename, duplicate, reparent, reorder, undo, redo, delete, restore, animation-track migration, and save.

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

## Editing workflow

Call `editor_get_state` and `scene_get_hierarchy` before editing. Pass the returned `current_scene` as `scene_file` when calling write tools to reject commands if the user switches scenes between inspection and mutation.

Compound property values use JSON shapes inferred from the target Godot property:

```json
{
  "position": {"x": 120, "y": 64},
  "modulate": {"r": 1, "g": 0.5, "b": 0.25, "a": 1}
}
```

Node changes mark the scene as unsaved and participate in the active scene's normal Godot undo history. Only `scene_save` writes the `.tscn` file.

This preview creates built-in `ClassDB` node types only. It rejects structure edits that cross a PackedScene boundary or contain unsupported 3D nodes, deletions that would leave direct `NodePath` or animation-track references dangling, and renames or reparents requiring changes to external animation resources. Animation tools edit only scene-embedded `AnimationLibrary` and `Animation` resources, and create 2D/UI property value tracks only; external resources, imported tracks, method tracks, audio tracks, and arbitrary code execution remain out of scope. Layout tools reject Controls managed by a parent `Container`. Style tools create isolated local `StyleBoxFlat` overrides instead of changing shared Theme or external resources. Theme tools can assign an external `res://` Theme but deliberately never mutate it; only scene-embedded Themes are editable. Font items accept an existing project `Font` resource or an embedded `SystemFont` family list, while icon items only bind an existing project `Texture2D`. Collision shape tools replace an existing `Shape2D` with an independent built-in resource rather than mutating an external or shared resource. Collision layer tools apply only to local `CollisionObject2D` nodes. Signal tools only connect methods that already exist; they never generate or modify user script callbacks.

`node_rename` and `node_reparent` migrate direct scene-local `NodePath` properties plus tracks stored in built-in `AnimationPlayer` animations. The returned migration counts make that work visible to the caller. `node_reparent` accepts an optional sibling `index` and defaults `keep_global_transform` to `true`; set it to `false` when the node should inherit its new parent's visual transform instead.

For a button animation, use `animation_create` on an `AnimationPlayer`, then call `animation_track_upsert` with the button path, `scale` or `modulate` property, and typed keyframes. Finish by connecting `pressed`, `mouse_entered`, or `mouse_exited` to the existing `AnimationPlayer.play` method with `binds: ["animation_name"]`. Both animation edits and connections are persistent, saved in the scene, and support undo/redo.

For a standalone Control, call `control_set_layout_preset` for a named placement such as `full_rect`, or use `control_set_layout` with exact `anchors` and `offsets`. `control_stylebox_flat_upsert` then applies `bg_color`, borders, corner radii, shadows, and other public `StyleBoxFlat` properties to a local state such as a Button's `normal` or `hover` style. Controls below a `Container` are intentionally rejected because the container owns their layout.

For reusable UI styling, call `control_theme_create` on a locally owned parent Control, then set defaults with `control_theme_defaults_set` and add entries using `control_theme_item_upsert`. A Button color entry uses `item_type: "color"`, `theme_type: "Button"`, and `name: "font_color"`; a system font uses `{"source": "system", "families": ["sans-serif"]}`. Icons must be an existing project texture path such as `res://ui/play.svg`. Theme items cascade normally through the Control subtree. `control_theme_assign` may attach an external `res://` Theme, but it is inspection-only through this MCP so external resource files cannot be mutated accidentally.

For a `StaticBody2D`, `CharacterBody2D`, `RigidBody2D`, or `Area2D`, create a locally owned `CollisionShape2D` child and call `collision_shape_set`. Shape names are `circle`, `rectangle`, `capsule`, `segment`, `separation_ray`, `world_boundary`, `convex_polygon`, and `concave_polygon`; every required geometry property must be supplied. `collision_object_set_layers` accepts human-readable lists such as `layers: [2, 5]` and `masks: [1, 3]`. It atomically maps them to Godot's 32-bit collision flags and can be undone from the editor history.

Use `area_2d_set` for environment behavior such as `gravity_space_override: "replace"`, `gravity_direction: {"x": 0, "y": 1}`, and readable damp override modes. Use `physics_body_2d_set` for body-specific behavior only; its `supported_properties` response prevents invalid cross-type fields. `CharacterBody2D` platform-layer properties accept arrays such as `platform_floor_layers: [1, 3]`, not raw bitmasks. `joint_2d_set` accepts `node_a_path` and `node_b_path` from `scene_get_hierarchy`, converts them to paths relative to the joint, and verifies both endpoints are distinct `PhysicsBody2D` nodes. Pin joints support limits and motors, Groove joints expose length and offset, and DampedSpring joints expose length, rest length, stiffness, and damping.

Use `ray_cast_2d_set` with `target_position`, filter flags, and `masks: [2, 4]` to author a persistent RayCast2D. `shape_cast_2d_set` accepts the same filtering configuration plus an optional `shape_type` and `shape_properties`, for example `shape_type: "circle"` and `shape_properties: {"radius": 16}`. Shape resources are independent built-in resources, so shared or external `Shape2D` files are never mutated. Static editor scenes have no simulated physics tick, therefore these tools author query configuration rather than claiming runtime hit results; runtime sampling belongs to the later play-mode integration.

Use `navigation_2d_set` on each navigation node type and first inspect `supported_properties` from `navigation_2d_get`. `navigation_layers`, `avoidance_layers`, and `avoidance_mask` use arrays such as `[1, 3]`; no raw bitmask arithmetic is needed. The tool validates costs, path and avoidance limits, and prevents enabling obstacle carving without enabling navigation-mesh influence. For a Region, first call `navigation_polygon_create`, then either use `navigation_polygon_geometry_set` with shared vertex arrays and convex polygon index arrays, or append outlines with `navigation_polygon_outline_set` and call `navigation_polygon_make_from_outlines`. Geometry and outlines are copied into a new embedded resource for each change, so external and shared NavigationPolygon resources are never edited in place. `navigation_polygon_outline_remove` and `navigation_polygon_clear` are undoable destructive operations. Scene-source geometry baking is intentionally deferred because it requires a separate asynchronous source-geometry workflow.

Create `PointLight2D`, `DirectionalLight2D`, and `LightOccluder2D` with `node_create`, then call their `*_get` tool before configuration. `light_2d_set` uses readable `blend_mode` (`add`, `subtract`, `mix`) and `shadow_filter` (`none`, `pcf5`, `pcf13`) values; `range_item_cull_layers` and `shadow_item_cull_layers` are arrays of layer numbers instead of raw masks. A Point light also accepts `texture_path` with an existing `res://` `Texture2D`, `offset`, and `texture_scale`; passing an empty `texture_path` clears its texture. A Directional light supports `max_distance`, and its `height` is constrained to 0 through 1. `light_occluder_2d_set` accepts `layers`, `sdf_collision`, and one closed or open `{points, closed, cull_mode}` polygon; `clear: true` detaches it. Polygon replacement always creates an independent embedded resource, so shared or external occluders are never mutated in place.

Create `Camera2D`, `Parallax2D`, `CanvasLayer`, and optionally `SubViewport` with `node_create`, then inspect them through their `*_get` tools. `camera_2d_set` accepts readable `anchor_mode` (`fixed_top_left`, `drag_center`) and `process_callback` (`physics`, `idle`) values, bounded drag margins and offsets, valid limits, positive zoom, and an optional `custom_viewport_path`. `parallax_2d_set` validates scroll limits, non-negative `repeat_size`, and repeat counts. `canvas_layer_set` supports viewport binding, layer order, follow settings, transform, and visibility; `transform` cannot be combined with `offset`, `rotation`, or `scale` in one request. For Camera2D and CanvasLayer, set `custom_viewport_path` to an empty string to return to the default viewport. Bindings must point to a `Viewport` or `SubViewport` in the current scene.

Create `Path2D` with `node_create`, then call `path_2d_get` to inspect its Curve2D and paginated Bézier points. Use `path_2d_curve_set` to replace the entire curve with up to 512 `{position, in, out}` points and a bounded `bake_interval`; omitted handles default to zero. `path_2d_curve_point_insert`, `path_2d_curve_point_set`, and `path_2d_curve_point_remove` operate on individual point indexes, while `path_2d_curve_clear` detaches the curve. Every write binds a copied, embedded Curve2D rather than modifying a shared or external resource, and each action is independently undoable.

Create a `Skeleton2D` with `node_create`, then create every `Bone2D` through `skeleton_2d_bone_create`. That tool assigns a valid identity or supplied `rest` transform before the bone enters the scene, supports an optional parent Bone2D path in the same skeleton, and creates local manual display geometry. Use `skeleton_2d_get` and `bone_2d_get` to inspect hierarchy and rest data. `bone_2d_set` updates one valid bone's `rest`, automatic-length switch, manual `length`, and `angle_degrees` atomically; manual geometry requires automatic calculation to be disabled. `skeleton_2d_reset_to_rest` applies existing rest transforms, while destructive `skeleton_2d_make_rest_from_current` replaces every rest pose from current local transforms. All operations reject PackedScene boundaries and support undo/redo.

Create `AudioStreamPlayer2D` with `node_create`, call `audio_stream_player_2d_get`, then configure it with `audio_stream_player_2d_set`. `stream_path` accepts an existing project `res://` `AudioStream` resource, while an empty string clears the binding; external resources are only referenced and never modified. The response lists usable buses, and `area_layers` uses human-readable values 1 through 32. Editing supports `volume_db`, `pitch_scale`, `autoplay`, `max_distance`, `attenuation`, `panning_strength`, `max_polyphony`, `bus`, and `playback_type` (`default`, `stream`, or `sample`) in one undoable transaction. Play, stop, seek, and playback position remain runtime controls and are intentionally deferred to the play-mode workflow.

Create `GPUParticles2D` with `node_create`, then use `gpu_particles_2d_get` before calling `gpu_particles_2d_set`. The semantic tool covers emission count and ratio, lifetime, preprocessing, time scale, one-shot/randomness/fixed-seed controls, interpolation, visibility rect, local coordinates, draw order, collision base size, and trail configuration. `texture_path` and `process_material_path` bind existing project `Texture2D` and `ParticleProcessMaterial`/`ShaderMaterial` resources, while empty strings clear them; these resources are never modified. `sub_emitter_path` binds another `GPUParticles2D` from the active scene using its stable node path, or clears it with an empty string. All supplied properties are applied in a single undoable transaction.

Create `CPUParticles2D` with `node_create`, then use `cpu_particles_2d_get` before calling `cpu_particles_2d_set`. The semantic tool covers emission amount and timing, fixed-seed controls, local drawing order, point/normal/color emission arrays, sphere/rectangle/ring geometry, direction, gravity, velocity, acceleration, damping, angle, scale, hue, animation offsets, and color. `texture_path` only binds an existing project `Texture2D`; an empty string clears it, and the resource is never modified. Every supplied property is applied in one undoable transaction.

Use `cpu_particles_2d_curve_get` to inspect any of the 14 parameter curves: `initial_velocity`, `angular_velocity`, `orbit_velocity`, `linear_accel`, `radial_accel`, `tangential_accel`, `damping`, `angle`, `scale_amount`, `scale_x`, `scale_y`, `hue_variation`, `anim_speed`, or `anim_offset`. `cpu_particles_2d_curve_bind` only attaches an existing project `Curve`; `cpu_particles_2d_curve_set` creates or duplicates an embedded Curve before applying bounded domain, range, bake-resolution, and point/tangent updates; `cpu_particles_2d_curve_clear` detaches it. `cpu_particles_2d_gradient_*` provides the same inspect, bind, copy-on-write edit, and clear workflow for `color` and `initial_color` ramps, including color stops and interpolation settings. External and shared Curve/Gradient resources are never modified in place, and every binding or replacement supports undo/redo.

Call `particle_process_material_2d_get` to inspect the material bound to a `GPUParticles2D`. `particle_process_material_2d_create` adds a new embedded 2D material and requires `replace_existing: true` before replacing an assigned material. `particle_process_material_2d_set` copies the assigned `ParticleProcessMaterial`, applies core 2D emission geometry, velocity, gravity, acceleration, scale, color, turbulence, collision, sub-emitter, and particle-flag settings to the copy, then atomically rebinds it. This preserves both external and shared material resources. The `inherit_emitter_scale` flag is exposed only on Godot versions that report it at runtime.

Use `particle_process_material_2d_curve_*` for scalar CurveTexture slots: `angle`, `angular_velocity`, `orbit_velocity`, `radial_velocity`, `velocity_limit`, `linear_accel`, `radial_accel`, `tangential_accel`, `damping`, `scale`, `scale_over_velocity`, `alpha`, `emission`, `hue_variation`, `anim_speed`, `anim_offset`, and `turbulence_influence_over_life`. Curve edits expose texture width/mode and the nested Curve domain, range, bake resolution, points, and tangent modes. `particle_process_material_2d_gradient_*` supplies the same inspect, bind, copy-on-write edit, and clear workflow for `color` and `initial_color`, including GradientTexture1D width/HDR and nested gradient stops/interpolation. Every mutation first copies the ParticleProcessMaterial and then copies the selected nested texture and Curve/Gradient before replacement, so external or shared resources at every level remain untouched and undo/redo remains complete.

Use `canvas_item_material_get` on any local `CanvasItem` such as `Node2D`, `Control`, `Sprite2D`, `Polygon2D`, or `Line2D`. `canvas_item_material_create` creates a new embedded material and requires `replace_existing: true` before replacing an assigned `ShaderMaterial` or other material. `canvas_item_material_bind` only attaches an existing project `CanvasItemMaterial`; it never edits that resource. `canvas_item_material_set` duplicates the assigned CanvasItemMaterial before applying blend mode (`mix`, `add`, `subtract`, `multiply`, `premultiplied_alpha`), light mode (`normal`, `unshaded`, `light_only`), and particle atlas animation settings. `canvas_item_material_clear` detaches the material. Every assignment and copy-on-write replacement is independently undoable.

Use `canvas_item_shader_get` before assigning a 2D shader to any local `CanvasItem`; it returns every Godot-discovered uniform, its runtime type, hint, current material override, and a `supported` flag. `canvas_item_shader_create` builds an embedded `ShaderMaterial` and `Shader`, and requires `replace_existing: true` when a material is already assigned. `canvas_item_shader_bind` only attaches an existing project `ShaderMaterial` whose Godot-parsed shader type is `canvas_item`; it never changes that resource. `canvas_item_shader_set` always duplicates the material and replaces the shader with a new embedded `canvas_item` source, so shared or external material and shader resources remain unchanged. `canvas_item_shader_uniforms_set` copies the material before atomically applying declared supported uniform values; `sampler2D` uniforms accept an existing `Texture2D` `res://` path. `canvas_item_shader_uniforms_clear` restores named uniforms to their shader defaults. Source is limited to 65,536 characters and embedded sources cannot use `#include`; bind a project resource for include-based shaders. Godot performs the final shader-type parse, while syntax/compiler diagnostics remain available in the editor's Output panel. `canvas_item_shader_clear` detaches the material. Every assignment and replacement is independently undoable.

For a `TileMapLayer`, call `tile_set_create`, then `tile_set_atlas_source_create` with an existing project `Texture2D` path, followed by `tile_set_atlas_tile_create` for every atlas grid tile used by the layer. `tile_set_layers_get` exposes the TileSet physics/navigation/occlusion layers, custom-data schema, and terrain definitions. Create those definitions before assigning `tile_set_atlas_tile_terrain_set`, `tile_set_atlas_tile_custom_data_set`, collision, navigation, or occlusion geometry; terrain peering directions are checked against the TileSet shape and terrain mode. `tile_set_atlas_tile_collision_set` atomically replaces every collision polygon on one physics layer and accepts optional one-way settings; an empty polygon list clears the layer. `tile_set_atlas_tile_navigation_set` atomically replaces a navigation layer with vertices and convex polygon indices, or clears it using `clear: true`. `tile_set_atlas_tile_occlusion_set` atomically replaces the `OccluderPolygon2D` resources for one occlusion layer; each polygon can be closed or open and specify its cull mode. `tile_set_atlas_tile_get` reads all three geometry families before mutation. `tile_map_layer_cells_set` accepts bounded, verified `{coords, source_id, atlas_coords, alternative_tile}` objects and rejects undefined source IDs, atlas coordinates, and alternatives. Cell reads and source reads are paginated. TileSet resource edits duplicate the resource before replacement so shared or external TileSets are not mutated in place; each direct cell batch and TileSet semantic edit uses one editor undo transaction. TileSet layer editing/removal and terrain painting remain future TileMap work.

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

Use `runtime_logs_get` with its `after_sequence` cursor to read logs from the game process. `runtime_screenshot_request` captures the running root viewport; poll `runtime_screenshot_get` for its bounded PNG or JPEG `data_base64` result, or call `runtime_screenshot_view` once ready to return a standard MCP image block for visual inspection. Screenshot bounds are limited to 1024 pixels per side and encoded output is limited to 1 MB to keep the editor bridge responsive. `runtime_input_send` accepts bounded `action`, `key`, `mouse_button`, and `mouse_motion` events; poll `runtime_input_result_get` for the game-side acknowledgement. Events use `Input.parse_input_event`, so they reach Godot's input pipeline but never control the host operating system.

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
