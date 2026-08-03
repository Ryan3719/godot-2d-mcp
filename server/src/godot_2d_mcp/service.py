"""Application service exposed through MCP tools."""

from __future__ import annotations

from typing import Any, Protocol

from godot_2d_mcp.sessions import SessionRegistry


class CommandBridge(Protocol):
    async def call(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]: ...


class GodotService:
    """Small typed boundary between MCP tools and Godot RPC commands."""

    def __init__(self, registry: SessionRegistry, bridge: CommandBridge) -> None:
        self.registry = registry
        self.bridge = bridge

    async def session_list(self) -> dict[str, Any]:
        sessions = await self.registry.list_sessions()
        return {"sessions": sessions, "count": len(sessions)}

    async def session_activate(self, session_id: str) -> dict[str, Any]:
        session = await self.registry.activate(session_id)
        return {
            "session_id": session.session_id,
            "project_name": session.project_name,
            "project_path": session.project_path,
        }

    async def editor_get_state(self, session_id: str | None = None) -> dict[str, Any]:
        return await self.bridge.call("editor_get_state", session_id=session_id)

    async def scene_get_hierarchy(
        self,
        session_id: str | None = None,
        root_path: str = "",
        max_depth: int = 8,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        if not 0 <= max_depth <= 64:
            raise ValueError("max_depth must be between 0 and 64")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        return await self.bridge.call(
            "scene_get_hierarchy",
            {
                "root_path": root_path,
                "max_depth": max_depth,
                "offset": offset,
                "limit": limit,
            },
            session_id=session_id,
        )

    async def class_search(
        self,
        query: str = "",
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        return await self.bridge.call(
            "class_search",
            {"query": query, "offset": offset, "limit": limit},
            session_id=session_id,
        )

    async def node_get_properties(
        self,
        path: str,
        fields: list[str] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        selected_fields = fields or []
        if len(selected_fields) > 100:
            raise ValueError("fields can contain at most 100 property names")
        if any(not field or len(field) > 256 for field in selected_fields):
            raise ValueError("field names must contain between 1 and 256 characters")
        return await self.bridge.call(
            "node_get_properties",
            _scene_params(scene_file, path=path, fields=selected_fields),
            session_id=session_id,
        )

    async def node_create(
        self,
        type_name: str,
        name: str = "",
        parent_path: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        if not type_name or len(type_name) > 256:
            raise ValueError("type must contain between 1 and 256 characters")
        if len(name) > 256:
            raise ValueError("name cannot exceed 256 characters")
        if parent_path:
            _validate_node_path(parent_path)
        return await self.bridge.call(
            "node_create",
            _scene_params(
                scene_file,
                type=type_name,
                name=name,
                parent_path=parent_path,
            ),
            session_id=session_id,
        )

    async def node_set_properties(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if not properties:
            raise ValueError("properties must be non-empty")
        if len(properties) > 64:
            raise ValueError("properties can contain at most 64 entries")
        if any(not key or len(key) > 256 for key in properties):
            raise ValueError("property names must contain between 1 and 256 characters")
        return await self.bridge.call(
            "node_set_properties",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def node_delete(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "node_delete",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def scene_save(
        self,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        return await self.bridge.call(
            "scene_save",
            _scene_params(scene_file),
            session_id=session_id,
        )

    async def scene_undo(
        self,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        return await self.bridge.call(
            "scene_undo",
            _scene_params(scene_file),
            session_id=session_id,
        )

    async def scene_redo(
        self,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        return await self.bridge.call(
            "scene_redo",
            _scene_params(scene_file),
            session_id=session_id,
        )


def _validate_node_path(path: str) -> None:
    if not path or len(path) > 4096:
        raise ValueError("path must contain between 1 and 4096 characters")


def _scene_params(scene_file: str, **params: Any) -> dict[str, Any]:
    if len(scene_file) > 4096:
        raise ValueError("scene_file cannot exceed 4096 characters")
    if scene_file:
        params["scene_file"] = scene_file
    return params
