# Godot 2D MCP

Godot 2D MCP connects Codex, Claude Code, and other MCP clients to a live Godot editor. The project is designed for comprehensive Godot 2D authoring while keeping editor mutations on Godot's main thread and inside its undo/redo system.

The current `0.21.0` preview adds safe `AudioStreamPlayer2D` authoring to scene, signal, animation, UI, Theme, collision, query, navigation, lighting, TileMap, viewport composition, path, and skeleton editing. Agents can configure existing audio streams and spatial playback settings while retaining Godot-native undo and save behavior.

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
