"""FastMCP application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

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

    @mcp.tool(annotations=WRITE)
    async def node_create(
        type: str,
        name: str = "",
        parent_path: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        """Create a ClassDB-backed 2D or UI node in the edited scene."""
        return await service.node_create(
            type_name=type,
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
        """Atomically set public properties after strict Godot Variant conversion."""
        return await service.node_set_properties(
            path=path,
            properties=properties,
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
