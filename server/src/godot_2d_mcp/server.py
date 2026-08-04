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
