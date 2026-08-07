"""FastMCP application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult
from mcp.types import ImageContent, ToolAnnotations

from godot_2d_mcp.bridge import GodotWebSocketBridge
from godot_2d_mcp.service import GodotService
from godot_2d_mcp.sessions import SessionRegistry

INSTRUCTIONS = """Godot 2D editor integration. Inspect editor state before editing.
When multiple sessions are connected, activate the intended session before issuing commands.
Pass scene_file from editor_get_state to write tools when scene drift must be rejected.
Node changes participate in Godot undo/redo and remain unsaved until scene_save is called.
"""

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

DESTRUCTIVE_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)

SAVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)


@dataclass(slots=True)
class Application:
    mcp: FastMCP
    registry: SessionRegistry
    bridge: GodotWebSocketBridge
    service: GodotService


def create_application(
    ws_host: str = "127.0.0.1",
    ws_port: int = 9500,
    command_timeout: float = 10.0,
) -> Application:
    registry = SessionRegistry()
    bridge = GodotWebSocketBridge(
        registry=registry,
        host=ws_host,
        port=ws_port,
        command_timeout=command_timeout,
    )
    service = GodotService(registry, bridge)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        await bridge.start()
        try:
            yield {}
        finally:
            await bridge.stop()

    mcp = FastMCP("Godot 2D MCP", instructions=INSTRUCTIONS, lifespan=lifespan)

    @mcp.tool(annotations=READ_ONLY)
    async def session_list() -> dict[str, Any]:
        """List connected Godot editor sessions and their live state."""
        return await service.session_list()

    @mcp.tool(annotations=READ_ONLY)
    async def session_activate(session_id: str) -> dict[str, Any]:
        """Select the Godot editor session used by calls that omit session_id."""
        return await service.session_activate(session_id)

    @mcp.tool(annotations=READ_ONLY)
    async def editor_get_state(session_id: str | None = None) -> dict[str, Any]:
        """Read project, scene, play, import, and compatibility state from Godot."""
        return await service.editor_get_state(session_id)

    @mcp.tool(annotations=WRITE)
    async def editor_run(
        mode: str = "current",
        scene_file: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Start a project scene; poll editor_get_state for launch completion."""
        return await service.editor_run(mode=mode, scene_file=scene_file, session_id=session_id)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def editor_stop(session_id: str | None = None) -> dict[str, Any]:
        """Request that the currently running Godot scene stops; safe when no scene is running."""
        return await service.editor_stop(session_id=session_id)

    @mcp.tool(annotations=READ_ONLY)
    async def runtime_get_state(session_id: str | None = None) -> dict[str, Any]:
        """Read runtime-bridge availability, game-debugger connection, and pending feedback jobs."""
        return await service.runtime_get_state(session_id=session_id)

    @mcp.tool(annotations=READ_ONLY)
    async def runtime_logs_get(
        after_sequence: int = 0,
        limit: int = 100,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Read paginated logs emitted by the running game process, not the editor UI."""
        return await service.runtime_logs_get(
            after_sequence=after_sequence, limit=limit, session_id=session_id
        )

    @mcp.tool(annotations=WRITE)
    async def runtime_screenshot_request(
        format: str = "png",
        max_width: int = 640,
        max_height: int = 640,
        quality: float = 0.85,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Request a bounded screenshot from the running game's root viewport."""
        return await service.runtime_screenshot_request(
            format=format,
            max_width=max_width,
            max_height=max_height,
            quality=quality,
            session_id=session_id,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def runtime_screenshot_get(
        request_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        """Poll a requested runtime screenshot and receive bounded base64 image data when ready."""
        return await service.runtime_screenshot_get(request_id=request_id, session_id=session_id)

    @mcp.tool(annotations=READ_ONLY, output_schema=None)
    async def runtime_screenshot_view(request_id: str, session_id: str | None = None) -> ToolResult:
        """Return a completed runtime screenshot as a standard MCP image block."""
        screenshot = await service.runtime_screenshot_get(
            request_id=request_id, session_id=session_id
        )
        result = screenshot.get("result", {})
        if screenshot.get("status") != "ready" or result.get("ok") is not True:
            return ToolResult(structured_content=screenshot)
        metadata = {
            "request_id": request_id,
            "status": "ready",
            "width": result["width"],
            "height": result["height"],
            "byte_size": result["byte_size"],
            "mime_type": result["mime_type"],
        }
        return ToolResult(
            content=[
                ImageContent(
                    type="image",
                    data=result["data_base64"],
                    mimeType=result["mime_type"],
                )
            ],
            structured_content=metadata,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def runtime_screenshot_assert(
        request_id: str,
        assertions: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate bounded pixel assertions against a completed PNG runtime screenshot locally."""
        return await service.runtime_screenshot_assert(
            request_id=request_id, assertions=assertions, session_id=session_id
        )

    @mcp.tool(annotations=WRITE)
    async def runtime_input_send(
        events: list[dict[str, Any]], session_id: str | None = None
    ) -> dict[str, Any]:
        """Inject bounded action, keyboard, or mouse events into the game input pipeline."""
        return await service.runtime_input_send(events=events, session_id=session_id)

    @mcp.tool(annotations=READ_ONLY)
    async def runtime_input_result_get(
        request_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        """Poll whether a runtime input request reached and was accepted by the game."""
        return await service.runtime_input_result_get(request_id=request_id, session_id=session_id)

    @mcp.tool(annotations=WRITE)
    async def runtime_audio_stream_player_2d_control(
        path: str,
        action: str,
        position_seconds: float | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Request a running AudioStreamPlayer2D state query, play, stop, or seek action."""
        return await service.runtime_audio_stream_player_2d_control(
            path=path,
            action=action,
            position_seconds=position_seconds,
            session_id=session_id,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def runtime_audio_stream_player_2d_control_result_get(
        request_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        """Poll a runtime AudioStreamPlayer2D request for state or a structured error."""
        return await service.runtime_audio_stream_player_2d_control_result_get(
            request_id=request_id, session_id=session_id
        )

    @mcp.tool(annotations=WRITE)
    async def runtime_performance_sample_request(
        duration_seconds: float, session_id: str | None = None
    ) -> dict[str, Any]:
        """Start a bounded game-process performance sample; poll the paired result tool."""
        return await service.runtime_performance_sample_request(
            duration_seconds=duration_seconds, session_id=session_id
        )

    @mcp.tool(annotations=READ_ONLY)
    async def runtime_performance_sample_result_get(
        request_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        """Poll FPS, process delta, memory, object, and draw-call measurements from a sample."""
        return await service.runtime_performance_sample_result_get(
            request_id=request_id, session_id=session_id
        )

    @mcp.tool(annotations=WRITE)
    async def runtime_test_run(
        mode: str = "current",
        scene_file: str = "",
        inputs: list[dict[str, Any]] | None = None,
        settle_seconds: float = 0.25,
        performance_sample_seconds: float | None = None,
        screenshot: dict[str, Any] | None = None,
        screenshot_assertions: list[dict[str, Any]] | None = None,
        stop_when_finished: bool = True,
        timeout_seconds: float = 20.0,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a bounded scene test with optional input, metrics, PNG assertions, and cleanup."""
        return await service.runtime_test_run(
            mode=mode,
            scene_file=scene_file,
            inputs=inputs,
            settle_seconds=settle_seconds,
            performance_sample_seconds=performance_sample_seconds,
            screenshot=screenshot,
            screenshot_assertions=screenshot_assertions,
            stop_when_finished=stop_when_finished,
            timeout_seconds=timeout_seconds,
            session_id=session_id,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def scene_get_hierarchy(
        session_id: str | None = None,
        root_path: str = "",
        max_depth: int = 8,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Read a paginated preorder snapshot of the edited scene hierarchy."""
        return await service.scene_get_hierarchy(
            session_id=session_id,
            root_path=root_path,
            max_depth=max_depth,
            offset=offset,
            limit=limit,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def scene_create(
        scene_path: str,
        root_type: str = "Node2D",
        root_name: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and open a new project-local .tscn scene with a supported 2D or UI root."""
        return await service.scene_create(
            scene_path=scene_path,
            root_type=root_type,
            root_name=root_name,
            session_id=session_id,
        )

    @mcp.tool(annotations=WRITE)
    async def scene_open(
        scene_path: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Audit and open an existing project-local 2D or UI PackedScene in the editor."""
        return await service.scene_open(scene_path=scene_path, session_id=session_id)

    @mcp.tool(annotations=READ_ONLY)
    async def class_search(
        query: str = "",
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Search Godot classes allowed by the server's 2D node policy."""
        return await service.class_search(
            query=query,
            session_id=session_id,
            offset=offset,
            limit=limit,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def class_2d_coverage(
        query: str = "",
        scope: str = "all",
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Audit the current Godot build's supported 2D node and resource coverage."""
        return await service.class_2d_coverage(
            query=query,
            scope=scope,
            session_id=session_id,
            offset=offset,
            limit=limit,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def node_get_properties(
        path: str,
        fields: list[str] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read public properties and JSON-safe values for one supported 2D node."""
        return await service.node_get_properties(
            path=path,
            fields=fields,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def node_get_signals(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """List a 2D node's signals, typed arguments, and current scene connections."""
        return await service.node_get_signals(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def sprite_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read Sprite2D texture, frame-grid, region, flip, and offset configuration."""
        return await service.sprite_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def line_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read Line2D points, stroke, caps, joints, and project-local resources."""
        return await service.line_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def polygon_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read Polygon2D geometry, UVs, colors, texture mapping, and inversion settings."""
        return await service.polygon_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def animated_sprite_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read AnimatedSprite2D playback selection, presentation, and frame-resource metadata."""
        return await service.animated_sprite_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def sprite_frames_get(
        path: str,
        animation: str = "",
        frame_offset: int = 0,
        frame_limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read SpriteFrames summaries and a bounded frame page from an AnimatedSprite2D."""
        return await service.sprite_frames_get(
            path=path,
            animation=animation,
            frame_offset=frame_offset,
            frame_limit=frame_limit,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def button_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read persistent BaseButton state and matching visual button presentation."""
        return await service.button_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def button_menu_items_get(
        path: str,
        offset: int = 0,
        limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a paginated OptionButton or MenuButton item list and selection state."""
        return await service.button_menu_items_get(
            path=path,
            offset=offset,
            limit=limit,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def animation_list(
        player_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """List an AnimationPlayer's libraries and available animation summaries."""
        return await service.animation_list(
            player_path=player_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def animation_get(
        player_path: str,
        animation: str,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read one animation's tracks, typed property targets, and keyframes."""
        return await service.animation_get(
            player_path=player_path,
            animation=animation,
            library=library,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def control_get_layout(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read one Control's anchors, offsets, sizing, and container-layout status."""
        return await service.control_get_layout(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def container_2d_get(
        path: str,
        child_offset: int = 0,
        child_limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a Container's layout configuration and direct Control child constraints."""
        return await service.container_2d_get(
            path=path,
            child_offset=child_offset,
            child_limit=child_limit,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def tab_container_items_get(
        path: str,
        item_offset: int = 0,
        item_limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read paginated per-tab metadata from a local TabContainer."""
        return await service.tab_container_items_get(
            path=path,
            item_offset=item_offset,
            item_limit=item_limit,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def control_get_styleboxes(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read available Control stylebox states and local/effective flat-style values."""
        return await service.control_get_styleboxes(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def control_theme_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a Control's assigned Theme, defaults, and local Theme items."""
        return await service.control_theme_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def collision_shape_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a CollisionShape2D's Shape2D resource and one-way collision settings."""
        return await service.collision_shape_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def collision_object_get_layers(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read an Area2D or PhysicsBody2D collision layer and mask as layer-number lists."""
        return await service.collision_object_get_layers(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def area_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read Area2D monitoring, priority, gravity, and damping override configuration."""
        return await service.area_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def physics_body_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read the semantic configuration supported by a 2D physics body type."""
        return await service.physics_body_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def joint_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a PinJoint2D, GrooveJoint2D, or DampedSpringJoint2D configuration."""
        return await service.joint_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def ray_cast_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read the persistent query configuration of a RayCast2D node."""
        return await service.ray_cast_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def shape_cast_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read the persistent query configuration and Shape2D of a ShapeCast2D node."""
        return await service.shape_cast_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def navigation_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read the semantic configuration supported by a 2D navigation node."""
        return await service.navigation_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def navigation_polygon_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read the NavigationPolygon resource bound to a NavigationRegion2D."""
        return await service.navigation_polygon_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def navigation_polygon_bake_result_get(
        request_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        """Poll an asynchronous NavigationPolygon scene-source geometry bake request."""
        return await service.navigation_polygon_bake_result_get(
            request_id=request_id, session_id=session_id
        )

    @mcp.tool(annotations=READ_ONLY)
    async def camera_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read Camera2D framing, limits, smoothing, and viewport binding settings."""
        return await service.camera_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def parallax_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read Parallax2D scrolling, limits, and texture-repeat configuration."""
        return await service.parallax_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def canvas_layer_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read CanvasLayer drawing order, transform, visibility, and viewport settings."""
        return await service.canvas_layer_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def path_2d_get(
        path: str,
        offset: int = 0,
        limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a paginated Path2D Curve2D, including Bezier point handles and bake settings."""
        return await service.path_2d_get(
            path=path,
            offset=offset,
            limit=limit,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def skeleton_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a Skeleton2D's valid Bone2D hierarchy, rest poses, and display geometry."""
        return await service.skeleton_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def bone_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read one Bone2D's hierarchy status, rest pose, and length/angle configuration."""
        return await service.bone_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def audio_stream_player_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read persistent AudioStreamPlayer2D stream, bus, spatial, and playback settings."""
        return await service.audio_stream_player_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def gpu_particles_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read persistent GPUParticles2D emission, drawing, trail, and resource bindings."""
        return await service.gpu_particles_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def cpu_particles_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read persistent CPUParticles2D emission, movement, drawing, and texture settings."""
        return await service.cpu_particles_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def cpu_particles_2d_curve_get(
        path: str,
        curve: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Inspect one CPUParticles2D Curve resource, including all points and tangent modes."""
        return await service.cpu_particles_2d_curve_get(
            path=path,
            curve=curve,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def cpu_particles_2d_gradient_get(
        path: str,
        gradient: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Inspect one CPUParticles2D Gradient resource, including color stops and interpolation."""
        return await service.cpu_particles_2d_gradient_get(
            path=path,
            gradient=gradient,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def particle_process_material_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a GPUParticles2D process material and its 2D particle simulation settings."""
        return await service.particle_process_material_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def particle_process_material_2d_curve_get(
        path: str,
        curve: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Inspect a scalar CurveTexture assigned to a GPUParticles2D ParticleProcessMaterial."""
        return await service.particle_process_material_2d_curve_get(
            path=path,
            curve=curve,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def particle_process_material_2d_gradient_get(
        path: str,
        gradient: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Inspect a GradientTexture1D assigned to a GPUParticles2D ParticleProcessMaterial."""
        return await service.particle_process_material_2d_gradient_get(
            path=path,
            gradient=gradient,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def canvas_item_material_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Inspect a CanvasItem material and semantic CanvasItemMaterial configuration."""
        return await service.canvas_item_material_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def canvas_item_shader_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Inspect a CanvasItem material and its assigned 2D canvas_item shader source."""
        return await service.canvas_item_shader_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def light_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Inspect PointLight2D or DirectionalLight2D configuration using semantic values."""
        return await service.light_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def light_occluder_2d_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Inspect a LightOccluder2D mask, SDF setting, and assigned polygon."""
        return await service.light_occluder_2d_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def tile_map_layer_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read TileMapLayer cell usage and its bound TileSet summary."""
        return await service.tile_map_layer_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def tile_map_layer_cells_get(
        path: str,
        offset: int = 0,
        limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a stable, paginated list of TileMapLayer cell assignments."""
        return await service.tile_map_layer_cells_get(
            path=path,
            offset=offset,
            limit=limit,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def tile_set_get(
        path: str,
        offset: int = 0,
        limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read a TileMapLayer TileSet and its paginated source summaries."""
        return await service.tile_set_get(
            path=path,
            offset=offset,
            limit=limit,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def tile_set_layers_get(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read TileSet physics, navigation, custom-data, and terrain definitions."""
        return await service.tile_set_layers_get(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def tile_set_atlas_tile_get(
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Read collision and navigation geometry from an atlas tile or alternative."""
        return await service.tile_set_atlas_tile_get(
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            alternative_tile=alternative_tile,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def node_create(
        type: str,
        name: str = "",
        parent_path: str = "",
        script_path: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create a 2D/UI node and optionally attach a compatible project-local non-tool script."""
        return await service.node_create(
            type_name=type,
            name=name,
            parent_path=parent_path,
            script_path=script_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def node_script_bind(
        path: str,
        script_path: str,
        replace_existing: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Attach a compatible existing project-local non-tool Script to a local 2D/UI node."""
        return await service.node_script_bind(
            path=path,
            script_path=script_path,
            replace_existing=replace_existing,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def node_script_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach the script from a local 2D/UI node while retaining editor undo support."""
        return await service.node_script_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def node_instance_scene(
        scene_path: str,
        name: str = "",
        parent_path: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Instance a project-local 2D PackedScene while retaining its scene boundary."""
        return await service.node_instance_scene(
            scene_path=scene_path,
            name=name,
            parent_path=parent_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def node_set_properties(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically set typed public properties, including safe res:// resource references."""
        return await service.node_set_properties(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def sprite_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a Sprite2D with bounded frames and project-local textures."""
        return await service.sprite_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def line_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a Line2D with validated geometry and project-local resources."""
        return await service.line_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def polygon_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a triangulable Polygon2D with bounded visual data."""
        return await service.polygon_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def animated_sprite_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure an AnimatedSprite2D using an assigned SpriteFrames resource."""
        return await service.animated_sprite_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def button_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure BaseButton behavior and matching visual button properties."""
        return await service.button_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def button_menu_items_set(
        path: str,
        items: list[dict[str, Any]],
        selected_index: int | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically replace a flat OptionButton or MenuButton item list."""
        return await service.button_menu_items_set(
            path=path,
            items=items,
            selected_index=selected_index,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def button_menu_items_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove every flat OptionButton or MenuButton menu item in one undoable transaction."""
        return await service.button_menu_items_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def sprite_frames_animation_upsert(
        path: str,
        animation: str,
        speed: float | None = None,
        loop_mode: str | None = None,
        frames: list[dict[str, Any]] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create or replace one SpriteFrames animation using existing project-local textures."""
        return await service.sprite_frames_animation_upsert(
            path=path,
            animation=animation,
            speed=speed,
            loop_mode=loop_mode,
            frames=frames,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def sprite_frames_animation_rename(
        path: str,
        animation: str,
        new_name: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Rename one SpriteFrames animation and preserve matching node animation selections."""
        return await service.sprite_frames_animation_rename(
            path=path,
            animation=animation,
            new_name=new_name,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def sprite_frames_animation_remove(
        path: str,
        animation: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove one non-final SpriteFrames animation and restore a valid node selection."""
        return await service.sprite_frames_animation_remove(
            path=path,
            animation=animation,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def node_delete(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Delete a non-root node while retaining it in Godot undo history."""
        return await service.node_delete(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def node_rename(
        path: str,
        name: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Rename a local 2D node and migrate scene-local NodePath and animation references."""
        return await service.node_rename(
            path=path,
            name=name,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def node_duplicate(
        path: str,
        name: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Duplicate a local 2D node subtree into its current parent and retain undo support."""
        return await service.node_duplicate(
            path=path,
            name=name,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def node_reparent(
        path: str,
        new_parent_path: str,
        index: int | None = None,
        keep_global_transform: bool = True,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Move a local node under a new 2D parent while preserving paths and visual placement."""
        return await service.node_reparent(
            path=path,
            new_parent_path=new_parent_path,
            index=index,
            keep_global_transform=keep_global_transform,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def node_move(
        path: str,
        index: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Reorder a local node among siblings without changing its parent or references."""
        return await service.node_move(
            path=path,
            index=index,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def signal_connect(
        source_path: str,
        signal: str,
        target_path: str,
        method: str,
        binds: list[Any] | None = None,
        deferred: bool = False,
        one_shot: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create a persistent, undoable connection between local 2D scene nodes."""
        return await service.signal_connect(
            source_path=source_path,
            signal=signal,
            target_path=target_path,
            method=method,
            binds=binds,
            deferred=deferred,
            one_shot=one_shot,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def signal_disconnect(
        source_path: str,
        signal: str,
        target_path: str,
        method: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove one persistent local-node connection while retaining undo support."""
        return await service.signal_disconnect(
            source_path=source_path,
            signal=signal,
            target_path=target_path,
            method=method,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def animation_create(
        player_path: str,
        animation: str,
        length: float = 0.2,
        loop_mode: str = "none",
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create a persistent scene-embedded Animation resource."""
        return await service.animation_create(
            player_path=player_path,
            animation=animation,
            length=length,
            loop_mode=loop_mode,
            library=library,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def animation_delete(
        player_path: str,
        animation: str,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Delete one persistent animation while preserving editor undo support."""
        return await service.animation_delete(
            player_path=player_path,
            animation=animation,
            library=library,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def animation_track_upsert(
        player_path: str,
        animation: str,
        target_path: str,
        property: str,
        keys: list[dict[str, Any]],
        interpolation: str = "linear",
        update_mode: str = "continuous",
        enabled: bool = True,
        loop_wrap: bool = True,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create or replace a local 2D/UI property value track atomically."""
        return await service.animation_track_upsert(
            player_path=player_path,
            animation=animation,
            target_path=target_path,
            property=property,
            keys=keys,
            interpolation=interpolation,
            update_mode=update_mode,
            enabled=enabled,
            loop_wrap=loop_wrap,
            library=library,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def animation_track_delete(
        player_path: str,
        animation: str,
        track_index: int,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Delete one animation track while preserving editor undo support."""
        return await service.animation_track_delete(
            player_path=player_path,
            animation=animation,
            track_index=track_index,
            library=library,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def animation_key_upsert(
        player_path: str,
        animation: str,
        track_index: int,
        time: float,
        value: Any,
        transition: float = 1.0,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create or replace one key on a local property value track."""
        return await service.animation_key_upsert(
            player_path=player_path,
            animation=animation,
            track_index=track_index,
            time=time,
            value=value,
            transition=transition,
            library=library,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def animation_key_delete(
        player_path: str,
        animation: str,
        track_index: int,
        time: float,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Delete one key at an exact time on a local property value track."""
        return await service.animation_key_delete(
            player_path=player_path,
            animation=animation,
            track_index=track_index,
            time=time,
            library=library,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def control_set_layout(
        path: str,
        anchors: dict[str, float] | None = None,
        offsets: dict[str, float] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically set exact anchors and/or offsets on a local non-Container Control."""
        return await service.control_set_layout(
            path=path,
            anchors=anchors,
            offsets=offsets,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def container_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure one local Container's supported layout behavior."""
        return await service.container_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tab_container_item_set(
        path: str,
        child_path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically update one direct TabContainer child's tab metadata."""
        return await service.tab_container_item_set(
            path=path,
            child_path=child_path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def container_child_layout_set(
        path: str,
        child_path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Set one direct Container child's minimum size, flags, and stretch ratio."""
        return await service.container_child_layout_set(
            path=path,
            child_path=child_path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def control_set_layout_preset(
        path: str,
        preset: str,
        resize_mode: str = "min_size",
        margin: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Apply a named Godot layout preset while retaining editor undo support."""
        return await service.control_set_layout_preset(
            path=path,
            preset=preset,
            resize_mode=resize_mode,
            margin=margin,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def control_stylebox_flat_upsert(
        path: str,
        state: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create or replace one local StyleBoxFlat theme override on a Control."""
        return await service.control_stylebox_flat_upsert(
            path=path,
            state=state,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def control_stylebox_override_clear(
        path: str,
        state: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove one local stylebox override while retaining editor undo support."""
        return await service.control_stylebox_override_clear(
            path=path,
            state=state,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def control_theme_create(
        path: str,
        resource_name: str = "",
        replace: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create and assign one embedded, undoable Theme to a local Control."""
        return await service.control_theme_create(
            path=path,
            resource_name=resource_name,
            replace=replace,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def control_theme_assign(
        path: str,
        theme_path: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Assign an existing res:// Theme, or clear the local assignment with an empty path."""
        return await service.control_theme_assign(
            path=path,
            theme_path=theme_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def control_theme_defaults_set(
        path: str,
        font: dict[str, Any] | None = None,
        font_size: int | None = None,
        base_scale: float | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Set one or more embedded Theme defaults, including a project or system font."""
        return await service.control_theme_defaults_set(
            path=path,
            font=font,
            font_size=font_size,
            base_scale=base_scale,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def control_theme_defaults_clear(
        path: str,
        defaults: list[str],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Clear selected embedded Theme defaults while retaining editor undo support."""
        return await service.control_theme_defaults_clear(
            path=path,
            defaults=defaults,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def control_theme_item_upsert(
        path: str,
        item_type: str,
        theme_type: str,
        name: str,
        value: Any,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create or replace a color, constant, font, icon, or StyleBoxFlat Theme item."""
        return await service.control_theme_item_upsert(
            path=path,
            item_type=item_type,
            theme_type=theme_type,
            name=name,
            value=value,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def control_theme_item_clear(
        path: str,
        item_type: str,
        theme_type: str,
        name: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Clear one local item from an embedded Theme while retaining editor undo support."""
        return await service.control_theme_item_clear(
            path=path,
            item_type=item_type,
            theme_type=theme_type,
            name=name,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def collision_shape_set(
        path: str,
        shape_type: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create or replace an embedded Circle, Polygon, Ray, or other built-in Shape2D."""
        return await service.collision_shape_set(
            path=path,
            shape_type=shape_type,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def collision_shape_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach a CollisionShape2D's Shape2D resource while retaining editor undo support."""
        return await service.collision_shape_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def collision_object_set_layers(
        path: str,
        layers: list[int] | None = None,
        masks: list[int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Set an Area2D or PhysicsBody2D collision layer and/or mask with numbers 1 through 32."""
        return await service.collision_object_set_layers(
            path=path,
            layers=layers,
            masks=masks,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def area_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically set allowed Area2D monitoring, gravity, and damping configuration."""
        return await service.area_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def physics_body_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically set allowed Static, Animatable, Character, or RigidBody2D configuration."""
        return await service.physics_body_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def joint_2d_set(
        path: str,
        properties: dict[str, Any] | None = None,
        node_a_path: str | None = None,
        node_b_path: str | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a supported 2D joint and its stable scene-path endpoints."""
        return await service.joint_2d_set(
            path=path,
            properties=properties,
            node_a_path=node_a_path,
            node_b_path=node_b_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def ray_cast_2d_set(
        path: str,
        properties: dict[str, Any] | None = None,
        masks: list[int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure RayCast2D behavior and its collision-mask layer numbers."""
        return await service.ray_cast_2d_set(
            path=path,
            properties=properties,
            masks=masks,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def shape_cast_2d_set(
        path: str,
        properties: dict[str, Any] | None = None,
        masks: list[int] | None = None,
        shape_type: str | None = None,
        shape_properties: dict[str, Any] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure ShapeCast2D behavior and optionally replace its embedded Shape2D."""
        return await service.shape_cast_2d_set(
            path=path,
            properties=properties,
            masks=masks,
            shape_type=shape_type,
            shape_properties=shape_properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def shape_cast_2d_shape_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach a ShapeCast2D Shape2D resource while retaining editor undo support."""
        return await service.shape_cast_2d_shape_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def navigation_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically set allowed Region, Agent, Obstacle, or Link 2D navigation configuration."""
        return await service.navigation_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def navigation_polygon_create(
        path: str,
        agent_radius: float = 0.0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create and bind a new embedded NavigationPolygon to a NavigationRegion2D."""
        return await service.navigation_polygon_create(
            path=path,
            agent_radius=agent_radius,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def navigation_polygon_geometry_set(
        path: str,
        vertices: list[dict[str, float | int]],
        polygons: list[list[int]],
        agent_radius: float | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Replace NavigationPolygon vertices and convex polygon index arrays atomically."""
        return await service.navigation_polygon_geometry_set(
            path=path,
            vertices=vertices,
            polygons=polygons,
            agent_radius=agent_radius,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def navigation_polygon_outline_set(
        path: str,
        outline: list[dict[str, float | int]],
        index: int | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Append or replace one NavigationPolygon outline without mutating shared resources."""
        return await service.navigation_polygon_outline_set(
            path=path,
            outline=outline,
            index=index,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def navigation_polygon_outline_remove(
        path: str,
        index: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove one NavigationPolygon outline while retaining editor undo support."""
        return await service.navigation_polygon_outline_remove(
            path=path,
            index=index,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def navigation_polygon_make_from_outlines(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Build NavigationPolygon convex polygons from its existing outlines."""
        return await service.navigation_polygon_make_from_outlines(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def navigation_polygon_bake_request(
        path: str,
        source_root_path: str = "",
        settings: dict[str, Any] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Start an asynchronous scene-source geometry bake for one NavigationPolygon."""
        return await service.navigation_polygon_bake_request(
            path=path,
            source_root_path=source_root_path,
            settings=settings,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def navigation_polygon_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach the NavigationPolygon resource from a NavigationRegion2D."""
        return await service.navigation_polygon_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def camera_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a Camera2D using readable enums and typed 2D values."""
        return await service.camera_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def parallax_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a Parallax2D node using typed scrolling values."""
        return await service.parallax_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def canvas_layer_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a CanvasLayer without ambiguous transform combinations."""
        return await service.canvas_layer_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def path_2d_curve_set(
        path: str,
        points: list[dict[str, Any]],
        bake_interval: float = 5.0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Replace a Path2D curve with an independent embedded Curve2D resource."""
        return await service.path_2d_curve_set(
            path=path,
            points=points,
            bake_interval=bake_interval,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def path_2d_curve_point_insert(
        path: str,
        point: dict[str, Any],
        index: int | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Insert a Bezier point into a Path2D curve without mutating a shared resource."""
        return await service.path_2d_curve_point_insert(
            path=path,
            point=point,
            index=index,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def path_2d_curve_point_set(
        path: str,
        index: int,
        point: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Replace one Path2D Curve2D point and both of its Bezier handles atomically."""
        return await service.path_2d_curve_point_set(
            path=path,
            index=index,
            point=point,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def path_2d_curve_point_remove(
        path: str,
        index: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove one Path2D curve point while retaining editor undo support."""
        return await service.path_2d_curve_point_remove(
            path=path,
            index=index,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def path_2d_curve_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach the Curve2D resource from a Path2D while retaining editor undo support."""
        return await service.path_2d_curve_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def skeleton_2d_bone_create(
        path: str,
        name: str = "",
        parent_bone_path: str = "",
        rest: dict[str, Any] | None = None,
        length: float = 16.0,
        angle_degrees: float = 0.0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create a local Bone2D under a Skeleton2D with a valid initial rest transform."""
        return await service.skeleton_2d_bone_create(
            path=path,
            name=name,
            parent_bone_path=parent_bone_path,
            rest=rest,
            length=length,
            angle_degrees=angle_degrees,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def bone_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure one Bone2D's rest pose or manual display geometry."""
        return await service.bone_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def skeleton_2d_reset_to_rest(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Set every Bone2D transform in a Skeleton2D to its existing rest pose."""
        return await service.skeleton_2d_reset_to_rest(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def skeleton_2d_make_rest_from_current(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Overwrite every Skeleton2D Bone2D rest pose with its current local transform."""
        return await service.skeleton_2d_make_rest_from_current(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def audio_stream_player_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a local AudioStreamPlayer2D without mutating its stream resource."""
        return await service.audio_stream_player_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def gpu_particles_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a local GPUParticles2D without mutating assigned resources."""
        return await service.gpu_particles_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def cpu_particles_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a local CPUParticles2D without modifying its texture resource."""
        return await service.cpu_particles_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def cpu_particles_2d_curve_bind(
        path: str,
        curve: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Bind an existing project Curve resource to one CPUParticles2D curve slot."""
        return await service.cpu_particles_2d_curve_bind(
            path=path,
            curve=curve,
            resource_path=resource_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def cpu_particles_2d_curve_set(
        path: str,
        curve: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy, update, and rebind one CPUParticles2D Curve resource atomically."""
        return await service.cpu_particles_2d_curve_set(
            path=path,
            curve=curve,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def cpu_particles_2d_curve_clear(
        path: str,
        curve: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach one CPUParticles2D Curve resource while retaining editor undo support."""
        return await service.cpu_particles_2d_curve_clear(
            path=path,
            curve=curve,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def cpu_particles_2d_gradient_bind(
        path: str,
        gradient: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Bind an existing project Gradient resource to one CPUParticles2D gradient slot."""
        return await service.cpu_particles_2d_gradient_bind(
            path=path,
            gradient=gradient,
            resource_path=resource_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def cpu_particles_2d_gradient_set(
        path: str,
        gradient: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy, update, and rebind one CPUParticles2D Gradient resource atomically."""
        return await service.cpu_particles_2d_gradient_set(
            path=path,
            gradient=gradient,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def cpu_particles_2d_gradient_clear(
        path: str,
        gradient: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach one CPUParticles2D Gradient resource while retaining editor undo support."""
        return await service.cpu_particles_2d_gradient_clear(
            path=path,
            gradient=gradient,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def particle_process_material_2d_create(
        path: str,
        replace_existing: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Attach a new embedded ParticleProcessMaterial to a local GPUParticles2D node."""
        return await service.particle_process_material_2d_create(
            path=path,
            replace_existing=replace_existing,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def particle_process_material_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy, update, and rebind a GPUParticles2D ParticleProcessMaterial atomically."""
        return await service.particle_process_material_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def particle_process_material_2d_curve_bind(
        path: str,
        curve: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Bind an existing CurveTexture to one scalar ParticleProcessMaterial curve slot."""
        return await service.particle_process_material_2d_curve_bind(
            path=path,
            curve=curve,
            resource_path=resource_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def particle_process_material_2d_curve_set(
        path: str,
        curve: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy, update, and rebind one scalar ParticleProcessMaterial CurveTexture."""
        return await service.particle_process_material_2d_curve_set(
            path=path,
            curve=curve,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def particle_process_material_2d_curve_clear(
        path: str,
        curve: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach one scalar ParticleProcessMaterial CurveTexture with editor undo support."""
        return await service.particle_process_material_2d_curve_clear(
            path=path,
            curve=curve,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def particle_process_material_2d_gradient_bind(
        path: str,
        gradient: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Bind an existing GradientTexture1D to a ParticleProcessMaterial color ramp."""
        return await service.particle_process_material_2d_gradient_bind(
            path=path,
            gradient=gradient,
            resource_path=resource_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def particle_process_material_2d_gradient_set(
        path: str,
        gradient: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy, update, and rebind one ParticleProcessMaterial GradientTexture1D."""
        return await service.particle_process_material_2d_gradient_set(
            path=path,
            gradient=gradient,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def particle_process_material_2d_gradient_clear(
        path: str,
        gradient: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach one ParticleProcessMaterial GradientTexture1D with editor undo support."""
        return await service.particle_process_material_2d_gradient_clear(
            path=path,
            gradient=gradient,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def canvas_item_material_create(
        path: str,
        replace_existing: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Attach a new embedded CanvasItemMaterial to a local CanvasItem node."""
        return await service.canvas_item_material_create(
            path=path,
            replace_existing=replace_existing,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def canvas_item_material_bind(
        path: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Bind an existing project CanvasItemMaterial without modifying the resource."""
        return await service.canvas_item_material_bind(
            path=path,
            resource_path=resource_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def canvas_item_material_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy, configure, and rebind a CanvasItemMaterial atomically."""
        return await service.canvas_item_material_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def canvas_item_material_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach a CanvasItem material while retaining editor undo support."""
        return await service.canvas_item_material_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def canvas_item_shader_create(
        path: str,
        source: str = "shader_type canvas_item;\n",
        replace_existing: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Attach an embedded ShaderMaterial containing a 2D canvas_item shader."""
        return await service.canvas_item_shader_create(
            path=path,
            source=source,
            replace_existing=replace_existing,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def canvas_item_shader_bind(
        path: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Bind an existing canvas_item ShaderMaterial without modifying its resource."""
        return await service.canvas_item_shader_bind(
            path=path,
            resource_path=resource_path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def canvas_item_shader_set(
        path: str,
        source: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy a ShaderMaterial, replace its source with a 2D canvas_item shader, and rebind it."""
        return await service.canvas_item_shader_set(
            path=path,
            source=source,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def canvas_item_shader_uniforms_set(
        path: str,
        values: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy a 2D ShaderMaterial and atomically set declared shader uniform overrides."""
        return await service.canvas_item_shader_uniforms_set(
            path=path,
            values=values,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def canvas_item_shader_uniforms_clear(
        path: str,
        names: list[str],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Copy a 2D ShaderMaterial and clear declared uniform overrides to shader defaults."""
        return await service.canvas_item_shader_uniforms_clear(
            path=path,
            names=names,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def canvas_item_shader_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach a CanvasItem material while retaining editor undo support."""
        return await service.canvas_item_shader_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def light_2d_set(
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a PointLight2D or DirectionalLight2D with safe semantic values."""
        return await service.light_2d_set(
            path=path,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def light_occluder_2d_set(
        path: str,
        layers: list[int] | None = None,
        sdf_collision: bool | None = None,
        polygon: dict[str, Any] | None = None,
        clear: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically configure a LightOccluder2D and replace or clear its embedded polygon."""
        return await service.light_occluder_2d_set(
            path=path,
            layers=layers,
            sdf_collision=sdf_collision,
            polygon=polygon,
            clear=clear,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_create(
        path: str,
        tile_size: dict[str, int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create and bind an embedded TileSet to a TileMapLayer."""
        return await service.tile_set_create(
            path=path,
            tile_size=tile_size,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def tile_set_clear(
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Detach a TileSet from a TileMapLayer while retaining editor undo support."""
        return await service.tile_set_clear(
            path=path,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_atlas_source_create(
        path: str,
        texture_path: str,
        source_id: int | None = None,
        texture_region_size: dict[str, int] | None = None,
        margins: dict[str, int] | None = None,
        separation: dict[str, int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Add an embedded TileSetAtlasSource using an existing project Texture2D."""
        return await service.tile_set_atlas_source_create(
            path=path,
            texture_path=texture_path,
            source_id=source_id,
            texture_region_size=texture_region_size,
            margins=margins,
            separation=separation,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_atlas_tile_create(
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        size: dict[str, int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create one base atlas tile in a TileSetAtlasSource."""
        return await service.tile_set_atlas_tile_create(
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            size=size,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_physics_layer_create(
        path: str,
        layers: list[int] | None = None,
        masks: list[int] | None = None,
        priority: float = 1.0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Add a TileSet physics layer with collision layers, masks, and priority."""
        return await service.tile_set_physics_layer_create(
            path=path,
            layers=layers,
            masks=masks,
            priority=priority,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_navigation_layer_create(
        path: str,
        layers: list[int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Add a TileSet navigation layer using Godot navigation-layer numbers 1 through 32."""
        return await service.tile_set_navigation_layer_create(
            path=path,
            layers=layers,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_occlusion_layer_create(
        path: str,
        layers: list[int] | None = None,
        sdf_collision: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Add a TileSet occlusion layer with light-mask layers and SDF collision mode."""
        return await service.tile_set_occlusion_layer_create(
            path=path,
            layers=layers,
            sdf_collision=sdf_collision,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_custom_data_layer_create(
        path: str,
        name: str,
        value_type: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Add a named TileSet custom-data layer with an explicit Variant type."""
        return await service.tile_set_custom_data_layer_create(
            path=path,
            name=name,
            value_type=value_type,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_layer_set(
        path: str,
        kind: str,
        index: int,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically update one existing TileSet layer definition."""
        return await service.tile_set_layer_set(
            path=path,
            kind=kind,
            index=index,
            properties=properties,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def tile_set_layer_remove(
        path: str,
        kind: str,
        index: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove one TileSet layer definition and reindex remaining layer data."""
        return await service.tile_set_layer_remove(
            path=path,
            kind=kind,
            index=index,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_terrain_set_create(
        path: str,
        mode: str = "match_corners_and_sides",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Add a TileSet terrain set with one of Godot's supported matching modes."""
        return await service.tile_set_terrain_set_create(
            path=path,
            mode=mode,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_terrain_create(
        path: str,
        terrain_set: int,
        name: str = "",
        color: Any | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Add a named, colored terrain definition to an existing TileSet terrain set."""
        return await service.tile_set_terrain_create(
            path=path,
            terrain_set=terrain_set,
            name=name,
            color=color,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def tile_set_terrain_set_remove(
        path: str,
        terrain_set: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove one TileSet terrain set and reindex remaining terrain-set data."""
        return await service.tile_set_terrain_set_remove(
            path=path,
            terrain_set=terrain_set,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def tile_set_terrain_remove(
        path: str,
        terrain_set: int,
        terrain: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Remove one terrain definition from an existing TileSet terrain set."""
        return await service.tile_set_terrain_remove(
            path=path,
            terrain_set=terrain_set,
            terrain=terrain,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_atlas_alternative_create(
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        alternative_tile: int | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create an alternative version of an existing TileSet atlas tile."""
        return await service.tile_set_atlas_alternative_create(
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            alternative_tile=alternative_tile,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_atlas_tile_terrain_set(
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        terrain_set: int,
        terrain: int,
        peering_bits: dict[str, int] | None = None,
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Configure terrain IDs and optional peering bits for an atlas tile or alternative."""
        return await service.tile_set_atlas_tile_terrain_set(
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            terrain_set=terrain_set,
            terrain=terrain,
            peering_bits=peering_bits,
            alternative_tile=alternative_tile,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_atlas_tile_custom_data_set(
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        values: dict[str, Any],
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Set typed custom-data values for an atlas tile or alternative."""
        return await service.tile_set_atlas_tile_custom_data_set(
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            values=values,
            alternative_tile=alternative_tile,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_atlas_tile_collision_set(
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        physics_layer: int,
        polygons: list[dict[str, Any]],
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically replace collision polygons for one atlas-tile physics layer."""
        return await service.tile_set_atlas_tile_collision_set(
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            physics_layer=physics_layer,
            polygons=polygons,
            alternative_tile=alternative_tile,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_atlas_tile_navigation_set(
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        navigation_layer: int,
        vertices: list[dict[str, float | int]] | None = None,
        polygons: list[list[int]] | None = None,
        agent_radius: float | None = None,
        clear: bool = False,
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Replace or clear the NavigationPolygon on one atlas-tile navigation layer."""
        return await service.tile_set_atlas_tile_navigation_set(
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            navigation_layer=navigation_layer,
            vertices=vertices,
            polygons=polygons,
            agent_radius=agent_radius,
            clear=clear,
            alternative_tile=alternative_tile,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_set_atlas_tile_occlusion_set(
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        occlusion_layer: int,
        polygons: list[dict[str, Any]],
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically replace OccluderPolygon2D resources on one atlas-tile layer."""
        return await service.tile_set_atlas_tile_occlusion_set(
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            occlusion_layer=occlusion_layer,
            polygons=polygons,
            alternative_tile=alternative_tile,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_map_layer_cells_set(
        path: str,
        cells: list[dict[str, Any]],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Atomically assign verified TileSet atlas tiles to TileMapLayer cells."""
        return await service.tile_map_layer_cells_set(
            path=path,
            cells=cells,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=WRITE)
    async def tile_map_layer_terrain_paint(
        path: str,
        coords: list[dict[str, int]],
        terrain_set: int,
        terrain: int,
        strategy: str = "connect",
        ignore_empty_terrains: bool = True,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Paint configured TileSet terrain into adjacent TileMapLayer cells."""
        return await service.tile_map_layer_terrain_paint(
            path=path,
            coords=coords,
            terrain_set=terrain_set,
            terrain=terrain,
            strategy=strategy,
            ignore_empty_terrains=ignore_empty_terrains,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=DESTRUCTIVE_WRITE)
    async def tile_map_layer_cells_clear(
        path: str,
        coords: list[dict[str, int]],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Clear selected TileMapLayer cells while retaining editor undo support."""
        return await service.tile_map_layer_cells_clear(
            path=path,
            coords=coords,
            session_id=session_id,
            scene_file=scene_file,
        )

    @mcp.tool(annotations=SAVE)
    async def scene_save(
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Save the active scene to its existing res:// file path."""
        return await service.scene_save(session_id=session_id, scene_file=scene_file)

    @mcp.tool(annotations=WRITE)
    async def scene_undo(
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Undo the latest action in the active scene's editor history."""
        return await service.scene_undo(session_id=session_id, scene_file=scene_file)

    @mcp.tool(annotations=WRITE)
    async def scene_redo(
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Redo the next action in the active scene's editor history."""
        return await service.scene_redo(session_id=session_id, scene_file=scene_file)

    return Application(mcp=mcp, registry=registry, bridge=bridge, service=service)
