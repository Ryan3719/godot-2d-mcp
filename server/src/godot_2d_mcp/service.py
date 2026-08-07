"""Application service exposed through MCP tools."""

from __future__ import annotations

import math
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

    async def editor_run(
        self,
        mode: str = "current",
        scene_file: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_mode = mode.strip().lower() if isinstance(mode, str) else ""
        if normalized_mode not in {"current", "main", "custom"}:
            raise ValueError("mode must be current, main, or custom")
        if normalized_mode == "custom":
            _validate_project_resource_path(scene_file, "scene_file")
        elif scene_file:
            raise ValueError("scene_file is only accepted when mode is custom")
        return await self.bridge.call(
            "editor_run",
            {"mode": normalized_mode, "scene_file": scene_file},
            session_id=session_id,
        )

    async def editor_stop(self, session_id: str | None = None) -> dict[str, Any]:
        return await self.bridge.call("editor_stop", session_id=session_id)

    async def runtime_get_state(self, session_id: str | None = None) -> dict[str, Any]:
        return await self.bridge.call("runtime_get_state", session_id=session_id)

    async def runtime_logs_get(
        self,
        after_sequence: int = 0,
        limit: int = 100,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(after_sequence, bool) or after_sequence < 0:
            raise ValueError("after_sequence must be a non-negative integer")
        if isinstance(limit, bool) or not 1 <= limit <= 200:
            raise ValueError("limit must be an integer between 1 and 200")
        return await self.bridge.call(
            "runtime_logs_get",
            {"after_sequence": after_sequence, "limit": limit},
            session_id=session_id,
        )

    async def runtime_screenshot_request(
        self,
        format: str = "png",
        max_width: int = 640,
        max_height: int = 640,
        quality: float = 0.85,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_format = format.strip().lower() if isinstance(format, str) else ""
        if normalized_format not in {"png", "jpeg"}:
            raise ValueError("format must be png or jpeg")
        _validate_runtime_screenshot_dimension(max_width, "max_width")
        _validate_runtime_screenshot_dimension(max_height, "max_height")
        if not _is_finite_number(quality) or not 0.1 <= float(quality) <= 1.0:
            raise ValueError("quality must be a finite number between 0.1 and 1.0")
        return await self.bridge.call(
            "runtime_screenshot_request",
            {
                "format": normalized_format,
                "max_width": max_width,
                "max_height": max_height,
                "quality": float(quality),
            },
            session_id=session_id,
        )

    async def runtime_screenshot_get(
        self, request_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        _validate_runtime_request_id(request_id)
        return await self.bridge.call(
            "runtime_screenshot_get", {"request_id": request_id}, session_id=session_id
        )

    async def runtime_input_send(
        self, events: list[dict[str, Any]], session_id: str | None = None
    ) -> dict[str, Any]:
        _validate_runtime_input_events(events)
        return await self.bridge.call(
            "runtime_input_send", {"events": events}, session_id=session_id
        )

    async def runtime_input_result_get(
        self, request_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        _validate_runtime_request_id(request_id)
        return await self.bridge.call(
            "runtime_input_result_get", {"request_id": request_id}, session_id=session_id
        )

    async def runtime_audio_stream_player_2d_control(
        self,
        path: str,
        action: str,
        position_seconds: float | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        _validate_node_path(path)
        normalized_action = _validate_runtime_audio_action(action)
        if position_seconds is None:
            if normalized_action == "seek":
                raise ValueError("seek requires position_seconds")
        else:
            _validate_runtime_audio_position(position_seconds)
            if normalized_action in {"get", "stop"}:
                raise ValueError("position_seconds is only accepted for play or seek")
        params: dict[str, Any] = {"path": path, "action": normalized_action}
        if position_seconds is not None:
            params["position_seconds"] = float(position_seconds)
        return await self.bridge.call(
            "runtime_audio_stream_player_2d_control", params, session_id=session_id
        )

    async def runtime_audio_stream_player_2d_control_result_get(
        self, request_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        _validate_runtime_request_id(request_id)
        return await self.bridge.call(
            "runtime_audio_stream_player_2d_control_result_get",
            {"request_id": request_id},
            session_id=session_id,
        )

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

    async def class_2d_coverage(
        self,
        query: str = "",
        scope: str = "all",
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        if not isinstance(query, str) or len(query) > 256:
            raise ValueError("query must be a string no longer than 256 characters")
        normalized_scope = scope.strip().lower() if isinstance(scope, str) else ""
        if normalized_scope not in {"all", "node", "resource"}:
            raise ValueError("scope must be all, node, or resource")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        return await self.bridge.call(
            "class_2d_coverage",
            {"query": query, "scope": normalized_scope, "offset": offset, "limit": limit},
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

    async def node_get_signals(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "node_get_signals",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def sprite_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "sprite_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def line_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "line_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def polygon_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "polygon_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def animated_sprite_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "animated_sprite_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def sprite_frames_get(
        self,
        path: str,
        animation: str = "",
        frame_offset: int = 0,
        frame_limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_optional_sprite_frames_animation_name(animation, "animation")
        _validate_sprite_frames_page(frame_offset, frame_limit)
        return await self.bridge.call(
            "sprite_frames_get",
            _scene_params(
                scene_file,
                path=path,
                animation=animation.strip(),
                frame_offset=frame_offset,
                frame_limit=frame_limit,
            ),
            session_id=session_id,
        )

    async def button_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "button_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def animated_sprite_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_animated_sprite_2d_properties(properties)
        return await self.bridge.call(
            "animated_sprite_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def button_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_button_2d_properties(properties)
        return await self.bridge.call(
            "button_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def button_menu_items_get(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_button_menu_page(offset, limit)
        return await self.bridge.call(
            "button_menu_items_get",
            _scene_params(scene_file, path=path, offset=offset, limit=limit),
            session_id=session_id,
        )

    async def button_menu_items_set(
        self,
        path: str,
        items: list[dict[str, Any]],
        selected_index: int | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_button_menu_items(items)
        if selected_index is not None and (
            isinstance(selected_index, bool)
            or not isinstance(selected_index, int)
            or not -1 <= selected_index < len(items)
        ):
            raise ValueError("selected_index must be -1 or an item index")
        params = _scene_params(scene_file, path=path, items=items)
        if selected_index is not None:
            params["selected_index"] = selected_index
        return await self.bridge.call("button_menu_items_set", params, session_id=session_id)

    async def button_menu_items_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "button_menu_items_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def sprite_frames_animation_upsert(
        self,
        path: str,
        animation: str,
        speed: float | None = None,
        loop_mode: str | None = None,
        frames: list[dict[str, Any]] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_sprite_frames_animation_name(animation, "animation")
        _validate_sprite_frames_upsert(speed, loop_mode, frames)
        params = _scene_params(scene_file, path=path, animation=animation.strip())
        if speed is not None:
            params["speed"] = speed
        if loop_mode is not None:
            params["loop_mode"] = loop_mode.strip().lower()
        if frames is not None:
            params["frames"] = frames
        return await self.bridge.call(
            "sprite_frames_animation_upsert", params, session_id=session_id
        )

    async def sprite_frames_animation_rename(
        self,
        path: str,
        animation: str,
        new_name: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_sprite_frames_animation_name(animation, "animation")
        _validate_sprite_frames_animation_name(new_name, "new_name")
        if animation.strip() == new_name.strip():
            raise ValueError("animation and new_name must differ")
        return await self.bridge.call(
            "sprite_frames_animation_rename",
            _scene_params(
                scene_file,
                path=path,
                animation=animation.strip(),
                new_name=new_name.strip(),
            ),
            session_id=session_id,
        )

    async def sprite_frames_animation_remove(
        self,
        path: str,
        animation: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_sprite_frames_animation_name(animation, "animation")
        return await self.bridge.call(
            "sprite_frames_animation_remove",
            _scene_params(scene_file, path=path, animation=animation.strip()),
            session_id=session_id,
        )

    async def sprite_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_sprite_2d_properties(properties)
        return await self.bridge.call(
            "sprite_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def line_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_line_2d_properties(properties)
        return await self.bridge.call(
            "line_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def polygon_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_polygon_2d_properties(properties)
        return await self.bridge.call(
            "polygon_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def node_create(
        self,
        type_name: str,
        name: str = "",
        parent_path: str = "",
        session_id: str | None = None,
        scene_file: str = "",
        script_path: str = "",
    ) -> dict[str, Any]:
        if not type_name or len(type_name) > 256:
            raise ValueError("type must contain between 1 and 256 characters")
        if len(name) > 256:
            raise ValueError("name cannot exceed 256 characters")
        if parent_path:
            _validate_node_path(parent_path)
        _validate_optional_project_resource_path(script_path, "script_path")
        params = _scene_params(
            scene_file,
            type=type_name,
            name=name,
            parent_path=parent_path,
        )
        if script_path:
            params["script_path"] = script_path
        return await self.bridge.call("node_create", params, session_id=session_id)

    async def node_script_bind(
        self,
        path: str,
        script_path: str,
        replace_existing: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_project_resource_path(script_path, "script_path")
        _validate_boolean(replace_existing, "replace_existing")
        return await self.bridge.call(
            "node_script_bind",
            _scene_params(
                scene_file,
                path=path,
                script_path=script_path,
                replace_existing=replace_existing,
            ),
            session_id=session_id,
        )

    async def node_script_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "node_script_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def node_instance_scene(
        self,
        scene_path: str,
        name: str = "",
        parent_path: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_project_resource_path(scene_path, "scene_path")
        if len(name) > 256:
            raise ValueError("name cannot exceed 256 characters")
        if parent_path:
            _validate_node_path(parent_path)
        return await self.bridge.call(
            "node_instance_scene",
            _scene_params(
                scene_file,
                scene_path=scene_path,
                name=name,
                parent_path=parent_path,
            ),
            session_id=session_id,
        )

    async def scene_create(
        self,
        scene_path: str,
        root_type: str = "Node2D",
        root_name: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        _validate_new_scene_path(scene_path)
        _validate_scene_root_type(root_type)
        if root_name:
            _validate_node_name(root_name)
        return await self.bridge.call(
            "scene_create",
            {
                "scene_path": scene_path,
                "root_type": root_type,
                "root_name": root_name,
            },
            session_id=session_id,
        )

    async def scene_open(
        self,
        scene_path: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        _validate_existing_scene_path(scene_path)
        return await self.bridge.call(
            "scene_open",
            {"scene_path": scene_path},
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

    async def node_rename(
        self,
        path: str,
        name: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_node_name(name)
        return await self.bridge.call(
            "node_rename",
            _scene_params(scene_file, path=path, name=name),
            session_id=session_id,
        )

    async def node_duplicate(
        self,
        path: str,
        name: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if name:
            _validate_node_name(name)
        return await self.bridge.call(
            "node_duplicate",
            _scene_params(scene_file, path=path, name=name),
            session_id=session_id,
        )

    async def node_reparent(
        self,
        path: str,
        new_parent_path: str,
        index: int | None = None,
        keep_global_transform: bool = True,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_node_path(new_parent_path)
        if index is not None and (isinstance(index, bool) or index < 0):
            raise ValueError("index must be non-negative when supplied")
        if not isinstance(keep_global_transform, bool):
            raise ValueError("keep_global_transform must be a boolean")
        return await self.bridge.call(
            "node_reparent",
            _scene_params(
                scene_file,
                path=path,
                new_parent_path=new_parent_path,
                index=-1 if index is None else index,
                keep_global_transform=keep_global_transform,
            ),
            session_id=session_id,
        )

    async def node_move(
        self,
        path: str,
        index: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if isinstance(index, bool) or index < 0:
            raise ValueError("index must be non-negative")
        return await self.bridge.call(
            "node_move",
            _scene_params(scene_file, path=path, index=index),
            session_id=session_id,
        )

    async def signal_connect(
        self,
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
        _validate_node_path(source_path)
        _validate_node_path(target_path)
        _validate_signal_member(signal, "signal")
        _validate_signal_member(method, "method")
        requested_binds = [] if binds is None else binds
        _validate_binds(requested_binds)
        if not isinstance(deferred, bool) or not isinstance(one_shot, bool):
            raise ValueError("deferred and one_shot must be booleans")
        return await self.bridge.call(
            "signal_connect",
            _scene_params(
                scene_file,
                source_path=source_path,
                signal=signal,
                target_path=target_path,
                method=method,
                binds=requested_binds,
                deferred=deferred,
                one_shot=one_shot,
            ),
            session_id=session_id,
        )

    async def signal_disconnect(
        self,
        source_path: str,
        signal: str,
        target_path: str,
        method: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(source_path)
        _validate_node_path(target_path)
        _validate_signal_member(signal, "signal")
        _validate_signal_member(method, "method")
        return await self.bridge.call(
            "signal_disconnect",
            _scene_params(
                scene_file,
                source_path=source_path,
                signal=signal,
                target_path=target_path,
                method=method,
            ),
            session_id=session_id,
        )

    async def animation_list(
        self,
        player_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(player_path)
        return await self.bridge.call(
            "animation_list",
            _scene_params(scene_file, player_path=player_path),
            session_id=session_id,
        )

    async def animation_get(
        self,
        player_path: str,
        animation: str,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(player_path)
        _validate_animation_name(animation)
        _validate_animation_library(library)
        return await self.bridge.call(
            "animation_get",
            _scene_params(
                scene_file,
                player_path=player_path,
                animation=animation,
                library=library,
            ),
            session_id=session_id,
        )

    async def animation_create(
        self,
        player_path: str,
        animation: str,
        length: float = 0.2,
        loop_mode: str = "none",
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(player_path)
        _validate_animation_name(animation)
        _validate_animation_library(library)
        _validate_animation_length(length)
        _validate_loop_mode(loop_mode)
        return await self.bridge.call(
            "animation_create",
            _scene_params(
                scene_file,
                player_path=player_path,
                animation=animation,
                length=length,
                loop_mode=loop_mode,
                library=library,
            ),
            session_id=session_id,
        )

    async def animation_delete(
        self,
        player_path: str,
        animation: str,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(player_path)
        _validate_animation_name(animation)
        _validate_animation_library(library)
        return await self.bridge.call(
            "animation_delete",
            _scene_params(
                scene_file,
                player_path=player_path,
                animation=animation,
                library=library,
            ),
            session_id=session_id,
        )

    async def animation_track_upsert(
        self,
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
        _validate_node_path(player_path)
        _validate_animation_name(animation)
        _validate_node_path(target_path)
        _validate_animation_property(property)
        _validate_animation_keys(keys)
        _validate_interpolation(interpolation)
        _validate_update_mode(update_mode)
        _validate_boolean(enabled, "enabled")
        _validate_boolean(loop_wrap, "loop_wrap")
        _validate_animation_library(library)
        return await self.bridge.call(
            "animation_track_upsert",
            _scene_params(
                scene_file,
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
            ),
            session_id=session_id,
        )

    async def animation_track_delete(
        self,
        player_path: str,
        animation: str,
        track_index: int,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(player_path)
        _validate_animation_name(animation)
        _validate_track_index(track_index)
        _validate_animation_library(library)
        return await self.bridge.call(
            "animation_track_delete",
            _scene_params(
                scene_file,
                player_path=player_path,
                animation=animation,
                track_index=track_index,
                library=library,
            ),
            session_id=session_id,
        )

    async def animation_key_upsert(
        self,
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
        _validate_node_path(player_path)
        _validate_animation_name(animation)
        _validate_track_index(track_index)
        _validate_key_time(time)
        if not _is_json_bind_value(value):
            raise ValueError("value must be a bounded JSON-compatible value")
        _validate_transition(transition)
        _validate_animation_library(library)
        return await self.bridge.call(
            "animation_key_upsert",
            _scene_params(
                scene_file,
                player_path=player_path,
                animation=animation,
                track_index=track_index,
                time=time,
                value=value,
                transition=transition,
                library=library,
            ),
            session_id=session_id,
        )

    async def animation_key_delete(
        self,
        player_path: str,
        animation: str,
        track_index: int,
        time: float,
        library: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(player_path)
        _validate_animation_name(animation)
        _validate_track_index(track_index)
        _validate_key_time(time)
        _validate_animation_library(library)
        return await self.bridge.call(
            "animation_key_delete",
            _scene_params(
                scene_file,
                player_path=player_path,
                animation=animation,
                track_index=track_index,
                time=time,
                library=library,
            ),
            session_id=session_id,
        )

    async def control_get_layout(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "control_get_layout",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def container_2d_get(
        self,
        path: str,
        child_offset: int = 0,
        child_limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_container_child_page(child_offset, child_limit)
        return await self.bridge.call(
            "container_2d_get",
            _scene_params(
                scene_file,
                path=path,
                child_offset=child_offset,
                child_limit=child_limit,
            ),
            session_id=session_id,
        )

    async def control_set_layout(
        self,
        path: str,
        anchors: dict[str, float] | None = None,
        offsets: dict[str, float] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if anchors is None and offsets is None:
            raise ValueError("anchors or offsets must be supplied")
        if anchors is not None:
            _validate_layout_sides(anchors, "anchors", minimum=0, maximum=1)
        if offsets is not None:
            _validate_layout_sides(
                offsets,
                "offsets",
                minimum=-1_000_000,
                maximum=1_000_000,
            )
        return await self.bridge.call(
            "control_set_layout",
            _scene_params(scene_file, path=path, anchors=anchors, offsets=offsets),
            session_id=session_id,
        )

    async def container_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_container_2d_properties(properties)
        return await self.bridge.call(
            "container_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def container_child_layout_set(
        self,
        path: str,
        child_path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_node_path(child_path)
        _validate_container_child_layout_properties(properties)
        return await self.bridge.call(
            "container_child_layout_set",
            _scene_params(
                scene_file,
                path=path,
                child_path=child_path,
                properties=properties,
            ),
            session_id=session_id,
        )

    async def control_set_layout_preset(
        self,
        path: str,
        preset: str,
        resize_mode: str = "min_size",
        margin: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_layout_preset(preset)
        _validate_layout_resize_mode(resize_mode)
        _validate_layout_margin(margin)
        return await self.bridge.call(
            "control_set_layout_preset",
            _scene_params(
                scene_file,
                path=path,
                preset=preset,
                resize_mode=resize_mode,
                margin=margin,
            ),
            session_id=session_id,
        )

    async def control_get_styleboxes(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "control_get_styleboxes",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def control_theme_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "control_theme_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def collision_shape_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "collision_shape_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def collision_object_get_layers(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "collision_object_get_layers",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def area_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "area_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def physics_body_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "physics_body_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def joint_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "joint_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def ray_cast_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "ray_cast_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def shape_cast_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "shape_cast_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def navigation_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "navigation_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def navigation_polygon_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "navigation_polygon_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def camera_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "camera_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def parallax_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "parallax_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def canvas_layer_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "canvas_layer_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def path_2d_get(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_path_curve_page(offset, limit)
        return await self.bridge.call(
            "path_2d_get",
            _scene_params(scene_file, path=path, offset=offset, limit=limit),
            session_id=session_id,
        )

    async def skeleton_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "skeleton_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def bone_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "bone_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def audio_stream_player_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "audio_stream_player_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def gpu_particles_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "gpu_particles_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def cpu_particles_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "cpu_particles_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def cpu_particles_2d_curve_get(
        self,
        path: str,
        curve: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_curve_name(curve)
        return await self.bridge.call(
            "cpu_particles_2d_curve_get",
            _scene_params(scene_file, path=path, curve=curve),
            session_id=session_id,
        )

    async def cpu_particles_2d_gradient_get(
        self,
        path: str,
        gradient: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_gradient_name(gradient)
        return await self.bridge.call(
            "cpu_particles_2d_gradient_get",
            _scene_params(scene_file, path=path, gradient=gradient),
            session_id=session_id,
        )

    async def particle_process_material_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "particle_process_material_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def particle_process_material_2d_curve_get(
        self,
        path: str,
        curve: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_curve_name(curve)
        return await self.bridge.call(
            "particle_process_material_2d_curve_get",
            _scene_params(scene_file, path=path, curve=curve),
            session_id=session_id,
        )

    async def particle_process_material_2d_gradient_get(
        self,
        path: str,
        gradient: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_gradient_name(gradient)
        return await self.bridge.call(
            "particle_process_material_2d_gradient_get",
            _scene_params(scene_file, path=path, gradient=gradient),
            session_id=session_id,
        )

    async def canvas_item_material_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "canvas_item_material_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def canvas_item_shader_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "canvas_item_shader_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def light_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "light_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def light_occluder_2d_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "light_occluder_2d_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def tile_map_layer_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "tile_map_layer_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def tile_map_layer_cells_get(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_page(offset, limit)
        return await self.bridge.call(
            "tile_map_layer_cells_get",
            _scene_params(scene_file, path=path, offset=offset, limit=limit),
            session_id=session_id,
        )

    async def tile_set_get(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_page(offset, limit)
        return await self.bridge.call(
            "tile_set_get",
            _scene_params(scene_file, path=path, offset=offset, limit=limit),
            session_id=session_id,
        )

    async def tile_set_layers_get(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "tile_set_layers_get",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def tile_set_atlas_tile_get(
        self,
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_source_id(source_id)
        _validate_tilemap_vector2i(atlas_coords, "atlas_coords", nonnegative=True)
        _validate_atlas_alternative_tile(alternative_tile)
        return await self.bridge.call(
            "tile_set_atlas_tile_get",
            _scene_params(
                scene_file,
                path=path,
                source_id=source_id,
                atlas_coords=atlas_coords,
                alternative_tile=alternative_tile,
            ),
            session_id=session_id,
        )

    async def control_stylebox_flat_upsert(
        self,
        path: str,
        state: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_stylebox_state(state)
        _validate_stylebox_properties(properties)
        return await self.bridge.call(
            "control_stylebox_flat_upsert",
            _scene_params(scene_file, path=path, state=state, properties=properties),
            session_id=session_id,
        )

    async def control_stylebox_override_clear(
        self,
        path: str,
        state: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_stylebox_state(state)
        return await self.bridge.call(
            "control_stylebox_override_clear",
            _scene_params(scene_file, path=path, state=state),
            session_id=session_id,
        )

    async def control_theme_create(
        self,
        path: str,
        resource_name: str = "",
        replace: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_theme_resource_name(resource_name)
        _validate_boolean(replace, "replace")
        return await self.bridge.call(
            "control_theme_create",
            _scene_params(
                scene_file,
                path=path,
                resource_name=resource_name,
                replace=replace,
            ),
            session_id=session_id,
        )

    async def control_theme_assign(
        self,
        path: str,
        theme_path: str = "",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_optional_project_resource_path(theme_path, "theme_path")
        return await self.bridge.call(
            "control_theme_assign",
            _scene_params(scene_file, path=path, theme_path=theme_path),
            session_id=session_id,
        )

    async def control_theme_defaults_set(
        self,
        path: str,
        font: dict[str, Any] | None = None,
        font_size: int | None = None,
        base_scale: float | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if font is None and font_size is None and base_scale is None:
            raise ValueError("font, font_size, or base_scale must be supplied")
        if font is not None:
            _validate_theme_font_value(font)
        if font_size is not None:
            _validate_theme_font_size(font_size)
        if base_scale is not None:
            _validate_theme_base_scale(base_scale)
        return await self.bridge.call(
            "control_theme_defaults_set",
            _scene_params(
                scene_file,
                path=path,
                font=font,
                font_size=font_size,
                base_scale=base_scale,
            ),
            session_id=session_id,
        )

    async def control_theme_defaults_clear(
        self,
        path: str,
        defaults: list[str],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_theme_default_names(defaults)
        return await self.bridge.call(
            "control_theme_defaults_clear",
            _scene_params(scene_file, path=path, defaults=defaults),
            session_id=session_id,
        )

    async def control_theme_item_upsert(
        self,
        path: str,
        item_type: str,
        theme_type: str,
        name: str,
        value: Any,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_theme_item_identity(item_type, theme_type, name)
        _validate_theme_item_value(item_type, value)
        return await self.bridge.call(
            "control_theme_item_upsert",
            _scene_params(
                scene_file,
                path=path,
                item_type=item_type,
                theme_type=theme_type,
                name=name,
                value=value,
            ),
            session_id=session_id,
        )

    async def control_theme_item_clear(
        self,
        path: str,
        item_type: str,
        theme_type: str,
        name: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_theme_item_identity(item_type, theme_type, name)
        return await self.bridge.call(
            "control_theme_item_clear",
            _scene_params(
                scene_file,
                path=path,
                item_type=item_type,
                theme_type=theme_type,
                name=name,
            ),
            session_id=session_id,
        )

    async def collision_shape_set(
        self,
        path: str,
        shape_type: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_collision_shape_type(shape_type)
        _validate_collision_shape_properties(shape_type, properties)
        return await self.bridge.call(
            "collision_shape_set",
            _scene_params(
                scene_file,
                path=path,
                shape_type=shape_type,
                properties=properties,
            ),
            session_id=session_id,
        )

    async def collision_shape_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "collision_shape_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def collision_object_set_layers(
        self,
        path: str,
        layers: list[int] | None = None,
        masks: list[int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if layers is None and masks is None:
            raise ValueError("layers or masks must be supplied")
        if layers is not None:
            _validate_collision_layer_numbers(layers, "layers")
        if masks is not None:
            _validate_collision_layer_numbers(masks, "masks")
        return await self.bridge.call(
            "collision_object_set_layers",
            _scene_params(scene_file, path=path, layers=layers, masks=masks),
            session_id=session_id,
        )

    async def area_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_physics_configuration_properties(properties)
        return await self.bridge.call(
            "area_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def physics_body_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_physics_configuration_properties(properties)
        return await self.bridge.call(
            "physics_body_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def joint_2d_set(
        self,
        path: str,
        properties: dict[str, Any] | None = None,
        node_a_path: str | None = None,
        node_b_path: str | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if properties is None and node_a_path is None and node_b_path is None:
            raise ValueError("properties, node_a_path, or node_b_path must be supplied")
        if properties is not None:
            _validate_physics_configuration_properties(properties, allow_empty=True)
        _validate_optional_joint_endpoint_path(node_a_path, "node_a_path")
        _validate_optional_joint_endpoint_path(node_b_path, "node_b_path")
        return await self.bridge.call(
            "joint_2d_set",
            _scene_params(
                scene_file,
                path=path,
                properties=properties,
                node_a_path=node_a_path,
                node_b_path=node_b_path,
            ),
            session_id=session_id,
        )

    async def ray_cast_2d_set(
        self,
        path: str,
        properties: dict[str, Any] | None = None,
        masks: list[int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if properties is None and masks is None:
            raise ValueError("properties or masks must be supplied")
        if properties is not None:
            _validate_physics_configuration_properties(properties, allow_empty=True)
        if masks is not None:
            _validate_collision_layer_numbers(masks, "masks")
        return await self.bridge.call(
            "ray_cast_2d_set",
            _scene_params(scene_file, path=path, properties=properties, masks=masks),
            session_id=session_id,
        )

    async def shape_cast_2d_set(
        self,
        path: str,
        properties: dict[str, Any] | None = None,
        masks: list[int] | None = None,
        shape_type: str | None = None,
        shape_properties: dict[str, Any] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if properties is None and masks is None and shape_type is None:
            raise ValueError("properties, masks, or shape_type must be supplied")
        if properties is not None:
            _validate_physics_configuration_properties(properties, allow_empty=True)
        if masks is not None:
            _validate_collision_layer_numbers(masks, "masks")
        if shape_type is None and shape_properties is not None:
            raise ValueError("shape_type must be supplied with shape_properties")
        if shape_type is not None:
            _validate_collision_shape_type(shape_type)
            if shape_properties is None:
                raise ValueError("shape_properties must be supplied with shape_type")
            _validate_collision_shape_properties(shape_type, shape_properties)
        return await self.bridge.call(
            "shape_cast_2d_set",
            _scene_params(
                scene_file,
                path=path,
                properties=properties,
                masks=masks,
                shape_type=shape_type,
                shape_properties=shape_properties,
            ),
            session_id=session_id,
        )

    async def shape_cast_2d_shape_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "shape_cast_2d_shape_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def navigation_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_physics_configuration_properties(properties)
        return await self.bridge.call(
            "navigation_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def navigation_polygon_create(
        self,
        path: str,
        agent_radius: float = 0.0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_navigation_polygon_agent_radius(agent_radius)
        return await self.bridge.call(
            "navigation_polygon_create",
            _scene_params(scene_file, path=path, agent_radius=agent_radius),
            session_id=session_id,
        )

    async def navigation_polygon_geometry_set(
        self,
        path: str,
        vertices: list[dict[str, float | int]],
        polygons: list[list[int]],
        agent_radius: float | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_navigation_polygon_vertices(vertices, "vertices", allow_empty=True)
        _validate_navigation_polygon_indices(polygons)
        if bool(vertices) != bool(polygons):
            raise ValueError("vertices and polygons must both be empty or non-empty")
        if agent_radius is not None:
            _validate_navigation_polygon_agent_radius(agent_radius)
        return await self.bridge.call(
            "navigation_polygon_geometry_set",
            _scene_params(
                scene_file,
                path=path,
                vertices=vertices,
                polygons=polygons,
                agent_radius=agent_radius,
            ),
            session_id=session_id,
        )

    async def navigation_polygon_outline_set(
        self,
        path: str,
        outline: list[dict[str, float | int]],
        index: int | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_navigation_polygon_vertices(outline, "outline")
        _validate_navigation_outline_index(index, allow_none=True)
        return await self.bridge.call(
            "navigation_polygon_outline_set",
            _scene_params(scene_file, path=path, outline=outline, index=index),
            session_id=session_id,
        )

    async def navigation_polygon_outline_remove(
        self,
        path: str,
        index: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_navigation_outline_index(index)
        return await self.bridge.call(
            "navigation_polygon_outline_remove",
            _scene_params(scene_file, path=path, index=index),
            session_id=session_id,
        )

    async def navigation_polygon_make_from_outlines(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "navigation_polygon_make_from_outlines",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def navigation_polygon_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "navigation_polygon_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def camera_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_viewport_configuration_properties(properties)
        return await self.bridge.call(
            "camera_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def parallax_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_viewport_configuration_properties(properties)
        return await self.bridge.call(
            "parallax_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def canvas_layer_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_viewport_configuration_properties(properties)
        return await self.bridge.call(
            "canvas_layer_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def path_2d_curve_set(
        self,
        path: str,
        points: list[dict[str, Any]],
        bake_interval: float = 5.0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_path_curve_points(points)
        _validate_path_curve_bake_interval(bake_interval)
        return await self.bridge.call(
            "path_2d_curve_set",
            _scene_params(
                scene_file,
                path=path,
                points=points,
                bake_interval=bake_interval,
            ),
            session_id=session_id,
        )

    async def path_2d_curve_point_insert(
        self,
        path: str,
        point: dict[str, Any],
        index: int | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_path_curve_point(point)
        _validate_path_curve_index(index, allow_none=True, allow_endpoint=True)
        return await self.bridge.call(
            "path_2d_curve_point_insert",
            _scene_params(scene_file, path=path, point=point, index=index),
            session_id=session_id,
        )

    async def path_2d_curve_point_set(
        self,
        path: str,
        index: int,
        point: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_path_curve_index(index)
        _validate_path_curve_point(point)
        return await self.bridge.call(
            "path_2d_curve_point_set",
            _scene_params(scene_file, path=path, index=index, point=point),
            session_id=session_id,
        )

    async def path_2d_curve_point_remove(
        self,
        path: str,
        index: int,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_path_curve_index(index)
        return await self.bridge.call(
            "path_2d_curve_point_remove",
            _scene_params(scene_file, path=path, index=index),
            session_id=session_id,
        )

    async def path_2d_curve_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "path_2d_curve_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def skeleton_2d_bone_create(
        self,
        path: str,
        name: str = "",
        parent_bone_path: str = "",
        rest: dict[str, Any] | None = None,
        length: float = 16.0,
        angle_degrees: float = 0.0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if len(name) > 256:
            raise ValueError("name cannot exceed 256 characters")
        if parent_bone_path:
            _validate_node_path(parent_bone_path)
        _validate_bone_2d_creation(rest, length, angle_degrees)
        return await self.bridge.call(
            "skeleton_2d_bone_create",
            _scene_params(
                scene_file,
                path=path,
                name=name,
                parent_bone_path=parent_bone_path,
                rest=rest,
                length=length,
                angle_degrees=angle_degrees,
            ),
            session_id=session_id,
        )

    async def bone_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_bone_2d_properties(properties)
        return await self.bridge.call(
            "bone_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def skeleton_2d_reset_to_rest(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "skeleton_2d_reset_to_rest",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def skeleton_2d_make_rest_from_current(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "skeleton_2d_make_rest_from_current",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def audio_stream_player_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_audio_stream_player_2d_properties(properties)
        return await self.bridge.call(
            "audio_stream_player_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def gpu_particles_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_gpu_particles_2d_properties(properties)
        return await self.bridge.call(
            "gpu_particles_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def cpu_particles_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_2d_properties(properties)
        return await self.bridge.call(
            "cpu_particles_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def cpu_particles_2d_curve_bind(
        self,
        path: str,
        curve: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_curve_name(curve)
        _validate_project_resource_path(resource_path, "resource_path")
        return await self.bridge.call(
            "cpu_particles_2d_curve_bind",
            _scene_params(scene_file, path=path, curve=curve, resource_path=resource_path),
            session_id=session_id,
        )

    async def cpu_particles_2d_curve_set(
        self,
        path: str,
        curve: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_curve_name(curve)
        _validate_cpu_particles_curve_properties(properties)
        return await self.bridge.call(
            "cpu_particles_2d_curve_set",
            _scene_params(scene_file, path=path, curve=curve, properties=properties),
            session_id=session_id,
        )

    async def cpu_particles_2d_curve_clear(
        self,
        path: str,
        curve: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_curve_name(curve)
        return await self.bridge.call(
            "cpu_particles_2d_curve_clear",
            _scene_params(scene_file, path=path, curve=curve),
            session_id=session_id,
        )

    async def cpu_particles_2d_gradient_bind(
        self,
        path: str,
        gradient: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_gradient_name(gradient)
        _validate_project_resource_path(resource_path, "resource_path")
        return await self.bridge.call(
            "cpu_particles_2d_gradient_bind",
            _scene_params(scene_file, path=path, gradient=gradient, resource_path=resource_path),
            session_id=session_id,
        )

    async def cpu_particles_2d_gradient_set(
        self,
        path: str,
        gradient: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_gradient_name(gradient)
        _validate_cpu_particles_gradient_properties(properties)
        return await self.bridge.call(
            "cpu_particles_2d_gradient_set",
            _scene_params(scene_file, path=path, gradient=gradient, properties=properties),
            session_id=session_id,
        )

    async def cpu_particles_2d_gradient_clear(
        self,
        path: str,
        gradient: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_cpu_particles_gradient_name(gradient)
        return await self.bridge.call(
            "cpu_particles_2d_gradient_clear",
            _scene_params(scene_file, path=path, gradient=gradient),
            session_id=session_id,
        )

    async def particle_process_material_2d_create(
        self,
        path: str,
        replace_existing: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_boolean(replace_existing, "replace_existing")
        return await self.bridge.call(
            "particle_process_material_2d_create",
            _scene_params(scene_file, path=path, replace_existing=replace_existing),
            session_id=session_id,
        )

    async def particle_process_material_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_2d_properties(properties)
        return await self.bridge.call(
            "particle_process_material_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def particle_process_material_2d_curve_bind(
        self,
        path: str,
        curve: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_curve_name(curve)
        _validate_project_resource_path(resource_path, "resource_path")
        return await self.bridge.call(
            "particle_process_material_2d_curve_bind",
            _scene_params(scene_file, path=path, curve=curve, resource_path=resource_path),
            session_id=session_id,
        )

    async def particle_process_material_2d_curve_set(
        self,
        path: str,
        curve: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_curve_name(curve)
        _validate_particle_process_material_curve_properties(properties)
        return await self.bridge.call(
            "particle_process_material_2d_curve_set",
            _scene_params(scene_file, path=path, curve=curve, properties=properties),
            session_id=session_id,
        )

    async def particle_process_material_2d_curve_clear(
        self,
        path: str,
        curve: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_curve_name(curve)
        return await self.bridge.call(
            "particle_process_material_2d_curve_clear",
            _scene_params(scene_file, path=path, curve=curve),
            session_id=session_id,
        )

    async def particle_process_material_2d_gradient_bind(
        self,
        path: str,
        gradient: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_gradient_name(gradient)
        _validate_project_resource_path(resource_path, "resource_path")
        return await self.bridge.call(
            "particle_process_material_2d_gradient_bind",
            _scene_params(scene_file, path=path, gradient=gradient, resource_path=resource_path),
            session_id=session_id,
        )

    async def particle_process_material_2d_gradient_set(
        self,
        path: str,
        gradient: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_gradient_name(gradient)
        _validate_particle_process_material_gradient_properties(properties)
        return await self.bridge.call(
            "particle_process_material_2d_gradient_set",
            _scene_params(scene_file, path=path, gradient=gradient, properties=properties),
            session_id=session_id,
        )

    async def particle_process_material_2d_gradient_clear(
        self,
        path: str,
        gradient: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_particle_process_material_gradient_name(gradient)
        return await self.bridge.call(
            "particle_process_material_2d_gradient_clear",
            _scene_params(scene_file, path=path, gradient=gradient),
            session_id=session_id,
        )

    async def canvas_item_material_create(
        self,
        path: str,
        replace_existing: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_boolean(replace_existing, "replace_existing")
        return await self.bridge.call(
            "canvas_item_material_create",
            _scene_params(scene_file, path=path, replace_existing=replace_existing),
            session_id=session_id,
        )

    async def canvas_item_material_bind(
        self,
        path: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_project_resource_path(resource_path, "resource_path")
        return await self.bridge.call(
            "canvas_item_material_bind",
            _scene_params(scene_file, path=path, resource_path=resource_path),
            session_id=session_id,
        )

    async def canvas_item_material_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_canvas_item_material_properties(properties)
        return await self.bridge.call(
            "canvas_item_material_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def canvas_item_material_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "canvas_item_material_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def canvas_item_shader_create(
        self,
        path: str,
        source: str = "shader_type canvas_item;\n",
        replace_existing: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_canvas_item_shader_source(source)
        _validate_boolean(replace_existing, "replace_existing")
        return await self.bridge.call(
            "canvas_item_shader_create",
            _scene_params(
                scene_file,
                path=path,
                source=source,
                replace_existing=replace_existing,
            ),
            session_id=session_id,
        )

    async def canvas_item_shader_bind(
        self,
        path: str,
        resource_path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_project_resource_path(resource_path, "resource_path")
        return await self.bridge.call(
            "canvas_item_shader_bind",
            _scene_params(scene_file, path=path, resource_path=resource_path),
            session_id=session_id,
        )

    async def canvas_item_shader_set(
        self,
        path: str,
        source: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_canvas_item_shader_source(source)
        return await self.bridge.call(
            "canvas_item_shader_set",
            _scene_params(scene_file, path=path, source=source),
            session_id=session_id,
        )

    async def canvas_item_shader_uniforms_set(
        self,
        path: str,
        values: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_canvas_item_shader_uniform_values(values)
        return await self.bridge.call(
            "canvas_item_shader_uniforms_set",
            _scene_params(scene_file, path=path, values=values),
            session_id=session_id,
        )

    async def canvas_item_shader_uniforms_clear(
        self,
        path: str,
        names: list[str],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_canvas_item_shader_uniform_names(names)
        return await self.bridge.call(
            "canvas_item_shader_uniforms_clear",
            _scene_params(scene_file, path=path, names=names),
            session_id=session_id,
        )

    async def canvas_item_shader_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "canvas_item_shader_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def light_2d_set(
        self,
        path: str,
        properties: dict[str, Any],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_light_2d_properties(properties)
        return await self.bridge.call(
            "light_2d_set",
            _scene_params(scene_file, path=path, properties=properties),
            session_id=session_id,
        )

    async def light_occluder_2d_set(
        self,
        path: str,
        layers: list[int] | None = None,
        sdf_collision: bool | None = None,
        polygon: dict[str, Any] | None = None,
        clear: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        if layers is None and sdf_collision is None and polygon is None and not clear:
            raise ValueError("layers, sdf_collision, polygon, or clear must be supplied")
        if layers is not None:
            _validate_collision_layer_numbers(layers, "layers")
        if sdf_collision is not None:
            _validate_boolean(sdf_collision, "sdf_collision")
        _validate_boolean(clear, "clear")
        if clear and polygon is not None:
            raise ValueError("clear cannot be combined with polygon")
        if polygon is not None:
            _validate_light_occluder_polygon(polygon)
        return await self.bridge.call(
            "light_occluder_2d_set",
            _scene_params(
                scene_file,
                path=path,
                layers=layers,
                sdf_collision=sdf_collision,
                polygon=polygon,
                clear=clear,
            ),
            session_id=session_id,
        )

    async def tile_set_create(
        self,
        path: str,
        tile_size: dict[str, int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        requested_tile_size = {"x": 16, "y": 16} if tile_size is None else tile_size
        _validate_tilemap_vector2i(
            requested_tile_size, "tile_size", nonnegative=True, positive=True
        )
        return await self.bridge.call(
            "tile_set_create",
            _scene_params(scene_file, path=path, tile_size=requested_tile_size),
            session_id=session_id,
        )

    async def tile_set_clear(
        self,
        path: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        return await self.bridge.call(
            "tile_set_clear",
            _scene_params(scene_file, path=path),
            session_id=session_id,
        )

    async def tile_set_atlas_source_create(
        self,
        path: str,
        texture_path: str,
        source_id: int | None = None,
        texture_region_size: dict[str, int] | None = None,
        margins: dict[str, int] | None = None,
        separation: dict[str, int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_project_resource_path(texture_path, "texture_path")
        _validate_optional_tilemap_source_id(source_id)
        if texture_region_size is not None:
            _validate_tilemap_vector2i(
                texture_region_size, "texture_region_size", nonnegative=True, positive=True
            )
        if margins is not None:
            _validate_tilemap_vector2i(margins, "margins", nonnegative=True)
        if separation is not None:
            _validate_tilemap_vector2i(separation, "separation", nonnegative=True)
        return await self.bridge.call(
            "tile_set_atlas_source_create",
            _scene_params(
                scene_file,
                path=path,
                texture_path=texture_path,
                source_id=source_id,
                texture_region_size=texture_region_size,
                margins=margins,
                separation=separation,
            ),
            session_id=session_id,
        )

    async def tile_set_atlas_tile_create(
        self,
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        size: dict[str, int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_source_id(source_id)
        _validate_tilemap_vector2i(atlas_coords, "atlas_coords", nonnegative=True)
        requested_size = {"x": 1, "y": 1} if size is None else size
        _validate_tilemap_vector2i(requested_size, "size", nonnegative=True, positive=True)
        if requested_size["x"] > 64 or requested_size["y"] > 64:
            raise ValueError("size cannot exceed 64 atlas grid cells per axis")
        return await self.bridge.call(
            "tile_set_atlas_tile_create",
            _scene_params(
                scene_file,
                path=path,
                source_id=source_id,
                atlas_coords=atlas_coords,
                size=requested_size,
            ),
            session_id=session_id,
        )

    async def tile_map_layer_cells_set(
        self,
        path: str,
        cells: list[dict[str, Any]],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_cells(cells)
        return await self.bridge.call(
            "tile_map_layer_cells_set",
            _scene_params(scene_file, path=path, cells=cells),
            session_id=session_id,
        )

    async def tile_map_layer_cells_clear(
        self,
        path: str,
        coords: list[dict[str, int]],
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_coordinates(coords)
        return await self.bridge.call(
            "tile_map_layer_cells_clear",
            _scene_params(scene_file, path=path, coords=coords),
            session_id=session_id,
        )

    async def tile_set_physics_layer_create(
        self,
        path: str,
        layers: list[int] | None = None,
        masks: list[int] | None = None,
        priority: float = 1.0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        requested_layers = [1] if layers is None else layers
        requested_masks = [1] if masks is None else masks
        _validate_collision_layer_numbers(requested_layers, "layers")
        _validate_collision_layer_numbers(requested_masks, "masks")
        _validate_nonnegative_finite_number(priority, "priority")
        return await self.bridge.call(
            "tile_set_physics_layer_create",
            _scene_params(
                scene_file,
                path=path,
                layers=requested_layers,
                masks=requested_masks,
                priority=priority,
            ),
            session_id=session_id,
        )

    async def tile_set_navigation_layer_create(
        self,
        path: str,
        layers: list[int] | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        requested_layers = [1] if layers is None else layers
        _validate_collision_layer_numbers(requested_layers, "layers")
        return await self.bridge.call(
            "tile_set_navigation_layer_create",
            _scene_params(scene_file, path=path, layers=requested_layers),
            session_id=session_id,
        )

    async def tile_set_occlusion_layer_create(
        self,
        path: str,
        layers: list[int] | None = None,
        sdf_collision: bool = False,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        requested_layers = [1] if layers is None else layers
        _validate_collision_layer_numbers(requested_layers, "layers")
        if not isinstance(sdf_collision, bool):
            raise ValueError("sdf_collision must be a boolean")
        return await self.bridge.call(
            "tile_set_occlusion_layer_create",
            _scene_params(
                scene_file,
                path=path,
                layers=requested_layers,
                sdf_collision=sdf_collision,
            ),
            session_id=session_id,
        )

    async def tile_set_custom_data_layer_create(
        self,
        path: str,
        name: str,
        value_type: str,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tile_set_identifier(name, "name")
        _validate_tile_set_custom_data_type(value_type)
        return await self.bridge.call(
            "tile_set_custom_data_layer_create",
            _scene_params(scene_file, path=path, name=name, value_type=value_type),
            session_id=session_id,
        )

    async def tile_set_terrain_set_create(
        self,
        path: str,
        mode: str = "match_corners_and_sides",
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tile_set_terrain_mode(mode)
        return await self.bridge.call(
            "tile_set_terrain_set_create",
            _scene_params(scene_file, path=path, mode=mode),
            session_id=session_id,
        )

    async def tile_set_terrain_create(
        self,
        path: str,
        terrain_set: int,
        name: str = "",
        color: Any | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tile_set_terrain_set_index(terrain_set)
        _validate_optional_tile_set_name(name, "name")
        return await self.bridge.call(
            "tile_set_terrain_create",
            _scene_params(
                scene_file,
                path=path,
                terrain_set=terrain_set,
                name=name,
                color=color,
            ),
            session_id=session_id,
        )

    async def tile_set_atlas_alternative_create(
        self,
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        alternative_tile: int | None = None,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_source_id(source_id)
        _validate_tilemap_vector2i(atlas_coords, "atlas_coords", nonnegative=True)
        _validate_optional_atlas_alternative_tile(alternative_tile, minimum=1)
        return await self.bridge.call(
            "tile_set_atlas_alternative_create",
            _scene_params(
                scene_file,
                path=path,
                source_id=source_id,
                atlas_coords=atlas_coords,
                alternative_tile=alternative_tile,
            ),
            session_id=session_id,
        )

    async def tile_set_atlas_tile_terrain_set(
        self,
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
        _validate_node_path(path)
        _validate_tilemap_source_id(source_id)
        _validate_tilemap_vector2i(atlas_coords, "atlas_coords", nonnegative=True)
        _validate_atlas_alternative_tile(alternative_tile)
        _validate_tile_set_terrain_index(terrain_set, allow_clear=True, label="terrain_set")
        _validate_tile_set_terrain_index(terrain, allow_clear=True, label="terrain")
        if terrain_set == -1 and terrain != -1:
            raise ValueError("terrain must be -1 when terrain_set is -1")
        requested_peering_bits = {} if peering_bits is None else peering_bits
        _validate_tile_set_peering_bits(requested_peering_bits)
        return await self.bridge.call(
            "tile_set_atlas_tile_terrain_set",
            _scene_params(
                scene_file,
                path=path,
                source_id=source_id,
                atlas_coords=atlas_coords,
                terrain_set=terrain_set,
                terrain=terrain,
                peering_bits=requested_peering_bits,
                alternative_tile=alternative_tile,
            ),
            session_id=session_id,
        )

    async def tile_set_atlas_tile_custom_data_set(
        self,
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        values: dict[str, Any],
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_source_id(source_id)
        _validate_tilemap_vector2i(atlas_coords, "atlas_coords", nonnegative=True)
        _validate_atlas_alternative_tile(alternative_tile)
        _validate_tile_set_custom_data_values(values)
        return await self.bridge.call(
            "tile_set_atlas_tile_custom_data_set",
            _scene_params(
                scene_file,
                path=path,
                source_id=source_id,
                atlas_coords=atlas_coords,
                values=values,
                alternative_tile=alternative_tile,
            ),
            session_id=session_id,
        )

    async def tile_set_atlas_tile_collision_set(
        self,
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        physics_layer: int,
        polygons: list[dict[str, Any]],
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_source_id(source_id)
        _validate_tilemap_vector2i(atlas_coords, "atlas_coords", nonnegative=True)
        _validate_tile_set_layer_index(physics_layer, "physics_layer")
        _validate_tile_collision_polygons(polygons)
        _validate_atlas_alternative_tile(alternative_tile)
        return await self.bridge.call(
            "tile_set_atlas_tile_collision_set",
            _scene_params(
                scene_file,
                path=path,
                source_id=source_id,
                atlas_coords=atlas_coords,
                physics_layer=physics_layer,
                polygons=polygons,
                alternative_tile=alternative_tile,
            ),
            session_id=session_id,
        )

    async def tile_set_atlas_tile_navigation_set(
        self,
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
        _validate_node_path(path)
        _validate_tilemap_source_id(source_id)
        _validate_tilemap_vector2i(atlas_coords, "atlas_coords", nonnegative=True)
        _validate_tile_set_layer_index(navigation_layer, "navigation_layer")
        _validate_atlas_alternative_tile(alternative_tile)
        if not isinstance(clear, bool):
            raise ValueError("clear must be a boolean")
        params = _scene_params(
            scene_file,
            path=path,
            source_id=source_id,
            atlas_coords=atlas_coords,
            navigation_layer=navigation_layer,
            clear=clear,
            alternative_tile=alternative_tile,
        )
        if clear:
            if vertices is not None or polygons is not None or agent_radius is not None:
                raise ValueError(
                    "clear cannot be combined with vertices, polygons, or agent_radius"
                )
        else:
            if vertices is None or polygons is None:
                raise ValueError("vertices and polygons are required unless clear is true")
            _validate_tile_navigation_geometry(vertices, polygons)
            requested_radius = 0.0 if agent_radius is None else agent_radius
            _validate_navigation_polygon_agent_radius(requested_radius)
            params["vertices"] = vertices
            params["polygons"] = polygons
            params["agent_radius"] = requested_radius
        return await self.bridge.call(
            "tile_set_atlas_tile_navigation_set",
            params,
            session_id=session_id,
        )

    async def tile_set_atlas_tile_occlusion_set(
        self,
        path: str,
        source_id: int,
        atlas_coords: dict[str, int],
        occlusion_layer: int,
        polygons: list[dict[str, Any]],
        alternative_tile: int = 0,
        session_id: str | None = None,
        scene_file: str = "",
    ) -> dict[str, Any]:
        _validate_node_path(path)
        _validate_tilemap_source_id(source_id)
        _validate_tilemap_vector2i(atlas_coords, "atlas_coords", nonnegative=True)
        _validate_tile_set_layer_index(occlusion_layer, "occlusion_layer")
        _validate_tile_occlusion_polygons(polygons)
        _validate_atlas_alternative_tile(alternative_tile)
        return await self.bridge.call(
            "tile_set_atlas_tile_occlusion_set",
            _scene_params(
                scene_file,
                path=path,
                source_id=source_id,
                atlas_coords=atlas_coords,
                occlusion_layer=occlusion_layer,
                polygons=polygons,
                alternative_tile=alternative_tile,
            ),
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


def _validate_runtime_screenshot_dimension(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1024:
        raise ValueError(f"{label} must be an integer between 1 and 1024")


def _validate_runtime_request_id(value: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("request_id must contain between 1 and 128 characters")


def _validate_runtime_audio_action(value: str) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if normalized not in {"get", "play", "stop", "seek"}:
        raise ValueError("action must be get, play, stop, or seek")
    return normalized


def _validate_runtime_audio_position(value: float) -> None:
    if not _is_finite_number(value) or not 0 <= float(value) <= 3600:
        raise ValueError("position_seconds must be a finite number between 0 and 3600")


def _validate_runtime_input_events(events: list[dict[str, Any]]) -> None:
    if not isinstance(events, list) or not 1 <= len(events) <= 64:
        raise ValueError("events must contain between 1 and 64 items")
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each input event must be an object")
        event_type = event.get("type")
        if event_type == "action":
            _validate_runtime_action_event(event)
        elif event_type == "key":
            _validate_runtime_key_event(event)
        elif event_type == "mouse_button":
            _validate_runtime_mouse_button_event(event)
        elif event_type == "mouse_motion":
            _validate_runtime_mouse_motion_event(event)
        else:
            raise ValueError("input event type must be action, key, mouse_button, or mouse_motion")


def _validate_runtime_action_event(event: dict[str, Any]) -> None:
    action = event.get("action")
    if not isinstance(action, str) or not 1 <= len(action) <= 256:
        raise ValueError("action input events require action with 1 to 256 characters")
    _validate_boolean(event.get("pressed"), "pressed")


def _validate_runtime_key_event(event: dict[str, Any]) -> None:
    _validate_boolean(event.get("pressed"), "pressed")
    key_fields = ("keycode", "physical_keycode", "unicode")
    supplied = [field for field in key_fields if field in event]
    if len(supplied) != 1:
        raise ValueError(
            "key input events require exactly one keycode, physical_keycode, or unicode"
        )
    value = event[supplied[0]]
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0x7FFFFFFF:
        raise ValueError(f"{supplied[0]} must be an integer between 0 and 2147483647")
    for modifier in ("echo", "shift", "alt", "ctrl", "meta"):
        if modifier in event:
            _validate_boolean(event[modifier], modifier)


def _validate_runtime_mouse_button_event(event: dict[str, Any]) -> None:
    button = event.get("button")
    if isinstance(button, bool) or not isinstance(button, int) or not 1 <= button <= 8:
        raise ValueError("mouse_button input events require button between 1 and 8")
    _validate_boolean(event.get("pressed"), "pressed")
    _validate_runtime_position(event.get("position"), "position")
    if "double_click" in event:
        _validate_boolean(event["double_click"], "double_click")


def _validate_runtime_mouse_motion_event(event: dict[str, Any]) -> None:
    _validate_runtime_position(event.get("position"), "position")
    _validate_runtime_position(event.get("relative"), "relative")


def _validate_runtime_position(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        raise ValueError(f"{label} must be an object with x and y")
    if any(
        not _is_finite_number(value[axis]) or abs(float(value[axis])) > 100_000
        for axis in ("x", "y")
    ):
        raise ValueError(f"{label} coordinates must be finite numbers from -100000 to 100000")


def _validate_node_name(name: str) -> None:
    if not name or len(name) > 256:
        raise ValueError("name must contain between 1 and 256 characters")


def _validate_scene_root_type(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("root_type must contain between 1 and 256 characters")


def _validate_new_scene_path(value: str) -> None:
    _validate_project_resource_path(value, "scene_path")
    if not value.endswith(".tscn"):
        raise ValueError("new scene_path must end with .tscn")


def _validate_existing_scene_path(value: str) -> None:
    _validate_project_resource_path(value, "scene_path")
    if not value.endswith((".tscn", ".scn")):
        raise ValueError("scene_path must end with .tscn or .scn")


def _validate_signal_member(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"{label} must contain between 1 and 256 characters")


def _validate_animation_name(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 256 or "/" in value:
        raise ValueError(
            "animation must contain between 1 and 256 characters and cannot contain '/'"
        )


def _validate_animation_library(value: str) -> None:
    if not isinstance(value, str) or len(value) > 256 or "/" in value:
        raise ValueError("library cannot exceed 256 characters or contain '/'")


def _validate_animation_length(value: float) -> None:
    if not _is_finite_number(value) or not 0 < float(value) <= 3600:
        raise ValueError("length must be a finite number between 0 and 3600")


def _validate_loop_mode(value: str) -> None:
    if value not in {"none", "linear", "pingpong"}:
        raise ValueError("loop_mode must be none, linear, or pingpong")


def _validate_interpolation(value: str) -> None:
    if value not in {"nearest", "linear", "cubic", "linear_angle", "cubic_angle"}:
        raise ValueError("interpolation is not supported")


def _validate_update_mode(value: str) -> None:
    if value not in {"continuous", "discrete", "capture"}:
        raise ValueError("update_mode must be continuous, discrete, or capture")


def _validate_animation_property(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 256 or ":" in value:
        raise ValueError("property must be a single name between 1 and 256 characters")


def _validate_animation_keys(keys: list[dict[str, Any]]) -> None:
    if not isinstance(keys, list) or not keys:
        raise ValueError("keys must be a non-empty array")
    if len(keys) > 512:
        raise ValueError("keys can contain at most 512 entries")
    times: list[float] = []
    for key in keys:
        if not isinstance(key, dict) or "time" not in key or "value" not in key:
            raise ValueError("each key requires time and value")
        _validate_key_time(key["time"])
        if not _is_json_bind_value(key["value"]):
            raise ValueError("key values must be bounded JSON-compatible values")
        if "transition" in key:
            _validate_transition(key["transition"])
        time = float(key["time"])
        if any(math.isclose(time, existing, rel_tol=1e-9, abs_tol=1e-9) for existing in times):
            raise ValueError("keys cannot contain duplicate times")
        times.append(time)


def _validate_track_index(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("track_index must be a non-negative integer")


def _validate_key_time(value: float) -> None:
    if not _is_finite_number(value) or float(value) < 0:
        raise ValueError("time must be a finite non-negative number")


def _validate_transition(value: float) -> None:
    if not _is_finite_number(value):
        raise ValueError("transition must be a finite number")


def _validate_boolean(value: bool, label: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")


def _validate_layout_sides(
    sides: dict[str, float],
    label: str,
    minimum: float,
    maximum: float,
) -> None:
    expected = {"left", "top", "right", "bottom"}
    if not isinstance(sides, dict) or set(sides) != expected:
        raise ValueError(f"{label} must contain exactly left, top, right, and bottom")
    if any(
        not _is_finite_number(value) or not minimum <= float(value) <= maximum
        for value in sides.values()
    ):
        raise ValueError(f"{label} values must be finite numbers between {minimum} and {maximum}")


def _validate_layout_preset(value: str) -> None:
    if value not in {
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
        "center_left",
        "center_top",
        "center_right",
        "center_bottom",
        "center",
        "left_wide",
        "top_wide",
        "right_wide",
        "bottom_wide",
        "vcenter_wide",
        "hcenter_wide",
        "full_rect",
    }:
        raise ValueError("preset is not supported")


def _validate_layout_resize_mode(value: str) -> None:
    if value not in {"min_size", "keep_width", "keep_height", "keep_size"}:
        raise ValueError("resize_mode is not supported")


def _validate_layout_margin(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 1_000_000:
        raise ValueError("margin must be an integer between -1000000 and 1000000")


def _validate_container_child_page(offset: int, limit: int) -> None:
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 256:
        raise ValueError("child_offset must be an integer between 0 and 256")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
        raise ValueError("child_limit must be an integer between 1 and 256")


def _validate_container_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "accessibility_region",
        "alignment",
        "columns",
        "use_top_left",
        "ratio",
        "stretch_mode",
        "alignment_horizontal",
        "alignment_vertical",
        "last_wrap_alignment",
        "reverse_fill",
        "split_offsets",
        "collapsed",
        "dragging_enabled",
        "dragger_visibility",
        "touch_dragger_enabled",
        "drag_nested_intersections",
        "drag_area_margin_begin",
        "drag_area_margin_end",
        "drag_area_offset",
        "drag_area_highlight_in_editor",
        "follow_focus",
        "draw_focus_border",
        "scroll_horizontal",
        "scroll_vertical",
        "scroll_horizontal_custom_step",
        "scroll_vertical_custom_step",
        "horizontal_scroll_mode",
        "vertical_scroll_mode",
        "scroll_horizontal_by_default",
        "scroll_deadzone",
        "scroll_hint_mode",
        "tile_scroll_hint",
        "tab_alignment",
        "current_tab",
        "tabs_position",
        "clip_tabs",
        "tabs_visible",
        "switch_on_drag_hover",
        "drag_to_rearrange_enabled",
        "tabs_rearrange_group",
        "use_hidden_tabs_for_min_size",
        "tab_focus_mode",
        "deselect_enabled",
        "stretch",
        "stretch_shrink",
        "mouse_target",
    }
    _validate_draw_2d_property_names(properties, allowed, "Container", maximum=32)
    for name in {
        "accessibility_region",
        "use_top_left",
        "reverse_fill",
        "collapsed",
        "dragging_enabled",
        "touch_dragger_enabled",
        "drag_nested_intersections",
        "drag_area_highlight_in_editor",
        "follow_focus",
        "draw_focus_border",
        "scroll_horizontal_by_default",
        "tile_scroll_hint",
        "clip_tabs",
        "tabs_visible",
        "switch_on_drag_hover",
        "drag_to_rearrange_enabled",
        "use_hidden_tabs_for_min_size",
        "deselect_enabled",
        "stretch",
        "mouse_target",
    } & properties.keys():
        _validate_boolean(properties[name], name)
    for name, choices in {
        "alignment": {"begin", "center", "end"},
        "alignment_horizontal": {"begin", "center", "end"},
        "alignment_vertical": {"begin", "center", "end"},
        "stretch_mode": {"width_controls_height", "height_controls_width", "fit", "cover"},
        "last_wrap_alignment": {"inherit", "begin", "center", "end"},
        "dragger_visibility": {"visible", "hidden", "hidden_and_collapsed"},
        "horizontal_scroll_mode": {
            "disabled",
            "auto",
            "always_show",
            "never_show",
            "reserve",
            "maximize_first",
        },
        "vertical_scroll_mode": {
            "disabled",
            "auto",
            "always_show",
            "never_show",
            "reserve",
            "maximize_first",
        },
        "scroll_hint_mode": {"disabled", "all", "top_and_left", "bottom_and_right"},
        "tab_alignment": {"left", "center", "right"},
        "tabs_position": {"top", "bottom"},
        "tab_focus_mode": {"none", "click", "all"},
    }.items():
        _validate_button_enum(properties, name, choices)
    if "ratio" in properties:
        _validate_viewport_number(properties["ratio"], "ratio", minimum=0.001, maximum=1_000_000.0)
    for name in {
        "scroll_horizontal_custom_step",
        "scroll_vertical_custom_step",
    } & properties.keys():
        _validate_viewport_number(properties[name], name, minimum=-1.0, maximum=4096.0)
    for name, minimum, maximum in (
        ("columns", 1, 1024),
        ("drag_area_margin_begin", -1_000_000, 1_000_000),
        ("drag_area_margin_end", -1_000_000, 1_000_000),
        ("drag_area_offset", -1_000_000, 1_000_000),
        ("scroll_horizontal", 0, 1_000_000),
        ("scroll_vertical", 0, 1_000_000),
        ("scroll_deadzone", 0, 1_000_000),
        ("current_tab", -1, 4096),
        ("tabs_rearrange_group", -1, 1_000_000),
        ("stretch_shrink", 1, 1_000_000),
    ):
        if name in properties:
            _validate_container_integer(properties[name], name, minimum, maximum)
    if "split_offsets" in properties:
        offsets = properties["split_offsets"]
        if not isinstance(offsets, list) or len(offsets) > 256:
            raise ValueError("split_offsets must contain at most 256 integer pixel offsets")
        for index, offset in enumerate(offsets):
            _validate_container_integer(offset, f"split_offsets[{index}]", -1_000_000, 1_000_000)


def _validate_container_child_layout_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "custom_minimum_size",
        "size_flags_horizontal",
        "size_flags_vertical",
        "size_flags_stretch_ratio",
    }
    _validate_draw_2d_property_names(properties, allowed, "container child layout", maximum=4)
    if "custom_minimum_size" in properties:
        value = properties["custom_minimum_size"]
        if (
            not isinstance(value, dict)
            or set(value) != {"x", "y"}
            or any(
                not _is_finite_number(value[axis])
                or not 0.0 <= float(value[axis]) <= 1_000_000.0
                for axis in ("x", "y")
            )
        ):
            raise ValueError(
                "custom_minimum_size values must be finite numbers between 0 and 1000000"
            )
    for name in {"size_flags_horizontal", "size_flags_vertical"} & properties.keys():
        _validate_container_size_flags(properties[name], name)
    if "size_flags_stretch_ratio" in properties:
        _validate_viewport_number(
            properties["size_flags_stretch_ratio"],
            "size_flags_stretch_ratio",
            minimum=0.0,
            maximum=1_000_000.0,
        )


def _validate_container_integer(value: Any, label: str, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")


def _validate_container_size_flags(value: Any, label: str) -> None:
    allowed = {"fill", "expand", "shrink_begin", "shrink_center", "shrink_end"}
    if (
        not isinstance(value, list)
        or len(value) > 4
        or any(not isinstance(flag, str) or flag.strip().lower() not in allowed for flag in value)
        or len({flag.strip().lower() for flag in value}) != len(value)
    ):
        raise ValueError(f"{label} must contain unique supported size flag names")
    normalized = {flag.strip().lower() for flag in value}
    if "shrink_begin" in normalized and len(normalized) != 1:
        raise ValueError("shrink_begin cannot be combined with other size flags")
    if len(normalized & {"shrink_center", "shrink_end"}) > 1:
        raise ValueError(f"{label} can contain only one shrink flag")


def _validate_stylebox_state(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 256 or "/" in value:
        raise ValueError("state must contain between 1 and 256 characters and cannot contain '/'")


def _validate_stylebox_properties(properties: dict[str, Any]) -> None:
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > 48:
        raise ValueError("properties can contain at most 48 entries")
    if any(
        not isinstance(name, str) or not name or len(name) > 256 or not _is_json_bind_value(value)
        for name, value in properties.items()
    ):
        raise ValueError("properties must contain bounded JSON-compatible values")


def _validate_theme_resource_name(value: str) -> None:
    if not isinstance(value, str) or len(value) > 256 or "/" in value or ":" in value:
        raise ValueError(
            "resource_name must be at most 256 characters and cannot contain '/' or ':'"
        )


def _validate_optional_project_resource_path(value: str, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a res:// path or an empty string")
    if not value:
        return
    _validate_project_resource_path(value, label)


def _validate_project_resource_path(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("res://")
        or len(value) > 4096
        or "/../" in value
        or value.endswith("/..")
    ):
        raise ValueError(f"{label} must stay inside res://")


def _validate_theme_default_names(defaults: list[str]) -> None:
    if not isinstance(defaults, list) or not 1 <= len(defaults) <= 3:
        raise ValueError("defaults must contain between 1 and 3 names")
    allowed = {"font", "font_size", "base_scale"}
    if any(not isinstance(name, str) or name not in allowed for name in defaults):
        raise ValueError("defaults must contain only font, font_size, or base_scale")
    if len(set(defaults)) != len(defaults):
        raise ValueError("defaults cannot contain duplicates")


def _validate_theme_item_identity(item_type: str, theme_type: str, name: str) -> None:
    if item_type not in {"color", "constant", "font_size", "font", "icon", "stylebox_flat"}:
        raise ValueError("item_type is not supported")
    for label, value in (("theme_type", theme_type), ("name", name)):
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 256
            or "/" in value
            or ":" in value
        ):
            raise ValueError(f"{label} must be a non-empty Theme identifier")


def _validate_theme_item_value(item_type: str, value: Any) -> None:
    if item_type == "color":
        if not isinstance(value, str) and not (
            isinstance(value, dict) and set(value) in ({"r", "g", "b"}, {"r", "g", "b", "a"})
        ):
            raise ValueError("color value must be a color string or r/g/b/a object")
        return
    if item_type == "constant":
        if not _is_finite_number(value) or not float(value).is_integer() or abs(value) > 1_000_000:
            raise ValueError("constant value must be an integer between -1000000 and 1000000")
        return
    if item_type == "font_size":
        _validate_theme_font_size(value)
        return
    if item_type == "font":
        _validate_theme_font_value(value)
        return
    if item_type == "icon":
        _validate_project_resource_path(value, "icon value")
        return
    if not isinstance(value, dict) or not value or len(value) > 48:
        raise ValueError(
            "stylebox_flat value must be a non-empty object with at most 48 properties"
        )
    if any(
        not isinstance(name, str)
        or not name
        or len(name) > 256
        or not _is_json_bind_value(property_value)
        for name, property_value in value.items()
    ):
        raise ValueError("stylebox_flat properties must be bounded JSON-compatible values")


def _validate_theme_font_value(value: dict[str, Any]) -> None:
    if not isinstance(value, dict) or set(value) - {"source", "path", "families"}:
        raise ValueError("font must be a source/path or source/families object")
    source = value.get("source")
    if source == "path" and set(value) == {"source", "path"}:
        _validate_project_resource_path(value["path"], "font path")
        return
    if source == "system" and set(value) == {"source", "families"}:
        families = value["families"]
        if (
            not isinstance(families, list)
            or not 1 <= len(families) <= 8
            or any(
                not isinstance(family, str) or not family or len(family) > 256
                for family in families
            )
        ):
            raise ValueError("system font families must contain 1 to 8 non-empty names")
        return
    raise ValueError("font.source must be path or system with the matching fields")


def _validate_theme_font_size(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 4096:
        raise ValueError("font_size must be an integer between 1 and 4096")


def _validate_theme_base_scale(value: float) -> None:
    if not _is_finite_number(value) or not 0.01 <= float(value) <= 100:
        raise ValueError("base_scale must be a finite number between 0.01 and 100")


def _validate_collision_shape_type(value: str) -> None:
    if value not in {
        "circle",
        "rectangle",
        "capsule",
        "segment",
        "separation_ray",
        "world_boundary",
        "convex_polygon",
        "concave_polygon",
    }:
        raise ValueError("shape_type is not supported")


def _validate_collision_shape_properties(shape_type: str, properties: dict[str, Any]) -> None:
    required = {
        "circle": {"radius"},
        "rectangle": {"size"},
        "capsule": {"radius", "height"},
        "segment": {"a", "b"},
        "separation_ray": {"length"},
        "world_boundary": {"normal", "distance"},
        "convex_polygon": {"points"},
        "concave_polygon": {"segments"},
    }[shape_type]
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > 16:
        raise ValueError("properties can contain at most 16 entries")
    if not required.issubset(properties):
        names = ", ".join(sorted(required))
        raise ValueError(f"properties must include {names}")
    if any(
        not isinstance(name, str)
        or not name
        or len(name) > 256
        or not _is_json_bind_value(property_value)
        for name, property_value in properties.items()
    ):
        raise ValueError("properties must contain bounded JSON-compatible values")


def _validate_physics_configuration_properties(
    properties: dict[str, Any], *, allow_empty: bool = False
) -> None:
    if not isinstance(properties, dict):
        raise ValueError("properties must be an object")
    if not properties and not allow_empty:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > 32:
        raise ValueError("properties can contain at most 32 entries")
    if any(
        not isinstance(name, str)
        or not name
        or len(name) > 256
        or not _is_json_bind_value(property_value)
        for name, property_value in properties.items()
    ):
        raise ValueError("properties must contain bounded JSON-compatible values")


def _validate_light_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "enabled",
        "editor_only",
        "color",
        "energy",
        "blend_mode",
        "range_z_min",
        "range_z_max",
        "range_layer_min",
        "range_layer_max",
        "range_item_cull_layers",
        "shadow_enabled",
        "shadow_color",
        "shadow_filter",
        "shadow_filter_smooth",
        "shadow_item_cull_layers",
        "height",
        "texture_path",
        "offset",
        "texture_scale",
        "max_distance",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > 18:
        raise ValueError("properties can contain at most 18 entries")
    if any(not isinstance(name, str) or name not in allowed for name in properties):
        raise ValueError("properties contains an unsupported light property")
    if any(not _is_json_bind_value(value) for value in properties.values()):
        raise ValueError("properties must contain bounded JSON-compatible values")

    for name in ("enabled", "editor_only", "shadow_enabled"):
        if name in properties:
            _validate_boolean(properties[name], name)
    for name in ("color", "shadow_color"):
        if name in properties:
            _validate_light_color(properties[name], name)
    for name, supported in {
        "blend_mode": {"add", "subtract", "mix"},
        "shadow_filter": {"none", "pcf5", "pcf13"},
    }.items():
        if name in properties and (
            not isinstance(properties[name], str)
            or properties[name].strip().lower() not in supported
        ):
            choices = ", ".join(sorted(supported))
            raise ValueError(f"{name} must be one of: {choices}")
    for name in ("range_item_cull_layers", "shadow_item_cull_layers"):
        if name in properties:
            _validate_collision_layer_numbers(properties[name], name)
    for name in ("energy", "shadow_filter_smooth", "height", "texture_scale", "max_distance"):
        if name in properties and not _is_finite_number(properties[name]):
            raise ValueError(f"{name} must be a finite number")
    if "energy" in properties and properties["energy"] < 0:
        raise ValueError("energy must be greater than or equal to zero")
    if "shadow_filter_smooth" in properties and not 0 <= properties["shadow_filter_smooth"] <= 64:
        raise ValueError("shadow_filter_smooth must be between 0 and 64")
    if "height" in properties and properties["height"] < 0:
        raise ValueError("height must be greater than or equal to zero")
    if "texture_scale" in properties and properties["texture_scale"] < 0.01:
        raise ValueError("texture_scale must be greater than or equal to 0.01")
    if "max_distance" in properties and properties["max_distance"] < 0:
        raise ValueError("max_distance must be greater than or equal to zero")
    for name, lower, upper in (
        ("range_z_min", -4096, 4096),
        ("range_z_max", -4096, 4096),
        ("range_layer_min", -(2**31), 2**31 - 1),
        ("range_layer_max", -(2**31), 2**31 - 1),
    ):
        if name in properties and (
            isinstance(properties[name], bool)
            or not isinstance(properties[name], int)
            or not lower <= properties[name] <= upper
        ):
            raise ValueError(f"{name} must be an integer between {lower} and {upper}")
    if "offset" in properties:
        _validate_light_vector2(properties["offset"], "offset")
    if "texture_path" in properties:
        _validate_optional_project_resource_path(properties["texture_path"], "texture_path")


def _validate_sprite_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "texture_path",
        "centered",
        "offset",
        "flip_h",
        "flip_v",
        "hframes",
        "vframes",
        "frame",
        "frame_coords",
        "region_enabled",
        "region_rect",
        "region_filter_clip_enabled",
    }
    _validate_draw_2d_property_names(properties, allowed, "Sprite2D")
    if {"frame", "frame_coords"} <= properties.keys():
        raise ValueError("frame and frame_coords cannot be supplied together")
    if "texture_path" in properties:
        _validate_optional_project_resource_path(properties["texture_path"], "texture_path")
    for name in {
        "centered",
        "flip_h",
        "flip_v",
        "region_enabled",
        "region_filter_clip_enabled",
    } & properties.keys():
        _validate_boolean(properties[name], name)
    if "offset" in properties:
        _validate_draw_2d_vector2(properties["offset"], "offset")
    for name in {"hframes", "vframes"} & properties.keys():
        _validate_draw_2d_integer(properties[name], name, minimum=1, maximum=16_384)
    if "frame" in properties:
        _validate_draw_2d_integer(
            properties["frame"], "frame", minimum=0, maximum=16_384 * 16_384 - 1
        )
    if "frame_coords" in properties:
        _validate_draw_2d_vector2i(properties["frame_coords"], "frame_coords")
    if "region_rect" in properties:
        _validate_draw_2d_rect2(properties["region_rect"], "region_rect")


def _validate_animated_sprite_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "sprite_frames_path",
        "animation",
        "autoplay",
        "frame",
        "frame_progress",
        "speed_scale",
        "centered",
        "offset",
        "flip_h",
        "flip_v",
    }
    _validate_draw_2d_property_names(properties, allowed, "AnimatedSprite2D")
    if "sprite_frames_path" in properties:
        _validate_optional_project_resource_path(
            properties["sprite_frames_path"], "sprite_frames_path"
        )
    if "animation" in properties:
        _validate_sprite_frames_animation_name(properties["animation"], "animation")
    if "autoplay" in properties:
        _validate_optional_sprite_frames_animation_name(properties["autoplay"], "autoplay")
    if "frame" in properties:
        _validate_draw_2d_integer(properties["frame"], "frame", minimum=0, maximum=511)
    for name in {"frame_progress", "speed_scale"} & properties.keys():
        minimum, maximum = (0.0, 1.0) if name == "frame_progress" else (-64.0, 64.0)
        _validate_viewport_number(properties[name], name, minimum=minimum, maximum=maximum)
    for name in {"centered", "flip_h", "flip_v"} & properties.keys():
        _validate_boolean(properties[name], name)
    if "offset" in properties:
        _validate_draw_2d_vector2(properties["offset"], "offset")


def _validate_button_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "disabled",
        "toggle_mode",
        "button_pressed",
        "action_mode",
        "button_mask",
        "keep_pressed_outside",
        "shortcut_feedback",
        "shortcut_in_tooltip",
        "button_group_path",
        "shortcut_path",
        "text",
        "icon_path",
        "flat",
        "alignment",
        "text_overrun_behavior",
        "autowrap_mode",
        "autowrap_trim_flags",
        "clip_text",
        "icon_alignment",
        "vertical_icon_alignment",
        "expand_icon",
        "text_direction",
        "language",
        "uri",
        "underline",
        "ellipsis_char",
        "texture_normal_path",
        "texture_pressed_path",
        "texture_hover_path",
        "texture_disabled_path",
        "texture_focused_path",
        "click_mask_path",
        "ignore_texture_size",
        "stretch_mode",
        "flip_h",
        "flip_v",
    }
    _validate_draw_2d_property_names(properties, allowed, "BaseButton", maximum=32)
    for name in {
        "disabled",
        "toggle_mode",
        "button_pressed",
        "keep_pressed_outside",
        "shortcut_feedback",
        "shortcut_in_tooltip",
        "flat",
        "clip_text",
        "expand_icon",
        "ignore_texture_size",
        "flip_h",
        "flip_v",
    } & properties.keys():
        _validate_boolean(properties[name], name)
    if properties.get("button_pressed") is True and properties.get("toggle_mode") is False:
        raise ValueError("button_pressed requires toggle_mode to be true")
    for name in {
        "button_group_path",
        "shortcut_path",
        "icon_path",
        "texture_normal_path",
        "texture_pressed_path",
        "texture_hover_path",
        "texture_disabled_path",
        "texture_focused_path",
        "click_mask_path",
    } & properties.keys():
        _validate_optional_project_resource_path(properties[name], name)
    _validate_button_enum(properties, "action_mode", {"press", "release"})
    _validate_button_enum(properties, "alignment", {"left", "center", "right"})
    _validate_button_enum(properties, "icon_alignment", {"left", "center", "right"})
    _validate_button_enum(properties, "vertical_icon_alignment", {"top", "center", "bottom"})
    _validate_button_enum(
        properties,
        "text_overrun_behavior",
        {
            "no_trimming",
            "trim_characters",
            "trim_words",
            "ellipsis",
            "word_ellipsis",
            "ellipsis_force",
            "word_ellipsis_force",
        },
    )
    _validate_button_enum(properties, "autowrap_mode", {"off", "arbitrary", "word", "smart_word"})
    _validate_button_enum(properties, "text_direction", {"auto", "ltr", "rtl", "inherited"})
    _validate_button_enum(properties, "underline", {"always", "on_hover", "never"})
    _validate_button_enum(
        properties,
        "stretch_mode",
        {
            "scale",
            "tile",
            "keep",
            "keep_centered",
            "keep_aspect",
            "keep_aspect_centered",
            "keep_aspect_covered",
        },
    )
    _validate_button_name_list(properties, "button_mask", {"left", "right", "middle"})
    _validate_button_name_list(properties, "autowrap_trim_flags", {"trim_start", "trim_end"})
    for name, maximum in (
        ("text", 4096),
        ("language", 128),
        ("uri", 4096),
    ):
        if name in properties and (
            not isinstance(properties[name], str) or len(properties[name]) > maximum
        ):
            raise ValueError(f"{name} must be a string up to {maximum} characters")
    if "ellipsis_char" in properties and (
        not isinstance(properties["ellipsis_char"], str) or len(properties["ellipsis_char"]) != 1
    ):
        raise ValueError("ellipsis_char must contain exactly one character")


def _validate_button_menu_page(offset: int, limit: int) -> None:
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 256:
        raise ValueError("offset must be an integer between 0 and 256")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
        raise ValueError("limit must be an integer between 1 and 256")


def _validate_button_menu_items(items: list[dict[str, Any]]) -> None:
    if not isinstance(items, list) or not 1 <= len(items) <= 256:
        raise ValueError("items must contain between 1 and 256 entries")
    for index, item in enumerate(items):
        label = f"items[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be an object")
        kind = item.get("kind", "normal")
        if not isinstance(kind, str) or kind.strip().lower() not in {
            "normal",
            "check",
            "radio",
            "multistate",
            "separator",
        }:
            raise ValueError(f"{label}.kind must be normal, check, radio, multistate, or separator")
        normalized_kind = kind.strip().lower()
        allowed = {"kind", "text", "id"}
        if normalized_kind != "separator":
            allowed |= {"icon_path", "metadata", "disabled", "tooltip"}
            if normalized_kind in {"check", "radio"}:
                allowed.add("checked")
            if normalized_kind == "multistate":
                allowed |= {"max_states", "state"}
            allowed |= {
                "accelerator",
                "indent",
                "text_direction",
                "language",
                "auto_translate_mode",
                "icon_max_width",
                "icon_modulate",
            }
        if any(not isinstance(name, str) or name not in allowed for name in item):
            raise ValueError(f"{label} contains an unsupported menu item field")
        text = item.get("text", "")
        if not isinstance(text, str) or len(text) > 4096:
            raise ValueError(f"{label}.text must be a string up to 4096 characters")
        _validate_button_menu_integer(
            item.get("id", index), f"{label}.id", -2_147_483_648, 2_147_483_647
        )
        if normalized_kind == "separator":
            continue
        for name in ("icon_path",):
            if name in item:
                _validate_optional_project_resource_path(item[name], f"{label}.{name}")
        for name in ("disabled", "checked"):
            if name in item:
                _validate_boolean(item[name], f"{label}.{name}")
        if "tooltip" in item and (
            not isinstance(item["tooltip"], str) or len(item["tooltip"]) > 1024
        ):
            raise ValueError(f"{label}.tooltip must be a string up to 1024 characters")
        if "metadata" in item:
            _validate_button_menu_json(item["metadata"], f"{label}.metadata")
        if "accelerator" in item:
            _validate_button_menu_integer(
                item["accelerator"], f"{label}.accelerator", 0, 2_147_483_647
            )
        if "indent" in item:
            _validate_button_menu_integer(item["indent"], f"{label}.indent", 0, 64)
        if "icon_max_width" in item:
            _validate_button_menu_integer(
                item["icon_max_width"], f"{label}.icon_max_width", 0, 4096
            )
        for name, choices in {
            "text_direction": {"auto", "ltr", "rtl", "inherited"},
            "auto_translate_mode": {"inherit", "always", "disabled"},
        }.items():
            if name in item and (
                not isinstance(item[name], str) or item[name].strip().lower() not in choices
            ):
                raise ValueError(f"{label}.{name} must be one of: {', '.join(sorted(choices))}")
        if "language" in item and (
            not isinstance(item["language"], str) or len(item["language"]) > 128
        ):
            raise ValueError(f"{label}.language must be a string up to 128 characters")
        if "icon_modulate" in item:
            _validate_light_color(item["icon_modulate"], f"{label}.icon_modulate")
        if normalized_kind == "multistate":
            _validate_button_menu_integer(item.get("max_states"), f"{label}.max_states", 2, 256)
            _validate_button_menu_integer(
                item.get("state", 0), f"{label}.state", 0, int(item["max_states"]) - 1
            )


def _validate_button_menu_integer(value: Any, label: str, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")


def _validate_button_menu_json(value: Any, label: str, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError(f"{label} nesting exceeds 8 levels")
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise ValueError(f"{label} must contain only finite numbers")
    if isinstance(value, list):
        if len(value) > 512:
            raise ValueError(f"{label} arrays can contain at most 512 values")
        for entry in value:
            _validate_button_menu_json(entry, label, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 512 or any(not isinstance(key, str) for key in value):
            raise ValueError(f"{label} objects require at most 512 string keys")
        for entry in value.values():
            _validate_button_menu_json(entry, label, depth + 1)
        return
    raise ValueError(f"{label} must contain only JSON-compatible values")


def _validate_button_enum(properties: dict[str, Any], name: str, allowed: set[str]) -> None:
    if name not in properties:
        return
    value = properties[name]
    if not isinstance(value, str) or value.strip().lower() not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}")


def _validate_button_name_list(properties: dict[str, Any], name: str, allowed: set[str]) -> None:
    if name not in properties:
        return
    value = properties[name]
    if (
        not isinstance(value, list)
        or len(value) > len(allowed)
        or any(not isinstance(item, str) or item.strip().lower() not in allowed for item in value)
        or len({item.strip().lower() for item in value}) != len(value)
    ):
        raise ValueError(f"{name} must contain unique values from: {', '.join(sorted(allowed))}")


def _validate_sprite_frames_animation_name(value: Any, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 128
        or "/" in value
        or ":" in value
    ):
        raise ValueError(f"{label} must be a non-empty animation name up to 128 characters")


def _validate_optional_sprite_frames_animation_name(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an animation name or an empty string")
    if value.strip():
        _validate_sprite_frames_animation_name(value, label)


def _validate_sprite_frames_page(frame_offset: int, frame_limit: int) -> None:
    _validate_draw_2d_integer(frame_offset, "frame_offset", minimum=0, maximum=2**31 - 1)
    _validate_draw_2d_integer(frame_limit, "frame_limit", minimum=1, maximum=256)


def _validate_sprite_frames_upsert(
    speed: float | None, loop_mode: str | None, frames: list[dict[str, Any]] | None
) -> None:
    if speed is not None:
        _validate_viewport_number(speed, "speed", minimum=0.0, maximum=1_000.0)
    if loop_mode is not None and (
        not isinstance(loop_mode, str)
        or loop_mode.strip().lower() not in {"none", "linear", "pingpong"}
    ):
        raise ValueError("loop_mode must be one of: linear, none, pingpong")
    if frames is None:
        return
    if not isinstance(frames, list) or len(frames) > 512:
        raise ValueError("frames must contain at most 512 entries")
    for index, frame in enumerate(frames):
        if (
            not isinstance(frame, dict)
            or set(frame) - {"texture_path", "duration"}
            or "texture_path" not in frame
        ):
            raise ValueError(
                f"frames[{index}] must contain texture_path and optional duration"
            )
        _validate_project_resource_path(frame["texture_path"], f"frames[{index}].texture_path")
        if "duration" in frame:
            _validate_viewport_number(
                frame["duration"],
                f"frames[{index}].duration",
                minimum=0.001,
                maximum=3600.0,
            )


def _validate_line_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "points",
        "closed",
        "width",
        "width_curve_path",
        "default_color",
        "gradient_path",
        "texture_path",
        "texture_mode",
        "joint_mode",
        "begin_cap_mode",
        "end_cap_mode",
        "sharp_limit",
        "round_precision",
        "antialiased",
    }
    _validate_draw_2d_property_names(properties, allowed, "Line2D")
    if "points" in properties:
        _validate_draw_2d_points(properties["points"], "points")
    for name in {"closed", "antialiased"} & properties.keys():
        _validate_boolean(properties[name], name)
    if (
        properties.get("closed") is True
        and "points" in properties
        and 0 < len(properties["points"]) < 3
    ):
        raise ValueError("closed Line2D requires zero or at least three points")
    if "width" in properties:
        _validate_viewport_number(properties["width"], "width", minimum=0.0, maximum=1_000_000.0)
    for name in {"width_curve_path", "gradient_path", "texture_path"} & properties.keys():
        _validate_optional_project_resource_path(properties[name], name)
    if "default_color" in properties:
        _validate_light_color(properties["default_color"], "default_color")
    _validate_draw_2d_enum(properties, "texture_mode", {"none", "tile", "stretch"})
    _validate_draw_2d_enum(properties, "joint_mode", {"sharp", "bevel", "round"})
    for name in {"begin_cap_mode", "end_cap_mode"}:
        _validate_draw_2d_enum(properties, name, {"none", "box", "round"})
    if "sharp_limit" in properties:
        _validate_viewport_number(
            properties["sharp_limit"], "sharp_limit", minimum=0.0, maximum=1_000.0
        )
    if "round_precision" in properties:
        _validate_draw_2d_integer(
            properties["round_precision"], "round_precision", minimum=1, maximum=32
        )


def _validate_polygon_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "polygon",
        "uv",
        "vertex_colors",
        "color",
        "texture_path",
        "texture_offset",
        "texture_rotation",
        "texture_scale",
        "invert_enabled",
        "invert_border",
        "antialiased",
        "offset",
    }
    _validate_draw_2d_property_names(properties, allowed, "Polygon2D")
    if "polygon" in properties:
        _validate_draw_2d_points(properties["polygon"], "polygon")
        if 0 < len(properties["polygon"]) < 3:
            raise ValueError("polygon must be empty or contain at least three points")
    if "uv" in properties:
        _validate_draw_2d_points(properties["uv"], "uv")
    if "vertex_colors" in properties:
        _validate_draw_2d_colors(properties["vertex_colors"], "vertex_colors")
    if (
        "polygon" in properties
        and "uv" in properties
        and properties["uv"]
        and len(properties["uv"]) != len(properties["polygon"])
    ):
        raise ValueError("uv must be empty or contain one entry per polygon point")
    if (
        "polygon" in properties
        and "vertex_colors" in properties
        and properties["vertex_colors"]
        and len(properties["vertex_colors"]) != len(properties["polygon"])
    ):
        raise ValueError("vertex_colors must be empty or contain one entry per polygon point")
    if "color" in properties:
        _validate_light_color(properties["color"], "color")
    if "texture_path" in properties:
        _validate_optional_project_resource_path(properties["texture_path"], "texture_path")
    for name in {"texture_offset", "offset"} & properties.keys():
        _validate_draw_2d_vector2(properties[name], name)
    if "texture_rotation" in properties:
        _validate_viewport_number(
            properties["texture_rotation"],
            "texture_rotation",
            minimum=-36_000.0,
            maximum=36_000.0,
        )
    if "texture_scale" in properties:
        _validate_draw_2d_vector2(properties["texture_scale"], "texture_scale")
        if math.isclose(
            float(properties["texture_scale"]["x"]), 0.0, abs_tol=1e-12
        ) or math.isclose(float(properties["texture_scale"]["y"]), 0.0, abs_tol=1e-12):
            raise ValueError("texture_scale components must be finite and non-zero")
    for name in {"invert_enabled", "antialiased"} & properties.keys():
        _validate_boolean(properties[name], name)
    if "invert_border" in properties:
        _validate_viewport_number(
            properties["invert_border"], "invert_border", minimum=0.0, maximum=1_000_000.0
        )


def _validate_draw_2d_property_names(
    properties: dict[str, Any], allowed: set[str], type_name: str, *, maximum: int = 20
) -> None:
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > maximum:
        raise ValueError(f"properties can contain at most {maximum} entries")
    if any(not isinstance(name, str) or name not in allowed for name in properties):
        raise ValueError(f"properties contains an unsupported {type_name} property")


def _validate_draw_2d_vector2(value: Any, label: str) -> None:
    _validate_viewport_vector2(value, label)
    if any(abs(float(value[axis])) > 1_000_000.0 for axis in ("x", "y")):
        raise ValueError(f"{label} coordinates must be between -1000000 and 1000000")


def _validate_draw_2d_vector2i(value: Any, label: str) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"x", "y"}
        or any(
            isinstance(value[axis], bool) or not isinstance(value[axis], int) for axis in ("x", "y")
        )
    ):
        raise ValueError(f"{label} must contain integral x and y values")


def _validate_draw_2d_rect2(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"position", "size"}:
        raise ValueError(f"{label} must contain position and size Vector2 values")
    _validate_draw_2d_vector2(value["position"], f"{label}.position")
    _validate_draw_2d_vector2(value["size"], f"{label}.size")
    if value["size"]["x"] < 0 or value["size"]["y"] < 0:
        raise ValueError(f"{label} size must be non-negative")


def _validate_draw_2d_points(value: Any, label: str) -> None:
    if not isinstance(value, list) or len(value) > 512:
        raise ValueError(f"{label} must contain at most 512 Vector2 values")
    for index, point in enumerate(value):
        _validate_draw_2d_vector2(point, f"{label}[{index}]")


def _validate_draw_2d_colors(value: Any, label: str) -> None:
    if not isinstance(value, list) or len(value) > 512:
        raise ValueError(f"{label} must contain at most 512 Color values")
    for index, color in enumerate(value):
        _validate_light_color(color, f"{label}[{index}]")


def _validate_draw_2d_integer(value: Any, label: str, *, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")


def _validate_draw_2d_enum(properties: dict[str, Any], name: str, allowed: set[str]) -> None:
    if name not in properties:
        return
    value = properties[name]
    if not isinstance(value, str) or value.strip().lower() not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}")


def _validate_viewport_configuration_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "anchor_mode",
        "autoscroll",
        "custom_viewport_path",
        "drag_bottom_margin",
        "drag_horizontal_enabled",
        "drag_horizontal_offset",
        "drag_left_margin",
        "drag_right_margin",
        "drag_top_margin",
        "drag_vertical_enabled",
        "drag_vertical_offset",
        "editor_draw_drag_margin",
        "editor_draw_limits",
        "editor_draw_screen",
        "enabled",
        "follow_viewport",
        "follow_viewport_enabled",
        "follow_viewport_scale",
        "ignore_camera_scroll",
        "ignore_rotation",
        "layer",
        "limit_begin",
        "limit_bottom",
        "limit_enabled",
        "limit_end",
        "limit_left",
        "limit_right",
        "limit_smoothed",
        "limit_top",
        "offset",
        "position_smoothing_enabled",
        "position_smoothing_speed",
        "process_callback",
        "repeat_size",
        "repeat_times",
        "rotation",
        "rotation_smoothing_enabled",
        "rotation_smoothing_speed",
        "scale",
        "screen_offset",
        "scroll_offset",
        "scroll_scale",
        "transform",
        "visible",
        "zoom",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > 32:
        raise ValueError("properties can contain at most 32 entries")
    if any(not isinstance(name, str) or name not in allowed for name in properties):
        raise ValueError("properties contains an unsupported viewport property")
    if any(not _is_json_bind_value(value) for value in properties.values()):
        raise ValueError("properties must contain bounded JSON-compatible values")

    boolean_properties = {
        "drag_horizontal_enabled",
        "drag_vertical_enabled",
        "editor_draw_drag_margin",
        "editor_draw_limits",
        "editor_draw_screen",
        "enabled",
        "follow_viewport",
        "follow_viewport_enabled",
        "ignore_camera_scroll",
        "ignore_rotation",
        "limit_enabled",
        "limit_smoothed",
        "position_smoothing_enabled",
        "rotation_smoothing_enabled",
        "visible",
    }
    for name in boolean_properties & properties.keys():
        _validate_boolean(properties[name], name)

    for name, supported in {
        "anchor_mode": {"fixed_top_left", "drag_center"},
        "process_callback": {"physics", "idle"},
    }.items():
        if name in properties and (
            not isinstance(properties[name], str)
            or properties[name].strip().lower() not in supported
        ):
            choices = ", ".join(sorted(supported))
            raise ValueError(f"{name} must be one of: {choices}")

    vector_properties = {
        "autoscroll",
        "limit_begin",
        "limit_end",
        "offset",
        "repeat_size",
        "scale",
        "screen_offset",
        "scroll_offset",
        "scroll_scale",
        "zoom",
    }
    for name in vector_properties & properties.keys():
        _validate_viewport_vector2(properties[name], name)
    if "transform" in properties:
        _validate_viewport_transform2d(properties["transform"])

    if "custom_viewport_path" in properties:
        custom_viewport_path = properties["custom_viewport_path"]
        if not isinstance(custom_viewport_path, str):
            raise ValueError("custom_viewport_path must be a scene path or an empty string")
        if custom_viewport_path.strip():
            _validate_node_path(custom_viewport_path.strip())

    integer_properties = {"limit_bottom", "limit_left", "limit_right", "limit_top", "layer"}
    for name in integer_properties & properties.keys():
        value = properties[name]
        if isinstance(value, bool) or not isinstance(value, int) or not -(2**31) <= value < 2**31:
            raise ValueError(f"{name} must be a signed 32-bit integer")
    if "repeat_times" in properties:
        value = properties["repeat_times"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 128:
            raise ValueError("repeat_times must be an integer between 1 and 128")

    drag_margin_properties = {
        "drag_bottom_margin",
        "drag_left_margin",
        "drag_right_margin",
        "drag_top_margin",
    }
    for name in drag_margin_properties & properties.keys():
        _validate_viewport_number(properties[name], name, minimum=0.0, maximum=1.0)
    for name in {"drag_horizontal_offset", "drag_vertical_offset"} & properties.keys():
        _validate_viewport_number(properties[name], name, minimum=-1.0, maximum=1.0)
    for name in {"position_smoothing_speed", "rotation_smoothing_speed"} & properties.keys():
        _validate_viewport_number(properties[name], name, minimum=0.0, exclusive_minimum=True)
    if "rotation" in properties:
        _validate_viewport_number(properties["rotation"], "rotation")
    if "follow_viewport_scale" in properties:
        _validate_viewport_number(properties["follow_viewport_scale"], "follow_viewport_scale")
        if math.isclose(float(properties["follow_viewport_scale"]), 0.0, abs_tol=1e-12):
            raise ValueError("follow_viewport_scale must be finite and non-zero")
    if "repeat_size" in properties and (
        properties["repeat_size"]["x"] < 0 or properties["repeat_size"]["y"] < 0
    ):
        raise ValueError("repeat_size components must be greater than or equal to zero")
    for name in ("zoom",):
        if name in properties and (properties[name]["x"] <= 0 or properties[name]["y"] <= 0):
            raise ValueError("zoom components must be finite and greater than zero")
    if "scale" in properties and (
        math.isclose(float(properties["scale"]["x"]), 0.0, abs_tol=1e-12)
        or math.isclose(float(properties["scale"]["y"]), 0.0, abs_tol=1e-12)
    ):
        raise ValueError("scale components must be finite and non-zero")
    if "transform" in properties and {"offset", "rotation", "scale"} & properties.keys():
        raise ValueError("transform cannot be combined with offset, rotation, or scale")


def _validate_path_curve_page(offset: int, limit: int) -> None:
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 1_000_000:
        raise ValueError("offset must be an integer between 0 and 1000000")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 512:
        raise ValueError("limit must be an integer between 1 and 512")


def _validate_path_curve_points(points: list[dict[str, Any]]) -> None:
    if not isinstance(points, list) or len(points) > 512:
        raise ValueError("points must contain at most 512 curve points")
    for point in points:
        _validate_path_curve_point(point)


def _validate_path_curve_point(point: dict[str, Any]) -> None:
    if (
        not isinstance(point, dict)
        or "position" not in point
        or set(point) - {"position", "in", "out"}
    ):
        raise ValueError("point must contain position and optional in/out Vector2 values")
    for name in ("position", "in", "out"):
        if name in point:
            _validate_path_curve_vector2(point[name], f"point.{name}")


def _validate_path_curve_vector2(value: Any, label: str) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"x", "y"}
        or not _is_finite_number(value["x"])
        or not _is_finite_number(value["y"])
    ):
        raise ValueError(f"{label} must contain finite x and y values")


def _validate_path_curve_bake_interval(value: float) -> None:
    if not _is_finite_number(value) or not 0.01 <= float(value) <= 512.0:
        raise ValueError("bake_interval must be a finite number between 0.01 and 512")


def _validate_path_curve_index(
    value: int | None,
    *,
    allow_none: bool = False,
    allow_endpoint: bool = False,
) -> None:
    if value is None and allow_none:
        return
    upper = 512 if allow_endpoint else 511
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= upper:
        raise ValueError(f"index must be an integer between 0 and {upper}")


def _validate_bone_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {"rest", "auto_calculate_length_and_angle", "length", "angle_degrees"}
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported Bone2D property")
    if "rest" in properties:
        _validate_bone_2d_transform(properties["rest"])
    if "auto_calculate_length_and_angle" in properties:
        _validate_boolean(
            properties["auto_calculate_length_and_angle"], "auto_calculate_length_and_angle"
        )
    for name, minimum, maximum in (
        ("length", 1.0, 1024.0),
        ("angle_degrees", -360.0, 360.0),
    ):
        if name in properties:
            _validate_viewport_number(properties[name], name, minimum=minimum, maximum=maximum)
    if properties.get("auto_calculate_length_and_angle") is True and (
        "length" in properties or "angle_degrees" in properties
    ):
        raise ValueError(
            "auto_calculate_length_and_angle cannot be combined with length or angle_degrees"
        )


def _validate_bone_2d_creation(
    rest: dict[str, Any] | None, length: float, angle_degrees: float
) -> None:
    if rest is not None:
        _validate_bone_2d_transform(rest)
    _validate_viewport_number(length, "length", minimum=1.0, maximum=1024.0)
    _validate_viewport_number(angle_degrees, "angle_degrees", minimum=-360.0, maximum=360.0)


def _validate_bone_2d_transform(value: Any) -> None:
    _validate_viewport_transform2d(value)


def _validate_audio_stream_player_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "stream_path",
        "volume_db",
        "pitch_scale",
        "autoplay",
        "max_distance",
        "attenuation",
        "panning_strength",
        "max_polyphony",
        "bus",
        "area_layers",
        "playback_type",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > len(allowed):
        raise ValueError("properties contains too many AudioStreamPlayer2D properties")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported AudioStreamPlayer2D property")
    if "stream_path" in properties:
        _validate_optional_project_resource_path(properties["stream_path"], "stream_path")
    if "autoplay" in properties:
        _validate_boolean(properties["autoplay"], "autoplay")
    if "bus" in properties and (
        not isinstance(properties["bus"], str)
        or not properties["bus"].strip()
        or len(properties["bus"]) > 256
    ):
        raise ValueError("bus must be a non-empty name up to 256 characters")
    if "playback_type" in properties and (
        not isinstance(properties["playback_type"], str)
        or properties["playback_type"].strip().lower() not in {"default", "stream", "sample"}
    ):
        raise ValueError("playback_type must be one of: default, sample, stream")
    for name, minimum, maximum in (
        ("volume_db", -80.0, 120.0),
        ("pitch_scale", 0.01, 16.0),
        ("max_distance", 1.0, 1_000_000.0),
        ("attenuation", 0.0, 128.0),
        ("panning_strength", 0.0, 16.0),
    ):
        if name in properties:
            _validate_viewport_number(properties[name], name, minimum=minimum, maximum=maximum)
    if "max_polyphony" in properties:
        value = properties["max_polyphony"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 256:
            raise ValueError("max_polyphony must be an integer between 1 and 256")
    if "area_layers" in properties:
        _validate_collision_layer_numbers(properties["area_layers"], "area_layers")


def _validate_gpu_particles_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "emitting",
        "amount",
        "amount_ratio",
        "sub_emitter_path",
        "texture_path",
        "process_material_path",
        "lifetime",
        "interp_to_end",
        "one_shot",
        "preprocess",
        "speed_scale",
        "explosiveness",
        "randomness",
        "use_fixed_seed",
        "seed",
        "fixed_fps",
        "interpolate",
        "fractional_delta",
        "collision_base_size",
        "visibility_rect",
        "local_coords",
        "draw_order",
        "trail_enabled",
        "trail_lifetime",
        "trail_sections",
        "trail_section_subdivisions",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > len(allowed):
        raise ValueError("properties contains too many GPUParticles2D properties")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported GPUParticles2D property")
    for name in (
        "emitting",
        "one_shot",
        "use_fixed_seed",
        "interpolate",
        "fractional_delta",
        "local_coords",
        "trail_enabled",
    ):
        if name in properties:
            _validate_boolean(properties[name], name)
    for name in ("texture_path", "process_material_path"):
        if name in properties:
            _validate_optional_project_resource_path(properties[name], name)
    if "sub_emitter_path" in properties:
        value = properties["sub_emitter_path"]
        if not isinstance(value, str):
            raise ValueError("sub_emitter_path must be a scene node path string")
        if value.strip():
            _validate_node_path(value)
    if "draw_order" in properties and (
        not isinstance(properties["draw_order"], str)
        or properties["draw_order"].strip().lower() not in {"index", "lifetime", "reverse_lifetime"}
    ):
        raise ValueError("draw_order must be one of: index, lifetime, reverse_lifetime")
    for name, minimum, maximum in (
        ("amount", 1, 1_000_000),
        ("seed", 0, 4_294_967_295),
        ("fixed_fps", 0, 1000),
        ("trail_sections", 2, 128),
        ("trail_section_subdivisions", 1, 1024),
    ):
        if name in properties and (
            isinstance(properties[name], bool)
            or not isinstance(properties[name], int)
            or not minimum <= properties[name] <= maximum
        ):
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    for name, minimum, maximum in (
        ("amount_ratio", 0.0, 1.0),
        ("lifetime", 0.01, 600.0),
        ("interp_to_end", 0.0, 1.0),
        ("preprocess", 0.0, 600.0),
        ("speed_scale", 0.0, 64.0),
        ("explosiveness", 0.0, 1.0),
        ("randomness", 0.0, 1.0),
        ("collision_base_size", 0.0, 1_000_000.0),
        ("trail_lifetime", 0.01, 600.0),
    ):
        if name in properties:
            _validate_viewport_number(properties[name], name, minimum=minimum, maximum=maximum)
    if "visibility_rect" in properties:
        value = properties["visibility_rect"]
        if not isinstance(value, dict) or set(value) != {"position", "size"}:
            raise ValueError("visibility_rect must contain position and size Vector2 values")
        _validate_viewport_vector2(value["position"], "visibility_rect.position")
        _validate_viewport_vector2(value["size"], "visibility_rect.size")


def _validate_cpu_particles_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "emitting",
        "amount",
        "texture_path",
        "lifetime",
        "one_shot",
        "preprocess",
        "speed_scale",
        "explosiveness",
        "randomness",
        "use_fixed_seed",
        "seed",
        "lifetime_randomness",
        "fixed_fps",
        "fractional_delta",
        "local_coords",
        "draw_order",
        "emission_shape",
        "emission_sphere_radius",
        "emission_rect_extents",
        "emission_points",
        "emission_normals",
        "emission_colors",
        "emission_ring_inner_radius",
        "emission_ring_radius",
        "align_y_to_velocity",
        "direction",
        "spread",
        "gravity",
        "initial_velocity_min",
        "initial_velocity_max",
        "angular_velocity_min",
        "angular_velocity_max",
        "orbit_velocity_min",
        "orbit_velocity_max",
        "linear_accel_min",
        "linear_accel_max",
        "radial_accel_min",
        "radial_accel_max",
        "tangential_accel_min",
        "tangential_accel_max",
        "damping_min",
        "damping_max",
        "angle_min",
        "angle_max",
        "scale_amount_min",
        "scale_amount_max",
        "hue_variation_min",
        "hue_variation_max",
        "anim_speed_min",
        "anim_speed_max",
        "anim_offset_min",
        "anim_offset_max",
        "split_scale",
        "color",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > 64:
        raise ValueError("properties can contain at most 64 CPUParticles2D entries")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported CPUParticles2D property")
    for name in (
        "emitting",
        "one_shot",
        "use_fixed_seed",
        "fractional_delta",
        "local_coords",
        "align_y_to_velocity",
        "split_scale",
    ):
        if name in properties:
            _validate_boolean(properties[name], name)
    if "texture_path" in properties:
        _validate_optional_project_resource_path(properties["texture_path"], "texture_path")
    for name, values in {
        "draw_order": {"index", "lifetime"},
        "emission_shape": {
            "point",
            "sphere",
            "sphere_surface",
            "rectangle",
            "points",
            "directed_points",
            "ring",
        },
    }.items():
        if name in properties and (
            not isinstance(properties[name], str) or properties[name].strip().lower() not in values
        ):
            raise ValueError(f"{name} must be one of: {', '.join(sorted(values))}")
    for name, minimum, maximum in (
        ("amount", 1, 1_000_000),
        ("seed", 0, 4_294_967_295),
        ("fixed_fps", 0, 1000),
    ):
        if name in properties and (
            isinstance(properties[name], bool)
            or not isinstance(properties[name], int)
            or not minimum <= properties[name] <= maximum
        ):
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    for name, minimum, maximum in (
        ("lifetime", 0.01, 600.0),
        ("preprocess", 0.0, 600.0),
        ("speed_scale", 0.0, 64.0),
        ("explosiveness", 0.0, 1.0),
        ("randomness", 0.0, 1.0),
        ("lifetime_randomness", 0.0, 1.0),
        ("emission_sphere_radius", 0.01, 1_000_000.0),
        ("emission_ring_inner_radius", 0.0, 1_000_000.0),
        ("emission_ring_radius", 0.0, 1_000_000.0),
        ("spread", 0.0, 180.0),
        ("initial_velocity_min", -1_000_000.0, 1_000_000.0),
        ("initial_velocity_max", -1_000_000.0, 1_000_000.0),
        ("angular_velocity_min", -1_000_000.0, 1_000_000.0),
        ("angular_velocity_max", -1_000_000.0, 1_000_000.0),
        ("orbit_velocity_min", -1_000_000.0, 1_000_000.0),
        ("orbit_velocity_max", -1_000_000.0, 1_000_000.0),
        ("linear_accel_min", -1_000_000.0, 1_000_000.0),
        ("linear_accel_max", -1_000_000.0, 1_000_000.0),
        ("radial_accel_min", -1_000_000.0, 1_000_000.0),
        ("radial_accel_max", -1_000_000.0, 1_000_000.0),
        ("tangential_accel_min", -1_000_000.0, 1_000_000.0),
        ("tangential_accel_max", -1_000_000.0, 1_000_000.0),
        ("damping_min", 0.0, 1_000_000.0),
        ("damping_max", 0.0, 1_000_000.0),
        ("angle_min", -1_000_000.0, 1_000_000.0),
        ("angle_max", -1_000_000.0, 1_000_000.0),
        ("scale_amount_min", 0.0, 1_000_000.0),
        ("scale_amount_max", 0.0, 1_000_000.0),
        ("hue_variation_min", -1.0, 1.0),
        ("hue_variation_max", -1.0, 1.0),
        ("anim_speed_min", -1_000_000.0, 1_000_000.0),
        ("anim_speed_max", -1_000_000.0, 1_000_000.0),
        ("anim_offset_min", 0.0, 1.0),
        ("anim_offset_max", 0.0, 1.0),
    ):
        if name in properties:
            _validate_viewport_number(properties[name], name, minimum=minimum, maximum=maximum)
    for name in ("emission_rect_extents", "direction", "gravity"):
        if name in properties:
            _validate_viewport_vector2(properties[name], name)
    if "emission_rect_extents" in properties and (
        properties["emission_rect_extents"]["x"] < 0 or properties["emission_rect_extents"]["y"] < 0
    ):
        raise ValueError("emission_rect_extents must have non-negative x and y")
    for name in ("emission_points", "emission_normals"):
        if name in properties:
            _validate_cpu_particles_vector2_array(properties[name], name)
    if "emission_colors" in properties:
        _validate_cpu_particles_color_array(properties["emission_colors"])
    if "color" in properties:
        _validate_light_color(properties["color"], "color")
    if (
        "emission_ring_inner_radius" in properties
        and "emission_ring_radius" in properties
        and properties["emission_ring_inner_radius"] > properties["emission_ring_radius"]
    ):
        raise ValueError("emission_ring_inner_radius cannot exceed emission_ring_radius")


def _validate_cpu_particles_vector2_array(value: Any, label: str) -> None:
    if not isinstance(value, list) or len(value) > 512:
        raise ValueError(f"{label} must contain at most 512 Vector2 values")
    for index, point in enumerate(value):
        _validate_viewport_vector2(point, f"{label}[{index}]")


def _validate_cpu_particles_color_array(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 512:
        raise ValueError("emission_colors must contain at most 512 Color values")
    for index, color in enumerate(value):
        _validate_light_color(color, f"emission_colors[{index}]")


def _validate_cpu_particles_curve_name(value: str) -> None:
    allowed = {
        "initial_velocity",
        "angular_velocity",
        "orbit_velocity",
        "linear_accel",
        "radial_accel",
        "tangential_accel",
        "damping",
        "angle",
        "scale_amount",
        "scale_x",
        "scale_y",
        "hue_variation",
        "anim_speed",
        "anim_offset",
    }
    if not isinstance(value, str) or value.strip().lower() not in allowed:
        raise ValueError(f"curve must be one of: {', '.join(sorted(allowed))}")


def _validate_cpu_particles_gradient_name(value: str) -> None:
    if not isinstance(value, str) or value.strip().lower() not in {"color", "initial_color"}:
        raise ValueError("gradient must be one of: color, initial_color")


def _validate_cpu_particles_curve_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "min_domain",
        "max_domain",
        "min_value",
        "max_value",
        "bake_resolution",
        "points",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported Curve field")
    for name in {"min_domain", "max_domain", "min_value", "max_value"} & properties.keys():
        _validate_viewport_number(properties[name], name, minimum=-1_000_000.0, maximum=1_000_000.0)
    if (
        "min_domain" in properties
        and "max_domain" in properties
        and (properties["min_domain"] >= properties["max_domain"])
    ):
        raise ValueError("min_domain must be less than max_domain")
    if (
        "min_value" in properties
        and "max_value" in properties
        and (properties["min_value"] >= properties["max_value"])
    ):
        raise ValueError("min_value must be less than max_value")
    if "bake_resolution" in properties and (
        isinstance(properties["bake_resolution"], bool)
        or not isinstance(properties["bake_resolution"], int)
        or not 1 <= properties["bake_resolution"] <= 1000
    ):
        raise ValueError("bake_resolution must be an integer between 1 and 1000")
    if "points" in properties:
        _validate_cpu_particles_curve_points(properties["points"])


def _validate_cpu_particles_curve_points(points: Any) -> None:
    if not isinstance(points, list) or len(points) > 512:
        raise ValueError("points must contain at most 512 Curve points")
    previous_x: float | None = None
    allowed = {"position", "left_tangent", "right_tangent", "left_mode", "right_mode"}
    for index, point in enumerate(points):
        if not isinstance(point, dict) or "position" not in point or set(point) - allowed:
            raise ValueError(
                "each Curve point must contain position and optional tangent/mode fields"
            )
        _validate_viewport_vector2(point["position"], f"points[{index}].position")
        position = point["position"]
        if abs(float(position["x"])) > 1_000_000 or abs(float(position["y"])) > 1_000_000:
            raise ValueError(f"points[{index}].position components must be within +/-1000000")
        if previous_x is not None and position["x"] <= previous_x:
            raise ValueError("Curve points must use strictly increasing position.x values")
        previous_x = float(position["x"])
        for name in {"left_tangent", "right_tangent"} & point.keys():
            _validate_viewport_number(
                point[name],
                f"points[{index}].{name}",
                minimum=-1_000_000.0,
                maximum=1_000_000.0,
            )
        for name in {"left_mode", "right_mode"} & point.keys():
            if not isinstance(point[name], str) or point[name].strip().lower() not in {
                "free",
                "linear",
            }:
                raise ValueError(f"points[{index}].{name} must be free or linear")


def _validate_cpu_particles_gradient_properties(properties: dict[str, Any]) -> None:
    allowed = {"points", "interpolation_mode", "interpolation_color_space"}
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported Gradient field")
    if "points" in properties:
        _validate_cpu_particles_gradient_points(properties["points"])
    if "interpolation_mode" in properties and (
        not isinstance(properties["interpolation_mode"], str)
        or properties["interpolation_mode"].strip().lower() not in {"linear", "constant", "cubic"}
    ):
        raise ValueError("interpolation_mode must be linear, constant, or cubic")
    if "interpolation_color_space" in properties and (
        not isinstance(properties["interpolation_color_space"], str)
        or properties["interpolation_color_space"].strip().lower()
        not in {"srgb", "linear_srgb", "oklab"}
    ):
        raise ValueError("interpolation_color_space must be srgb, linear_srgb, or oklab")


def _validate_cpu_particles_gradient_points(points: Any) -> None:
    if not isinstance(points, list) or not 2 <= len(points) <= 512:
        raise ValueError("points must contain between 2 and 512 Gradient points")
    previous_offset: float | None = None
    for index, point in enumerate(points):
        if not isinstance(point, dict) or set(point) != {"offset", "color"}:
            raise ValueError("each Gradient point must contain exactly offset and color")
        _validate_viewport_number(
            point["offset"],
            f"points[{index}].offset",
            minimum=0.0,
            maximum=1.0,
        )
        if previous_offset is not None and point["offset"] <= previous_offset:
            raise ValueError("Gradient points must use strictly increasing offsets")
        previous_offset = float(point["offset"])
        _validate_light_color(point["color"], f"points[{index}].color")


def _validate_particle_process_material_curve_name(value: str) -> None:
    allowed = {
        "angle",
        "angular_velocity",
        "orbit_velocity",
        "radial_velocity",
        "velocity_limit",
        "linear_accel",
        "radial_accel",
        "tangential_accel",
        "damping",
        "scale",
        "scale_over_velocity",
        "alpha",
        "emission",
        "hue_variation",
        "anim_speed",
        "anim_offset",
        "turbulence_influence_over_life",
    }
    if not isinstance(value, str) or value.strip().lower() not in allowed:
        raise ValueError(f"curve must be one of: {', '.join(sorted(allowed))}")


def _validate_particle_process_material_gradient_name(value: str) -> None:
    if not isinstance(value, str) or value.strip().lower() not in {"color", "initial_color"}:
        raise ValueError("gradient must be one of: color, initial_color")


def _validate_particle_process_material_curve_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "width",
        "texture_mode",
        "min_domain",
        "max_domain",
        "min_value",
        "max_value",
        "bake_resolution",
        "points",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > len(allowed):
        raise ValueError("properties can contain at most 8 CurveTexture entries")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported CurveTexture field")
    curve_properties = {
        name: value
        for name, value in properties.items()
        if name
        in {
            "min_domain",
            "max_domain",
            "min_value",
            "max_value",
            "bake_resolution",
            "points",
        }
    }
    if curve_properties:
        _validate_cpu_particles_curve_properties(curve_properties)
    if "width" in properties and (
        isinstance(properties["width"], bool)
        or not isinstance(properties["width"], int)
        or not 32 <= properties["width"] <= 4096
    ):
        raise ValueError("width must be an integer between 32 and 4096")
    if "texture_mode" in properties and (
        not isinstance(properties["texture_mode"], str)
        or properties["texture_mode"].strip().lower() not in {"rgb", "red"}
    ):
        raise ValueError("texture_mode must be rgb or red")


def _validate_particle_process_material_gradient_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "width",
        "use_hdr",
        "points",
        "interpolation_mode",
        "interpolation_color_space",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > len(allowed):
        raise ValueError("properties can contain at most 5 GradientTexture1D entries")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported GradientTexture1D field")
    gradient_properties = {
        name: value
        for name, value in properties.items()
        if name in {"points", "interpolation_mode", "interpolation_color_space"}
    }
    if gradient_properties:
        _validate_cpu_particles_gradient_properties(gradient_properties)
    if "width" in properties and (
        isinstance(properties["width"], bool)
        or not isinstance(properties["width"], int)
        or not 1 <= properties["width"] <= 16384
    ):
        raise ValueError("width must be an integer between 1 and 16384")
    if "use_hdr" in properties:
        _validate_boolean(properties["use_hdr"], "use_hdr")


def _validate_canvas_item_material_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "blend_mode",
        "light_mode",
        "particles_animation",
        "particles_anim_h_frames",
        "particles_anim_v_frames",
        "particles_anim_loop",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > len(allowed):
        raise ValueError("properties can contain at most 6 CanvasItemMaterial entries")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported CanvasItemMaterial property")
    for name, values in {
        "blend_mode": {"mix", "add", "subtract", "multiply", "premultiplied_alpha"},
        "light_mode": {"normal", "unshaded", "light_only"},
    }.items():
        if name in properties and (
            not isinstance(properties[name], str) or properties[name].strip().lower() not in values
        ):
            raise ValueError(f"{name} must be one of: {', '.join(sorted(values))}")
    for name in ("particles_animation", "particles_anim_loop"):
        if name in properties:
            _validate_boolean(properties[name], name)
    for name in ("particles_anim_h_frames", "particles_anim_v_frames"):
        if name in properties and (
            isinstance(properties[name], bool)
            or not isinstance(properties[name], int)
            or not 1 <= properties[name] <= 128
        ):
            raise ValueError(f"{name} must be an integer between 1 and 128")


def _validate_canvas_item_shader_source(source: str) -> None:
    if not isinstance(source, str) or not source.strip() or len(source) > 65_536:
        raise ValueError("source must contain between 1 and 65536 characters")


def _validate_canvas_item_shader_uniform_values(values: dict[str, Any]) -> None:
    if not isinstance(values, dict) or not values or len(values) > 32:
        raise ValueError("values must contain between 1 and 32 shader uniforms")
    for name, value in values.items():
        _validate_canvas_item_shader_uniform_name(name)
        if value is None or not _is_json_bind_value(value):
            raise ValueError("uniform values must be non-null bounded JSON-compatible values")


def _validate_canvas_item_shader_uniform_names(names: list[str]) -> None:
    if not isinstance(names, list) or not names or len(names) > 32:
        raise ValueError("names must contain between 1 and 32 shader uniforms")
    for name in names:
        _validate_canvas_item_shader_uniform_name(name)
    if len(set(names)) != len(names):
        raise ValueError("names cannot contain duplicate shader uniforms")


def _validate_canvas_item_shader_uniform_name(name: str) -> None:
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 128
        or not name.isascii()
        or not (name[0].isalpha() or name[0] == "_")
        or not all(character.isalnum() or character == "_" for character in name)
    ):
        raise ValueError("shader uniform names must be ASCII identifiers up to 128 characters")


def _validate_particle_process_material_2d_properties(properties: dict[str, Any]) -> None:
    allowed = {
        "lifetime_randomness",
        "align_y_to_velocity",
        "disable_z",
        "damping_as_friction",
        "inherit_emitter_scale",
        "emission_shape",
        "emission_shape_offset",
        "emission_shape_scale",
        "emission_sphere_radius",
        "emission_box_extents",
        "emission_point_count",
        "emission_ring_height",
        "emission_ring_radius",
        "emission_ring_inner_radius",
        "emission_ring_cone_angle",
        "direction",
        "spread",
        "flatness",
        "inherit_velocity_ratio",
        "velocity_pivot",
        "initial_velocity_min",
        "initial_velocity_max",
        "angular_velocity_min",
        "angular_velocity_max",
        "orbit_velocity_min",
        "orbit_velocity_max",
        "radial_velocity_min",
        "radial_velocity_max",
        "directional_velocity_min",
        "directional_velocity_max",
        "gravity",
        "linear_accel_min",
        "linear_accel_max",
        "radial_accel_min",
        "radial_accel_max",
        "tangential_accel_min",
        "tangential_accel_max",
        "damping_min",
        "damping_max",
        "attractor_interaction_enabled",
        "scale_min",
        "scale_max",
        "color",
        "turbulence_enabled",
        "turbulence_noise_strength",
        "turbulence_noise_scale",
        "turbulence_noise_speed",
        "turbulence_noise_speed_random",
        "collision_mode",
        "collision_friction",
        "collision_bounce",
        "collision_use_scale",
        "sub_emitter_mode",
        "sub_emitter_frequency",
        "sub_emitter_amount_at_end",
        "sub_emitter_amount_at_collision",
        "sub_emitter_amount_at_start",
        "sub_emitter_keep_velocity",
    }
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > 64:
        raise ValueError("properties can contain at most 64 ParticleProcessMaterial entries")
    if set(properties) - allowed:
        raise ValueError("properties contains an unsupported ParticleProcessMaterial property")
    for name in (
        "align_y_to_velocity",
        "disable_z",
        "damping_as_friction",
        "inherit_emitter_scale",
        "attractor_interaction_enabled",
        "turbulence_enabled",
        "collision_use_scale",
        "sub_emitter_keep_velocity",
    ):
        if name in properties:
            _validate_boolean(properties[name], name)
    for name in (
        "emission_shape_offset",
        "emission_shape_scale",
        "emission_box_extents",
        "direction",
        "velocity_pivot",
        "gravity",
        "turbulence_noise_speed",
    ):
        if name in properties:
            _validate_viewport_vector2(properties[name], name)
    if "emission_box_extents" in properties and (
        properties["emission_box_extents"]["x"] < 0 or properties["emission_box_extents"]["y"] < 0
    ):
        raise ValueError("emission_box_extents must have non-negative x and y")
    if "color" in properties:
        _validate_light_color(properties["color"], "color")
    for name, values in {
        "emission_shape": {
            "point",
            "sphere",
            "sphere_surface",
            "box",
            "points",
            "directed_points",
            "ring",
        },
        "collision_mode": {"disabled", "rigid", "hide_on_contact"},
        "sub_emitter_mode": {"disabled", "constant", "at_end", "at_collision", "at_start"},
    }.items():
        if name in properties and (
            not isinstance(properties[name], str) or properties[name].strip().lower() not in values
        ):
            raise ValueError(f"{name} must be one of: {', '.join(sorted(values))}")
    for name, minimum, maximum in (
        ("emission_point_count", 0, 1_000_000),
        ("sub_emitter_amount_at_end", 1, 32),
        ("sub_emitter_amount_at_collision", 1, 32),
        ("sub_emitter_amount_at_start", 1, 32),
    ):
        if name in properties and (
            isinstance(properties[name], bool)
            or not isinstance(properties[name], int)
            or not minimum <= properties[name] <= maximum
        ):
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    for name, minimum, maximum in (
        ("lifetime_randomness", 0.0, 1.0),
        ("emission_sphere_radius", 0.01, 1_000_000.0),
        ("emission_ring_height", 0.0, 1_000_000.0),
        ("emission_ring_radius", 0.0, 1_000_000.0),
        ("emission_ring_inner_radius", 0.0, 1_000_000.0),
        ("emission_ring_cone_angle", 0.0, 90.0),
        ("spread", 0.0, 180.0),
        ("flatness", 0.0, 1.0),
        ("inherit_velocity_ratio", -1000.0, 1000.0),
        ("turbulence_noise_strength", 0.0, 20.0),
        ("turbulence_noise_scale", 0.0, 1_000_000.0),
        ("turbulence_noise_speed_random", 0.0, 4.0),
        ("collision_friction", 0.0, 1.0),
        ("collision_bounce", 0.0, 1.0),
        ("sub_emitter_frequency", 0.01, 100.0),
    ):
        if name in properties:
            _validate_viewport_number(properties[name], name, minimum=minimum, maximum=maximum)
    parameter_prefixes = {
        "initial_velocity",
        "angular_velocity",
        "orbit_velocity",
        "radial_velocity",
        "directional_velocity",
        "linear_accel",
        "radial_accel",
        "tangential_accel",
        "damping",
        "scale",
    }
    for name, value in properties.items():
        if any(name in {f"{prefix}_min", f"{prefix}_max"} for prefix in parameter_prefixes):
            _validate_viewport_number(value, name, minimum=-1_000_000.0, maximum=1_000_000.0)
    for name in ("damping_min", "damping_max", "scale_min", "scale_max"):
        if name in properties and properties[name] < 0:
            raise ValueError(f"{name} must be greater than or equal to zero")
    if (
        "emission_ring_inner_radius" in properties
        and "emission_ring_radius" in properties
        and properties["emission_ring_inner_radius"] > properties["emission_ring_radius"]
    ):
        raise ValueError("emission_ring_inner_radius cannot exceed emission_ring_radius")


def _validate_viewport_vector2(value: Any, label: str) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"x", "y"}
        or not _is_finite_number(value["x"])
        or not _is_finite_number(value["y"])
    ):
        raise ValueError(f"{label} must contain finite x and y values")


def _validate_viewport_transform2d(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"x", "y", "origin"}:
        raise ValueError("transform must contain x, y, and origin Vector2 values")
    for name in ("x", "y", "origin"):
        _validate_viewport_vector2(value[name], f"transform.{name}")
    determinant = float(value["x"]["x"]) * float(value["y"]["y"]) - float(value["x"]["y"]) * float(
        value["y"]["x"]
    )
    if math.isclose(determinant, 0.0, abs_tol=1e-12):
        raise ValueError("transform must have a non-zero determinant")


def _validate_viewport_number(
    value: Any,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
    *,
    exclusive_minimum: bool = False,
) -> None:
    if not _is_finite_number(value):
        raise ValueError(f"{label} must be a finite number")
    numeric_value = float(value)
    if minimum is not None and (
        numeric_value <= minimum if exclusive_minimum else numeric_value < minimum
    ):
        comparison = "greater than" if exclusive_minimum else "greater than or equal to"
        raise ValueError(f"{label} must be {comparison} {minimum:g}")
    if maximum is not None and numeric_value > maximum:
        raise ValueError(f"{label} must be less than or equal to {maximum:g}")


def _validate_light_color(value: Any, label: str) -> None:
    if isinstance(value, str):
        return
    if (
        isinstance(value, dict)
        and set(value) in ({"r", "g", "b"}, {"r", "g", "b", "a"})
        and all(_is_finite_number(channel) for channel in value.values())
    ):
        return
    raise ValueError(f"{label} must be a color string or r/g/b/a object")


def _validate_light_vector2(value: Any, label: str) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"x", "y"}
        or not _is_finite_number(value["x"])
        or not _is_finite_number(value["y"])
    ):
        raise ValueError(f"{label} must contain finite x and y values")


def _validate_light_occluder_polygon(polygon: dict[str, Any]) -> None:
    if not isinstance(polygon, dict):
        raise ValueError("polygon must be an object")
    _validate_tile_occlusion_polygons([polygon])


def _validate_navigation_polygon_agent_radius(value: float) -> None:
    if not _is_finite_number(value) or float(value) < 0.0:
        raise ValueError("agent_radius must be a finite number greater than or equal to zero")


def _validate_navigation_polygon_vertices(
    points: list[dict[str, float | int]], label: str, *, allow_empty: bool = False
) -> None:
    if not isinstance(points, list) or len(points) > 512:
        raise ValueError(f"{label} must contain at most 512 Vector2 points")
    if len(points) < 3 and (not allow_empty or points):
        raise ValueError(f"{label} must contain at least three Vector2 points")
    if any(
        not isinstance(point, dict)
        or set(point) != {"x", "y"}
        or not _is_finite_number(point["x"])
        or not _is_finite_number(point["y"])
        for point in points
    ):
        raise ValueError(f"{label} must contain Vector2 objects with finite x and y values")


def _validate_navigation_polygon_indices(polygons: list[list[int]]) -> None:
    if not isinstance(polygons, list) or len(polygons) > 512:
        raise ValueError("polygons must contain at most 512 index arrays")
    if any(
        not isinstance(polygon, list) or len(polygon) < 3 or len(polygon) > 512
        for polygon in polygons
    ):
        raise ValueError("each polygon must contain between three and 512 vertex indices")
    if sum(len(polygon) for polygon in polygons) > 2048:
        raise ValueError("polygon indices exceed the supported limit")
    if any(
        isinstance(index, bool) or not isinstance(index, int) or index < 0
        for polygon in polygons
        for index in polygon
    ):
        raise ValueError("polygon indices must be non-negative integers")


def _validate_tile_set_layer_index(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 64:
        raise ValueError(f"{label} must be an integer between 0 and 63")


def _validate_tile_geometry_points(points: list[dict[str, float | int]], label: str) -> None:
    if not isinstance(points, list) or not 3 <= len(points) <= 512:
        raise ValueError(f"{label} must contain between three and 512 Vector2 points")
    if any(
        not isinstance(point, dict)
        or set(point) != {"x", "y"}
        or not _is_finite_number(point["x"])
        or not _is_finite_number(point["y"])
        for point in points
    ):
        raise ValueError(f"{label} must contain Vector2 objects with finite x and y values")
    point_keys = {(float(point["x"]), float(point["y"])) for point in points}
    if len(point_keys) != len(points):
        raise ValueError(f"{label} points must be unique")


def _validate_tile_collision_polygons(polygons: list[dict[str, Any]]) -> None:
    if not isinstance(polygons, list) or len(polygons) > 128:
        raise ValueError("polygons must contain at most 128 polygons")
    total_points = sum(
        len(polygon["points"])
        for polygon in polygons
        if isinstance(polygon, dict) and isinstance(polygon.get("points"), list)
    )
    if total_points > 2048:
        raise ValueError("collision polygon points exceed the supported limit")
    for index, polygon in enumerate(polygons):
        if (
            not isinstance(polygon, dict)
            or "points" not in polygon
            or set(polygon)
            - {
                "points",
                "one_way",
                "one_way_margin",
            }
        ):
            raise ValueError("each collision polygon must contain points and supported options")
        _validate_tile_geometry_points(polygon["points"], f"polygons[{index}].points")
        if "one_way" in polygon and not isinstance(polygon["one_way"], bool):
            raise ValueError("polygons[].one_way must be a boolean")
        if "one_way_margin" in polygon:
            _validate_nonnegative_finite_number(
                polygon["one_way_margin"], "polygons[].one_way_margin"
            )


def _validate_tile_occlusion_polygons(polygons: list[dict[str, Any]]) -> None:
    if not isinstance(polygons, list) or len(polygons) > 128:
        raise ValueError("polygons must contain at most 128 polygons")
    total_points = sum(
        len(polygon["points"])
        for polygon in polygons
        if isinstance(polygon, dict) and isinstance(polygon.get("points"), list)
    )
    if total_points > 2048:
        raise ValueError("occlusion polygon points exceed the supported limit")
    supported_cull_modes = {"disabled", "clockwise", "counter_clockwise"}
    for index, polygon in enumerate(polygons):
        if (
            not isinstance(polygon, dict)
            or "points" not in polygon
            or set(polygon)
            - {
                "points",
                "closed",
                "cull_mode",
            }
        ):
            raise ValueError("each occlusion polygon must contain points and supported options")
        closed = polygon.get("closed", True)
        if not isinstance(closed, bool):
            raise ValueError("polygons[].closed must be a boolean")
        _validate_tile_occlusion_points(polygon["points"], f"polygons[{index}].points", closed)
        if "cull_mode" in polygon and (
            not isinstance(polygon["cull_mode"], str)
            or polygon["cull_mode"].strip().lower() not in supported_cull_modes
        ):
            raise ValueError(
                "polygons[].cull_mode must be disabled, clockwise, or counter_clockwise"
            )


def _validate_tile_occlusion_points(
    points: list[dict[str, float | int]], label: str, closed: bool
) -> None:
    minimum = 3 if closed else 2
    minimum_word = "three" if closed else "two"
    if not isinstance(points, list) or not minimum <= len(points) <= 512:
        raise ValueError(f"{label} must contain between {minimum_word} and 512 Vector2 points")
    if any(
        not isinstance(point, dict)
        or set(point) != {"x", "y"}
        or not _is_finite_number(point["x"])
        or not _is_finite_number(point["y"])
        for point in points
    ):
        raise ValueError(f"{label} must contain Vector2 objects with finite x and y values")
    point_keys = {(float(point["x"]), float(point["y"])) for point in points}
    if len(point_keys) != len(points):
        raise ValueError(f"{label} points must be unique")


def _validate_tile_navigation_geometry(
    vertices: list[dict[str, float | int]], polygons: list[list[int]]
) -> None:
    _validate_tile_geometry_points(vertices, "vertices")
    if not isinstance(polygons, list) or not 1 <= len(polygons) <= 512:
        raise ValueError("polygons must contain between one and 512 index arrays")
    if sum(len(polygon) for polygon in polygons if isinstance(polygon, list)) > 2048:
        raise ValueError("polygon indices exceed the supported limit")
    for polygon in polygons:
        if not isinstance(polygon, list) or not 3 <= len(polygon) <= 512:
            raise ValueError("each polygon must contain between three and 512 vertex indices")
        if any(
            isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(vertices)
            for index in polygon
        ):
            raise ValueError("polygon indices must identify vertices")
        if len(set(polygon)) != len(polygon):
            raise ValueError("polygon indices must not repeat a vertex")


def _validate_navigation_outline_index(value: int | None, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("index must be a non-negative integer")


def _validate_tilemap_page(offset: int, limit: int) -> None:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 512:
        raise ValueError("limit must be an integer from 1 to 512")


def _validate_tilemap_vector2i(
    value: dict[str, int],
    label: str,
    *,
    nonnegative: bool = False,
    positive: bool = False,
) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"x", "y"}
        or any(
            isinstance(component, bool) or not isinstance(component, int)
            for component in value.values()
        )
    ):
        raise ValueError(f"{label} must be a Vector2i object with integral x and y values")
    maximum = 32767
    minimum = 0 if nonnegative else -1_000_000
    if any(component < minimum or component > maximum for component in value.values()):
        raise ValueError(f"{label} values must be between {minimum} and {maximum}")
    if positive and (value["x"] < 1 or value["y"] < 1):
        raise ValueError(f"{label}.x and {label}.y must be greater than zero")


def _validate_tilemap_source_id(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 32767:
        raise ValueError("source_id must be an integer between 0 and 32767")


def _validate_optional_tilemap_source_id(value: int | None) -> None:
    if value is not None:
        _validate_tilemap_source_id(value)


def _validate_tilemap_cells(cells: list[dict[str, Any]]) -> None:
    if not isinstance(cells, list) or not 1 <= len(cells) <= 512:
        raise ValueError("cells must contain between one and 512 entries")
    seen: set[tuple[int, int]] = set()
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {
            "coords",
            "source_id",
            "atlas_coords",
            "alternative_tile",
        }:
            raise ValueError(
                "each cell must contain exactly coords, source_id, atlas_coords, "
                "and alternative_tile"
            )
        _validate_tilemap_vector2i(cell["coords"], "cells[].coords")
        _validate_tilemap_source_id(cell["source_id"])
        _validate_tilemap_vector2i(cell["atlas_coords"], "cells[].atlas_coords", nonnegative=True)
        alternative_tile = cell["alternative_tile"]
        if (
            isinstance(alternative_tile, bool)
            or not isinstance(alternative_tile, int)
            or not 0 <= alternative_tile <= 32767
        ):
            raise ValueError("cells[].alternative_tile must be an integer between 0 and 32767")
        coord_key = (cell["coords"]["x"], cell["coords"]["y"])
        if coord_key in seen:
            raise ValueError("cells must not contain duplicate coords")
        seen.add(coord_key)


def _validate_tilemap_coordinates(coords: list[dict[str, int]]) -> None:
    if not isinstance(coords, list) or not 1 <= len(coords) <= 512:
        raise ValueError("coords must contain between one and 512 Vector2i objects")
    seen: set[tuple[int, int]] = set()
    for value in coords:
        _validate_tilemap_vector2i(value, "coords[]")
        coord_key = (value["x"], value["y"])
        if coord_key in seen:
            raise ValueError("coords must not contain duplicates")
        seen.add(coord_key)


def _validate_nonnegative_finite_number(value: float, label: str) -> None:
    if not _is_finite_number(value) or float(value) < 0.0:
        raise ValueError(f"{label} must be a finite number greater than or equal to zero")


def _validate_tile_set_identifier(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 128
        or "/" in value
        or ":" in value
    ):
        raise ValueError(
            f"{label} must be a non-empty TileSet identifier with at most 128 characters"
        )


def _validate_optional_tile_set_name(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError(f"{label} must be a string with at most 128 characters")


def _validate_tile_set_custom_data_type(value: str) -> None:
    if not isinstance(value, str) or value.strip().lower() not in {
        "bool",
        "int",
        "float",
        "string",
        "vector2",
        "vector2i",
        "color",
    }:
        raise ValueError(
            "value_type must be one of: bool, int, float, string, vector2, vector2i, color"
        )


def _validate_tile_set_terrain_mode(value: str) -> None:
    if not isinstance(value, str) or value.strip().lower() not in {
        "match_corners_and_sides",
        "match_corners",
        "match_sides",
    }:
        raise ValueError("mode must be match_corners_and_sides, match_corners, or match_sides")


def _validate_tile_set_terrain_set_index(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 64:
        raise ValueError("terrain_set must be an integer between 0 and 63")


def _validate_tile_set_terrain_index(value: int, *, allow_clear: bool, label: str) -> None:
    minimum = -1 if allow_clear else 0
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value < 64:
        raise ValueError(f"{label} must be an integer between {minimum} and 63")


def _validate_atlas_alternative_tile(value: int) -> None:
    _validate_optional_atlas_alternative_tile(value, minimum=0)


def _validate_optional_atlas_alternative_tile(value: int | None, *, minimum: int) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= 4095:
        raise ValueError(f"alternative_tile must be an integer between {minimum} and 4095")


def _validate_tile_set_peering_bits(peering_bits: dict[str, int]) -> None:
    supported_names = {
        "right_side",
        "right_corner",
        "bottom_right_side",
        "bottom_right_corner",
        "bottom_side",
        "bottom_corner",
        "bottom_left_side",
        "bottom_left_corner",
        "left_side",
        "left_corner",
        "top_left_side",
        "top_left_corner",
        "top_side",
        "top_corner",
        "top_right_side",
        "top_right_corner",
    }
    if not isinstance(peering_bits, dict) or len(peering_bits) > len(supported_names):
        raise ValueError("peering_bits must be an object with at most 16 supported directions")
    if any(
        not isinstance(name, str)
        or name not in supported_names
        or isinstance(value, bool)
        or not isinstance(value, int)
        or not -1 <= value < 64
        for name, value in peering_bits.items()
    ):
        raise ValueError(
            "peering_bits must map supported directions to terrain indices from -1 to 63"
        )


def _validate_tile_set_custom_data_values(values: dict[str, Any]) -> None:
    if not isinstance(values, dict) or not 1 <= len(values) <= 16:
        raise ValueError("values must be a non-empty object with at most 16 entries")
    for name, value in values.items():
        _validate_tile_set_identifier(name, "custom data name")
        if not _is_json_bind_value(value):
            raise ValueError("values must contain bounded JSON-compatible values")


def _validate_optional_joint_endpoint_path(value: str | None, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError(f"{label} must be a string with at most 4096 characters")


def _validate_collision_layer_numbers(values: list[int], label: str) -> None:
    if not isinstance(values, list) or len(values) > 32:
        raise ValueError(f"{label} must contain at most 32 layer numbers")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 32
        for value in values
    ):
        raise ValueError(f"{label} entries must be integers from 1 to 32")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} entries must be unique")


def _is_finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _validate_binds(binds: list[Any]) -> None:
    if not isinstance(binds, list):
        raise ValueError("binds must be an array")
    if len(binds) > 16:
        raise ValueError("binds can contain at most 16 values")
    if any(not _is_json_bind_value(value) for value in binds):
        raise ValueError("binds must contain bounded JSON-compatible values")


def _is_json_bind_value(value: Any, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if value is None or isinstance(value, (bool, str)):
        return True
    if isinstance(value, int):
        return -(2**63) <= value < 2**63
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return len(value) <= 128 and all(_is_json_bind_value(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return len(value) <= 128 and all(
            isinstance(key, str) and _is_json_bind_value(item, depth + 1)
            for key, item in value.items()
        )
    return False


def _scene_params(scene_file: str, **params: Any) -> dict[str, Any]:
    if len(scene_file) > 4096:
        raise ValueError("scene_file cannot exceed 4096 characters")
    if scene_file:
        params["scene_file"] = scene_file
    return params
