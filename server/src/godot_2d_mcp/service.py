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
        if name in properties and (
            properties[name]["x"] <= 0 or properties[name]["y"] <= 0
        ):
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
    determinant = float(value["x"]["x"]) * float(value["y"]["y"]) - float(
        value["x"]["y"]
    ) * float(value["y"]["x"])
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
        if not isinstance(polygon, dict) or "points" not in polygon or set(polygon) - {
            "points",
            "one_way",
            "one_way_margin",
        }:
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
        if not isinstance(polygon, dict) or "points" not in polygon or set(polygon) - {
            "points",
            "closed",
            "cull_mode",
        }:
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
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(vertices)
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
        raise ValueError(
            "mode must be match_corners_and_sides, match_corners, or match_sides"
        )


def _validate_tile_set_terrain_set_index(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 64:
        raise ValueError("terrain_set must be an integer between 0 and 63")


def _validate_tile_set_terrain_index(
    value: int, *, allow_clear: bool, label: str
) -> None:
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
