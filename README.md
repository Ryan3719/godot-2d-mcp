# Godot 2D MCP

Godot 2D MCP connects Codex, Claude Code, and other MCP clients to a live Godot editor. The project is designed for comprehensive Godot 2D authoring while keeping editor mutations on Godot's main thread and inside its undo/redo system.

The current `0.3.0` preview adds safe 2D scene-structure editing. Agents can inspect a live scene, create, rename, duplicate, reparent, reorder, and delete supported 2D and UI nodes, update public properties, use the editor's undo/redo history, and explicitly save the scene.

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
- `node_create`, `node_set_properties`, `node_delete`, `node_rename`, `node_duplicate`, `node_reparent`, and `node_move` with scene-file guards.
- Scene-local `NodePath` property and built-in `AnimationPlayer` track migration during rename and reparent.
- Reparenting preserves global placement for `Node2D` and `Control` by default.
- `scene_undo`, `scene_redo`, and `scene_save` through Godot editor APIs.
- Atomic multi-property updates registered with `EditorUndoRedoManager`.
- Strict 2D Variant conversion for `Vector2`, `Vector2i`, `Rect2`, `Rect2i`, `Transform2D`, `Color`, arrays, dictionaries, and common packed arrays.
- Real Godot 4.7 smoke coverage for create, update, rename, duplicate, reparent, reorder, undo, redo, delete, restore, animation-track migration, and save.

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

This preview creates built-in `ClassDB` node types only. It rejects structure edits that cross a PackedScene boundary or contain unsupported 3D nodes, deletions that would leave direct `NodePath` or animation-track references dangling, and renames or reparents requiring changes to external animation resources. Custom script nodes, PackedScene instances, resource assignment, signals, and semantic animation-authoring tools remain on the staged roadmap.

`node_rename` and `node_reparent` migrate direct scene-local `NodePath` properties plus tracks stored in built-in `AnimationPlayer` animations. The returned migration counts make that work visible to the caller. `node_reparent` accepts an optional sibling `index` and defaults `keep_global_transform` to `true`; set it to `false` when the node should inherit its new parent's visual transform instead.

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
