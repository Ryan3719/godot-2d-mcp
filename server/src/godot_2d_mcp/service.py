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


def _validate_node_name(name: str) -> None:
    if not name or len(name) > 256:
        raise ValueError("name must contain between 1 and 256 characters")


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


def _validate_stylebox_state(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 256 or "/" in value:
        raise ValueError("state must contain between 1 and 256 characters and cannot contain '/'")


def _validate_stylebox_properties(properties: dict[str, Any]) -> None:
    if not isinstance(properties, dict) or not properties:
        raise ValueError("properties must be a non-empty object")
    if len(properties) > 48:
        raise ValueError("properties can contain at most 48 entries")
    if any(
        not isinstance(name, str)
        or not name
        or len(name) > 256
        or not _is_json_bind_value(value)
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
        return (
            len(value) <= 128
            and all(
                isinstance(key, str) and _is_json_bind_value(item, depth + 1)
                for key, item in value.items()
            )
        )
    return False


def _scene_params(scene_file: str, **params: Any) -> dict[str, Any]:
    if len(scene_file) > 4096:
        raise ValueError("scene_file cannot exceed 4096 characters")
    if scene_file:
        params["scene_file"] = scene_file
    return params
