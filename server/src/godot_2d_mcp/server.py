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
