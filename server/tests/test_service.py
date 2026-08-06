from __future__ import annotations

from typing import Any

import pytest

from godot_2d_mcp.service import GodotService
from godot_2d_mcp.sessions import SessionRegistry


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []

    async def call(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((command, params or {}, session_id))
        return {"command": command}


@pytest.mark.asyncio
async def test_hierarchy_params_are_forwarded() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.scene_get_hierarchy(
        session_id="project@a1b2",
        root_path="/Main/UI",
        max_depth=3,
        offset=5,
        limit=20,
    )

    assert result == {"command": "scene_get_hierarchy"}
    assert bridge.calls == [
        (
            "scene_get_hierarchy",
            {"root_path": "/Main/UI", "max_depth": 3, "offset": 5, "limit": 20},
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_hierarchy_rejects_unbounded_page() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="limit"):
        await service.scene_get_hierarchy(limit=1001)


@pytest.mark.asyncio
async def test_node_create_forwards_scene_guard_and_session() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.node_create(
        type_name="Button",
        name="ConfirmButton",
        parent_path="/Main/UI",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )

    assert result == {"command": "node_create"}
    assert bridge.calls == [
        (
            "node_create",
            {
                "type": "Button",
                "name": "ConfirmButton",
                "parent_path": "/Main/UI",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_node_set_properties_forwards_one_atomic_payload() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    properties = {"text": "Start", "position": {"x": 24, "y": 48}}

    await service.node_set_properties(
        path="/Main/UI/StartButton",
        properties=properties,
    )

    assert bridge.calls == [
        (
            "node_set_properties",
            {"path": "/Main/UI/StartButton", "properties": properties},
            None,
        )
    ]


@pytest.mark.asyncio
async def test_node_set_properties_rejects_empty_or_unbounded_updates() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="non-empty"):
        await service.node_set_properties("/Main", {})
    with pytest.raises(ValueError, match="at most 64"):
        await service.node_set_properties(
            "/Main",
            {f"property_{index}": index for index in range(65)},
        )


@pytest.mark.asyncio
async def test_scene_commands_forward_to_godot() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    await service.scene_undo(scene_file="res://main.tscn")
    await service.scene_redo(scene_file="res://main.tscn")
    await service.scene_save(scene_file="res://main.tscn")

    assert bridge.calls == [
        ("scene_undo", {"scene_file": "res://main.tscn"}, None),
        ("scene_redo", {"scene_file": "res://main.tscn"}, None),
        ("scene_save", {"scene_file": "res://main.tscn"}, None),
    ]


@pytest.mark.asyncio
async def test_node_structure_tools_forward_scene_guard_and_options() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    await service.node_rename(
        path="/Main/UI/StartButton",
        name="PlayButton",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.node_duplicate(
        path="/Main/UI/PlayButton",
        name="PlayButtonCopy",
        scene_file="res://main.tscn",
    )
    await service.node_reparent(
        path="/Main/UI/PlayButton",
        new_parent_path="/Main",
        index=1,
        keep_global_transform=False,
        scene_file="res://main.tscn",
    )
    await service.node_move(
        path="/Main/PlayButton",
        index=0,
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "node_rename",
            {
                "path": "/Main/UI/StartButton",
                "name": "PlayButton",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "node_duplicate",
            {
                "path": "/Main/UI/PlayButton",
                "name": "PlayButtonCopy",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "node_reparent",
            {
                "path": "/Main/UI/PlayButton",
                "new_parent_path": "/Main",
                "index": 1,
                "keep_global_transform": False,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "node_move",
            {
                "path": "/Main/PlayButton",
                "index": 0,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_node_structure_tools_validate_names_and_indexes() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="name"):
        await service.node_rename("/Main/UI/StartButton", "")
    with pytest.raises(ValueError, match="index"):
        await service.node_reparent("/Main/UI/StartButton", "/Main", index=-1)
    with pytest.raises(ValueError, match="index"):
        await service.node_move("/Main/UI/StartButton", index=-1)
    with pytest.raises(ValueError, match="keep_global_transform"):
        await service.node_reparent("/Main/UI/StartButton", "/Main", keep_global_transform=1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_signal_tools_forward_persistent_connection_options() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    await service.node_get_signals(
        path="/Main/UI/StartButton",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.signal_connect(
        source_path="/Main/UI/StartButton",
        signal="pressed",
        target_path="/Main/ButtonAnimations",
        method="play",
        binds=["button_pulse", {"speed": 1.0}],
        deferred=True,
        one_shot=True,
        scene_file="res://main.tscn",
    )
    await service.signal_disconnect(
        source_path="/Main/UI/StartButton",
        signal="pressed",
        target_path="/Main/ButtonAnimations",
        method="play",
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "node_get_signals",
            {"path": "/Main/UI/StartButton", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "signal_connect",
            {
                "source_path": "/Main/UI/StartButton",
                "signal": "pressed",
                "target_path": "/Main/ButtonAnimations",
                "method": "play",
                "binds": ["button_pulse", {"speed": 1.0}],
                "deferred": True,
                "one_shot": True,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "signal_disconnect",
            {
                "source_path": "/Main/UI/StartButton",
                "signal": "pressed",
                "target_path": "/Main/ButtonAnimations",
                "method": "play",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_signal_tools_reject_invalid_bind_values_and_options() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="binds"):
        await service.signal_connect(
            "/Main/UI/StartButton",
            "pressed",
            "/Main/ButtonAnimations",
            "play",
            binds=[object()],
        )
    with pytest.raises(ValueError, match="deferred"):
        await service.signal_connect(
            "/Main/UI/StartButton",
            "pressed",
            "/Main/ButtonAnimations",
            "play",
            deferred=1,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_animation_tools_forward_scene_guard_and_track_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    keys = [
        {"time": 0.0, "value": {"x": 1.0, "y": 1.0}},
        {"time": 0.2, "value": {"x": 1.08, "y": 1.08}, "transition": 0.5},
    ]

    await service.animation_list(
        player_path="/Main/ButtonAnimations",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.animation_get(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        library="ui",
        scene_file="res://main.tscn",
    )
    await service.animation_create(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        length=0.2,
        loop_mode="pingpong",
        scene_file="res://main.tscn",
    )
    await service.animation_track_upsert(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        target_path="/Main/UI/StartButton",
        property="scale",
        keys=keys,
        interpolation="cubic",
        loop_wrap=False,
        scene_file="res://main.tscn",
    )
    await service.animation_key_upsert(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        track_index=0,
        time=0.1,
        value={"x": 1.04, "y": 1.04},
        scene_file="res://main.tscn",
    )
    await service.animation_key_delete(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        track_index=0,
        time=0.1,
        scene_file="res://main.tscn",
    )
    await service.animation_track_delete(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        track_index=0,
        scene_file="res://main.tscn",
    )
    await service.animation_delete(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "animation_list",
            {"player_path": "/Main/ButtonAnimations", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "animation_get",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "library": "ui",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "animation_create",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "length": 0.2,
                "loop_mode": "pingpong",
                "library": "",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "animation_track_upsert",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "target_path": "/Main/UI/StartButton",
                "property": "scale",
                "keys": keys,
                "interpolation": "cubic",
                "update_mode": "continuous",
                "enabled": True,
                "loop_wrap": False,
                "library": "",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "animation_key_upsert",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "track_index": 0,
                "time": 0.1,
                "value": {"x": 1.04, "y": 1.04},
                "transition": 1.0,
                "library": "",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "animation_key_delete",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "track_index": 0,
                "time": 0.1,
                "library": "",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "animation_track_delete",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "track_index": 0,
                "library": "",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "animation_delete",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "library": "",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_animation_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="animation"):
        await service.animation_create("/Main/ButtonAnimations", "bad/name")
    with pytest.raises(ValueError, match="length"):
        await service.animation_create("/Main/ButtonAnimations", "hover", length=0)
    with pytest.raises(ValueError, match="keys"):
        await service.animation_track_upsert(
            "/Main/ButtonAnimations",
            "hover",
            "/Main/UI/StartButton",
            "scale",
            keys=[{"time": 0.0, "value": 1}, {"time": 0.0, "value": 2}],
        )
    with pytest.raises(ValueError, match="track_index"):
        await service.animation_key_delete(
            "/Main/ButtonAnimations", "hover", track_index=-1, time=0.0
        )


@pytest.mark.asyncio
async def test_control_layout_and_stylebox_tools_forward_structured_values() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    anchors = {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
    offsets = {"left": 12.0, "top": 16.0, "right": -12.0, "bottom": -16.0}
    style_properties = {
        "bg_color": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0},
        "corner_radius_top_left": 8,
    }

    await service.control_get_layout(
        "/Main/UI/StartButton",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.control_set_layout(
        "/Main/UI/StartButton",
        anchors=anchors,
        offsets=offsets,
        scene_file="res://main.tscn",
    )
    await service.control_set_layout_preset(
        "/Main/UI/StartButton",
        preset="full_rect",
        resize_mode="keep_size",
        margin=4,
        scene_file="res://main.tscn",
    )
    await service.control_get_styleboxes(
        "/Main/UI/StartButton",
        scene_file="res://main.tscn",
    )
    await service.control_stylebox_flat_upsert(
        "/Main/UI/StartButton",
        state="normal",
        properties=style_properties,
        scene_file="res://main.tscn",
    )
    await service.control_stylebox_override_clear(
        "/Main/UI/StartButton",
        state="normal",
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "control_get_layout",
            {"path": "/Main/UI/StartButton", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "control_set_layout",
            {
                "path": "/Main/UI/StartButton",
                "anchors": anchors,
                "offsets": offsets,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "control_set_layout_preset",
            {
                "path": "/Main/UI/StartButton",
                "preset": "full_rect",
                "resize_mode": "keep_size",
                "margin": 4,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "control_get_styleboxes",
            {"path": "/Main/UI/StartButton", "scene_file": "res://main.tscn"},
            None,
        ),
        (
            "control_stylebox_flat_upsert",
            {
                "path": "/Main/UI/StartButton",
                "state": "normal",
                "properties": style_properties,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "control_stylebox_override_clear",
            {
                "path": "/Main/UI/StartButton",
                "state": "normal",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_control_layout_and_stylebox_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="anchors or offsets"):
        await service.control_set_layout("/Main/UI/StartButton")
    with pytest.raises(ValueError, match="anchors"):
        await service.control_set_layout(
            "/Main/UI/StartButton",
            anchors={"left": 0.0, "top": 0.0, "right": 1.0},
        )
    with pytest.raises(ValueError, match="preset"):
        await service.control_set_layout_preset("/Main/UI/StartButton", preset="not_a_preset")
    with pytest.raises(ValueError, match="properties"):
        await service.control_stylebox_flat_upsert(
            "/Main/UI/StartButton", state="normal", properties={}
        )
    with pytest.raises(ValueError, match="state"):
        await service.control_stylebox_override_clear("/Main/UI/StartButton", state="bad/state")


@pytest.mark.asyncio
async def test_control_theme_tools_forward_embedded_theme_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    font = {"source": "system", "families": ["Noto Sans CJK SC", "sans-serif"]}
    color = {"r": 0.15, "g": 0.35, "b": 0.7, "a": 1.0}

    await service.control_theme_get(
        "/Main/UI/Root", scene_file="res://main.tscn", session_id="project@a1b2"
    )
    await service.control_theme_create(
        "/Main/UI/Root",
        resource_name="UiTheme",
        scene_file="res://main.tscn",
    )
    await service.control_theme_assign(
        "/Main/UI/Root", theme_path="res://themes/existing.tres", scene_file="res://main.tscn"
    )
    await service.control_theme_defaults_set(
        "/Main/UI/Root",
        font=font,
        font_size=18,
        base_scale=1.25,
        scene_file="res://main.tscn",
    )
    await service.control_theme_defaults_clear(
        "/Main/UI/Root", ["font", "base_scale"], scene_file="res://main.tscn"
    )
    await service.control_theme_item_upsert(
        "/Main/UI/Root",
        item_type="color",
        theme_type="Button",
        name="font_color",
        value=color,
        scene_file="res://main.tscn",
    )
    await service.control_theme_item_clear(
        "/Main/UI/Root",
        item_type="color",
        theme_type="Button",
        name="font_color",
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "control_theme_get",
            {"path": "/Main/UI/Root", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "control_theme_create",
            {
                "path": "/Main/UI/Root",
                "resource_name": "UiTheme",
                "replace": False,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "control_theme_assign",
            {
                "path": "/Main/UI/Root",
                "theme_path": "res://themes/existing.tres",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "control_theme_defaults_set",
            {
                "path": "/Main/UI/Root",
                "font": font,
                "font_size": 18,
                "base_scale": 1.25,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "control_theme_defaults_clear",
            {
                "path": "/Main/UI/Root",
                "defaults": ["font", "base_scale"],
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "control_theme_item_upsert",
            {
                "path": "/Main/UI/Root",
                "item_type": "color",
                "theme_type": "Button",
                "name": "font_color",
                "value": color,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "control_theme_item_clear",
            {
                "path": "/Main/UI/Root",
                "item_type": "color",
                "theme_type": "Button",
                "name": "font_color",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_control_theme_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="font, font_size, or base_scale"):
        await service.control_theme_defaults_set("/Main/UI/Root")
    with pytest.raises(ValueError, match="res://"):
        await service.control_theme_assign("/Main/UI/Root", theme_path="/tmp/theme.tres")
    with pytest.raises(ValueError, match="font.source"):
        await service.control_theme_defaults_set(
            "/Main/UI/Root", font={"source": "unknown", "families": ["sans-serif"]}
        )
    with pytest.raises(ValueError, match="item_type"):
        await service.control_theme_item_upsert(
            "/Main/UI/Root", "shader", "Button", "font_color", {"r": 1, "g": 1, "b": 1}
        )
    with pytest.raises(ValueError, match="Theme identifier"):
        await service.control_theme_item_clear(
            "/Main/UI/Root", "color", "Button", "bad/name"
        )


@pytest.mark.asyncio
async def test_collision_shape_and_layer_tools_forward_safe_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    rectangle = {"size": {"x": 96.0, "y": 32.0}}

    await service.collision_shape_get(
        "/Main/Wall/Collider", scene_file="res://main.tscn", session_id="project@a1b2"
    )
    await service.collision_object_get_layers(
        "/Main/Wall", scene_file="res://main.tscn"
    )
    await service.collision_shape_set(
        "/Main/Wall/Collider",
        shape_type="rectangle",
        properties=rectangle,
        scene_file="res://main.tscn",
    )
    await service.collision_shape_clear("/Main/Wall/Collider", scene_file="res://main.tscn")
    await service.collision_object_set_layers(
        "/Main/Wall",
        layers=[2, 5],
        masks=[1, 3],
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "collision_shape_get",
            {"path": "/Main/Wall/Collider", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "collision_object_get_layers",
            {"path": "/Main/Wall", "scene_file": "res://main.tscn"},
            None,
        ),
        (
            "collision_shape_set",
            {
                "path": "/Main/Wall/Collider",
                "shape_type": "rectangle",
                "properties": rectangle,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "collision_shape_clear",
            {"path": "/Main/Wall/Collider", "scene_file": "res://main.tscn"},
            None,
        ),
        (
            "collision_object_set_layers",
            {
                "path": "/Main/Wall",
                "layers": [2, 5],
                "masks": [1, 3],
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_collision_shape_and_layer_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="shape_type"):
        await service.collision_shape_set("/Main/Collider", "box", {"size": {"x": 1, "y": 1}})
    with pytest.raises(ValueError, match="properties must include"):
        await service.collision_shape_set("/Main/Collider", "capsule", {"radius": 4})
    with pytest.raises(ValueError, match="layers or masks"):
        await service.collision_object_set_layers("/Main/Wall")
    with pytest.raises(ValueError, match="unique"):
        await service.collision_object_set_layers("/Main/Wall", layers=[1, 1])
    with pytest.raises(ValueError, match="1 to 32"):
        await service.collision_object_set_layers("/Main/Wall", masks=[33])


@pytest.mark.asyncio
async def test_physics_behavior_tools_forward_semantic_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    area_properties = {
        "monitoring": False,
        "gravity_space_override": "replace",
        "gravity_direction": {"x": 0, "y": 1},
        "gravity": 420.0,
    }
    body_properties = {
        "motion_mode": "grounded",
        "up_direction": {"x": 0, "y": -1},
        "platform_floor_layers": [1, 3],
    }
    joint_properties = {"softness": 0.5, "angular_limit_enabled": True}

    await service.area_2d_get("/Main/GravityZone", scene_file="res://main.tscn")
    await service.physics_body_2d_get("/Main/Player", scene_file="res://main.tscn")
    await service.joint_2d_get("/Main/PlayerJoint", scene_file="res://main.tscn")
    await service.area_2d_set(
        "/Main/GravityZone",
        area_properties,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.physics_body_2d_set(
        "/Main/Player", body_properties, scene_file="res://main.tscn"
    )
    await service.joint_2d_set(
        "/Main/PlayerJoint",
        properties=joint_properties,
        node_a_path="/Main/Player",
        node_b_path="/Main/Wall",
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        ("area_2d_get", {"path": "/Main/GravityZone", "scene_file": "res://main.tscn"}, None),
        ("physics_body_2d_get", {"path": "/Main/Player", "scene_file": "res://main.tscn"}, None),
        ("joint_2d_get", {"path": "/Main/PlayerJoint", "scene_file": "res://main.tscn"}, None),
        (
            "area_2d_set",
            {
                "path": "/Main/GravityZone",
                "properties": area_properties,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "physics_body_2d_set",
            {
                "path": "/Main/Player",
                "properties": body_properties,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "joint_2d_set",
            {
                "path": "/Main/PlayerJoint",
                "properties": joint_properties,
                "node_a_path": "/Main/Player",
                "node_b_path": "/Main/Wall",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_physics_behavior_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="non-empty"):
        await service.area_2d_set("/Main/GravityZone", {})
    with pytest.raises(ValueError, match="at most 32"):
        await service.physics_body_2d_set(
            "/Main/Player", {f"property_{index}": index for index in range(33)}
        )
    with pytest.raises(ValueError, match="properties, node_a_path, or node_b_path"):
        await service.joint_2d_set("/Main/PlayerJoint")
    with pytest.raises(ValueError, match="JSON-compatible"):
        await service.joint_2d_set("/Main/PlayerJoint", properties={"bias": float("inf")})
    with pytest.raises(ValueError, match="node_a_path"):
        await service.joint_2d_set("/Main/PlayerJoint", node_a_path="x" * 4097)


@pytest.mark.asyncio
async def test_cast_tools_forward_configuration_masks_and_shapes() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    ray_properties = {"target_position": {"x": 96, "y": 0}, "collide_with_areas": True}
    shape_properties = {"margin": 2.0, "max_results": 8}
    circle = {"radius": 12.0}

    await service.ray_cast_2d_get("/Main/GroundRay", scene_file="res://main.tscn")
    await service.shape_cast_2d_get("/Main/PlayerShapeCast", scene_file="res://main.tscn")
    await service.ray_cast_2d_set(
        "/Main/GroundRay",
        properties=ray_properties,
        masks=[1, 4],
        scene_file="res://main.tscn",
    )
    await service.shape_cast_2d_set(
        "/Main/PlayerShapeCast",
        properties=shape_properties,
        masks=[2],
        shape_type="circle",
        shape_properties=circle,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.shape_cast_2d_shape_clear("/Main/PlayerShapeCast", scene_file="res://main.tscn")

    assert bridge.calls == [
        ("ray_cast_2d_get", {"path": "/Main/GroundRay", "scene_file": "res://main.tscn"}, None),
        (
            "shape_cast_2d_get",
            {"path": "/Main/PlayerShapeCast", "scene_file": "res://main.tscn"},
            None,
        ),
        (
            "ray_cast_2d_set",
            {
                "path": "/Main/GroundRay",
                "properties": ray_properties,
                "masks": [1, 4],
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "shape_cast_2d_set",
            {
                "path": "/Main/PlayerShapeCast",
                "properties": shape_properties,
                "masks": [2],
                "shape_type": "circle",
                "shape_properties": circle,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "shape_cast_2d_shape_clear",
            {"path": "/Main/PlayerShapeCast", "scene_file": "res://main.tscn"},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_cast_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="properties or masks"):
        await service.ray_cast_2d_set("/Main/GroundRay")
    with pytest.raises(ValueError, match="unique"):
        await service.ray_cast_2d_set("/Main/GroundRay", masks=[2, 2])
    with pytest.raises(ValueError, match="properties, masks, or shape_type"):
        await service.shape_cast_2d_set("/Main/PlayerShapeCast")
    with pytest.raises(ValueError, match="shape_type"):
        await service.shape_cast_2d_set(
            "/Main/PlayerShapeCast", shape_properties={"radius": 12.0}
        )
    with pytest.raises(ValueError, match="shape_properties"):
        await service.shape_cast_2d_set("/Main/PlayerShapeCast", shape_type="circle")


@pytest.mark.asyncio
async def test_navigation_tools_forward_semantic_configuration() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    region_properties = {"navigation_layers": [1, 3], "travel_cost": 1.5}

    await service.navigation_2d_get(
        "/Main/NavigationRegion", scene_file="res://main.tscn", session_id="project@a1b2"
    )
    await service.navigation_2d_set(
        "/Main/NavigationRegion", region_properties, scene_file="res://main.tscn"
    )

    assert bridge.calls == [
        (
            "navigation_2d_get",
            {"path": "/Main/NavigationRegion", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "navigation_2d_set",
            {
                "path": "/Main/NavigationRegion",
                "properties": region_properties,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_navigation_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="non-empty"):
        await service.navigation_2d_set("/Main/NavigationRegion", {})
    with pytest.raises(ValueError, match="JSON-compatible"):
        await service.navigation_2d_set(
            "/Main/NavigationRegion", {"enter_cost": float("inf")}
        )


@pytest.mark.asyncio
async def test_navigation_polygon_tools_forward_resource_edits() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    vertices = [
        {"x": 0.0, "y": 0.0},
        {"x": 128.0, "y": 0.0},
        {"x": 128.0, "y": 64.0},
        {"x": 0.0, "y": 64.0},
    ]

    await service.navigation_polygon_get(
        "/Main/NavigationRegion", scene_file="res://main.tscn", session_id="project@a1b2"
    )
    await service.navigation_polygon_create(
        "/Main/NavigationRegion", agent_radius=12.0, scene_file="res://main.tscn"
    )
    await service.navigation_polygon_geometry_set(
        "/Main/NavigationRegion",
        vertices,
        [[0, 1, 2, 3]],
        agent_radius=8.0,
        scene_file="res://main.tscn",
    )
    await service.navigation_polygon_outline_set(
        "/Main/NavigationRegion", vertices, scene_file="res://main.tscn"
    )
    await service.navigation_polygon_outline_remove(
        "/Main/NavigationRegion", 0, scene_file="res://main.tscn"
    )
    await service.navigation_polygon_make_from_outlines(
        "/Main/NavigationRegion", scene_file="res://main.tscn"
    )
    await service.navigation_polygon_clear("/Main/NavigationRegion", scene_file="res://main.tscn")

    assert bridge.calls == [
        (
            "navigation_polygon_get",
            {"path": "/Main/NavigationRegion", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "navigation_polygon_create",
            {
                "path": "/Main/NavigationRegion",
                "agent_radius": 12.0,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "navigation_polygon_geometry_set",
            {
                "path": "/Main/NavigationRegion",
                "vertices": vertices,
                "polygons": [[0, 1, 2, 3]],
                "agent_radius": 8.0,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "navigation_polygon_outline_set",
            {
                "path": "/Main/NavigationRegion",
                "outline": vertices,
                "index": None,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "navigation_polygon_outline_remove",
            {"path": "/Main/NavigationRegion", "index": 0, "scene_file": "res://main.tscn"},
            None,
        ),
        (
            "navigation_polygon_make_from_outlines",
            {"path": "/Main/NavigationRegion", "scene_file": "res://main.tscn"},
            None,
        ),
        (
            "navigation_polygon_clear",
            {"path": "/Main/NavigationRegion", "scene_file": "res://main.tscn"},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_navigation_polygon_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="agent_radius"):
        await service.navigation_polygon_create("/Main/NavigationRegion", agent_radius=-1.0)
    with pytest.raises(ValueError, match="vertices"):
        await service.navigation_polygon_geometry_set(
            "/Main/NavigationRegion", [{"x": 1.0}], [[0, 1, 2]]
        )
    with pytest.raises(ValueError, match="vertices and polygons"):
        await service.navigation_polygon_geometry_set(
            "/Main/NavigationRegion", [], [[0, 1, 2]]
        )
    with pytest.raises(ValueError, match="outline"):
        await service.navigation_polygon_outline_set(
            "/Main/NavigationRegion", [{"x": 0.0, "y": 0.0}]
        )
    with pytest.raises(ValueError, match="index"):
        await service.navigation_polygon_outline_remove("/Main/NavigationRegion", True)


@pytest.mark.asyncio
async def test_viewport_tools_forward_atomic_semantic_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    scene_file = "res://main.tscn"
    camera_path = "/Main/Camera"
    parallax_path = "/Main/Background"
    canvas_layer_path = "/Main/HUD"
    camera_properties = {
        "anchor_mode": "drag_center",
        "drag_left_margin": 0.1,
        "limit_left": -960,
        "limit_right": 960,
        "position_smoothing_enabled": True,
        "position_smoothing_speed": 8.0,
        "process_callback": "physics",
        "zoom": {"x": 1.5, "y": 1.5},
    }
    parallax_properties = {
        "autoscroll": {"x": 12.0, "y": 0.0},
        "limit_begin": {"x": -1024.0, "y": -512.0},
        "limit_end": {"x": 1024.0, "y": 512.0},
        "repeat_size": {"x": 320.0, "y": 180.0},
        "repeat_times": 3,
        "scroll_scale": {"x": 0.5, "y": 0.5},
    }
    canvas_layer_properties = {
        "follow_viewport_enabled": True,
        "follow_viewport_scale": 0.75,
        "layer": 10,
        "offset": {"x": 16.0, "y": 24.0},
        "scale": {"x": 1.0, "y": -1.0},
        "visible": True,
    }

    await service.camera_2d_get(camera_path, session_id="project@a1b2", scene_file=scene_file)
    await service.parallax_2d_get(parallax_path, scene_file=scene_file)
    await service.canvas_layer_get(canvas_layer_path, scene_file=scene_file)
    await service.camera_2d_set(camera_path, camera_properties, scene_file=scene_file)
    await service.parallax_2d_set(parallax_path, parallax_properties, scene_file=scene_file)
    await service.canvas_layer_set(
        canvas_layer_path, canvas_layer_properties, scene_file=scene_file
    )

    assert bridge.calls == [
        ("camera_2d_get", {"path": camera_path, "scene_file": scene_file}, "project@a1b2"),
        ("parallax_2d_get", {"path": parallax_path, "scene_file": scene_file}, None),
        (
            "canvas_layer_get",
            {"path": canvas_layer_path, "scene_file": scene_file},
            None,
        ),
        (
            "camera_2d_set",
            {"path": camera_path, "properties": camera_properties, "scene_file": scene_file},
            None,
        ),
        (
            "parallax_2d_set",
            {"path": parallax_path, "properties": parallax_properties, "scene_file": scene_file},
            None,
        ),
        (
            "canvas_layer_set",
            {
                "path": canvas_layer_path,
                "properties": canvas_layer_properties,
                "scene_file": scene_file,
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_viewport_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="non-empty"):
        await service.camera_2d_set("/Main/Camera", {})
    with pytest.raises(ValueError, match="unsupported viewport property"):
        await service.camera_2d_set("/Main/Camera", {"texture": "res://camera.png"})
    with pytest.raises(ValueError, match="zoom"):
        await service.camera_2d_set("/Main/Camera", {"zoom": {"x": 0.0, "y": 1.0}})
    with pytest.raises(ValueError, match="custom_viewport_path"):
        await service.camera_2d_set("/Main/Camera", {"custom_viewport_path": 3})
    with pytest.raises(ValueError, match="repeat_times"):
        await service.parallax_2d_set("/Main/Background", {"repeat_times": 0})
    with pytest.raises(ValueError, match="repeat_size"):
        await service.parallax_2d_set(
            "/Main/Background", {"repeat_size": {"x": -1.0, "y": 1.0}}
        )
    with pytest.raises(ValueError, match="transform cannot"):
        await service.canvas_layer_set(
            "/Main/HUD",
            {
                "transform": {
                    "x": {"x": 1.0, "y": 0.0},
                    "y": {"x": 0.0, "y": 1.0},
                    "origin": {"x": 0.0, "y": 0.0},
                },
                "scale": {"x": 1.0, "y": 1.0},
            },
        )


@pytest.mark.asyncio
async def test_path_2d_tools_forward_curve_edits() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/PatrolPath"
    scene_file = "res://main.tscn"
    points = [
        {
            "position": {"x": 0.0, "y": 0.0},
            "out": {"x": 32.0, "y": 0.0},
        },
        {
            "position": {"x": 128.0, "y": 64.0},
            "in": {"x": -32.0, "y": 0.0},
        },
    ]
    inserted_point = {"position": {"x": 64.0, "y": 16.0}}
    updated_point = {
        "position": {"x": 128.0, "y": 80.0},
        "in": {"x": -24.0, "y": -8.0},
        "out": {"x": 16.0, "y": 12.0},
    }

    await service.path_2d_get(
        path, offset=2, limit=20, session_id="project@a1b2", scene_file=scene_file
    )
    await service.path_2d_curve_set(path, points, bake_interval=2.5, scene_file=scene_file)
    await service.path_2d_curve_point_insert(
        path, inserted_point, index=1, scene_file=scene_file
    )
    await service.path_2d_curve_point_set(path, 2, updated_point, scene_file=scene_file)
    await service.path_2d_curve_point_remove(path, 0, scene_file=scene_file)
    await service.path_2d_curve_clear(path, scene_file=scene_file)

    assert bridge.calls == [
        (
            "path_2d_get",
            {"path": path, "offset": 2, "limit": 20, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "path_2d_curve_set",
            {
                "path": path,
                "points": points,
                "bake_interval": 2.5,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "path_2d_curve_point_insert",
            {"path": path, "point": inserted_point, "index": 1, "scene_file": scene_file},
            None,
        ),
        (
            "path_2d_curve_point_set",
            {"path": path, "index": 2, "point": updated_point, "scene_file": scene_file},
            None,
        ),
        (
            "path_2d_curve_point_remove",
            {"path": path, "index": 0, "scene_file": scene_file},
            None,
        ),
        ("path_2d_curve_clear", {"path": path, "scene_file": scene_file}, None),
    ]


@pytest.mark.asyncio
async def test_path_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="limit"):
        await service.path_2d_get("/Main/PatrolPath", limit=513)
    with pytest.raises(ValueError, match="points"):
        await service.path_2d_curve_set(
            "/Main/PatrolPath", [{"position": {"x": 0.0, "y": 0.0}}] * 513
        )
    with pytest.raises(ValueError, match="position"):
        await service.path_2d_curve_point_insert(
            "/Main/PatrolPath", {"in": {"x": 0.0, "y": 0.0}}
        )
    with pytest.raises(ValueError, match="point.out"):
        await service.path_2d_curve_point_set(
            "/Main/PatrolPath",
            0,
            {"position": {"x": 0.0, "y": 0.0}, "out": {"x": float("inf"), "y": 0.0}},
        )
    with pytest.raises(ValueError, match="bake_interval"):
        await service.path_2d_curve_set("/Main/PatrolPath", [], bake_interval=0.0)
    with pytest.raises(ValueError, match="index"):
        await service.path_2d_curve_point_remove("/Main/PatrolPath", True)


@pytest.mark.asyncio
async def test_skeleton_2d_tools_forward_semantic_edits() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    skeleton_path = "/Main/Rig"
    bone_path = "/Main/Rig/UpperArm"
    scene_file = "res://main.tscn"
    properties = {
        "rest": {
            "x": {"x": 1.0, "y": 0.0},
            "y": {"x": 0.0, "y": 1.0},
            "origin": {"x": 32.0, "y": 8.0},
        },
        "auto_calculate_length_and_angle": False,
        "length": 48.0,
        "angle_degrees": 15.0,
    }
    child_rest = {
        "x": {"x": 1.0, "y": 0.0},
        "y": {"x": 0.0, "y": 1.0},
        "origin": {"x": 48.0, "y": 0.0},
    }

    await service.skeleton_2d_get(
        skeleton_path, session_id="project@a1b2", scene_file=scene_file
    )
    await service.bone_2d_get(bone_path, scene_file=scene_file)
    await service.skeleton_2d_bone_create(
        skeleton_path,
        name="Hand",
        parent_bone_path=bone_path,
        rest=child_rest,
        length=24.0,
        angle_degrees=-20.0,
        scene_file=scene_file,
    )
    await service.bone_2d_set(bone_path, properties, scene_file=scene_file)
    await service.skeleton_2d_reset_to_rest(skeleton_path, scene_file=scene_file)
    await service.skeleton_2d_make_rest_from_current(skeleton_path, scene_file=scene_file)

    assert bridge.calls == [
        (
            "skeleton_2d_get",
            {"path": skeleton_path, "scene_file": scene_file},
            "project@a1b2",
        ),
        ("bone_2d_get", {"path": bone_path, "scene_file": scene_file}, None),
        (
            "skeleton_2d_bone_create",
            {
                "path": skeleton_path,
                "name": "Hand",
                "parent_bone_path": bone_path,
                "rest": child_rest,
                "length": 24.0,
                "angle_degrees": -20.0,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "bone_2d_set",
            {"path": bone_path, "properties": properties, "scene_file": scene_file},
            None,
        ),
        (
            "skeleton_2d_reset_to_rest",
            {"path": skeleton_path, "scene_file": scene_file},
            None,
        ),
        (
            "skeleton_2d_make_rest_from_current",
            {"path": skeleton_path, "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_skeleton_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/Rig/UpperArm"

    with pytest.raises(ValueError, match="non-empty"):
        await service.bone_2d_set(path, {})
    with pytest.raises(ValueError, match="unsupported Bone2D"):
        await service.bone_2d_set(path, {"position": {"x": 0.0, "y": 0.0}})
    with pytest.raises(ValueError, match="non-zero determinant"):
        await service.bone_2d_set(
            path,
            {
                "rest": {
                    "x": {"x": 0.0, "y": 0.0},
                    "y": {"x": 0.0, "y": 0.0},
                    "origin": {"x": 0.0, "y": 0.0},
                }
            },
        )
    with pytest.raises(ValueError, match="cannot be combined"):
        await service.bone_2d_set(
            path,
            {"auto_calculate_length_and_angle": True, "length": 24.0},
        )
    with pytest.raises(ValueError, match="angle_degrees"):
        await service.bone_2d_set(path, {"angle_degrees": 361.0})
    with pytest.raises(ValueError, match="length"):
        await service.bone_2d_set(path, {"length": 0.0})
    with pytest.raises(ValueError, match="angle_degrees"):
        await service.skeleton_2d_bone_create("/Main/Rig", angle_degrees=-361.0)


@pytest.mark.asyncio
async def test_audio_stream_player_2d_tools_forward_semantic_edits() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/AmbientSound"
    scene_file = "res://main.tscn"
    properties = {
        "stream_path": "res://audio/test.tres",
        "volume_db": -6.0,
        "pitch_scale": 1.25,
        "autoplay": True,
        "max_distance": 640.0,
        "attenuation": 1.5,
        "panning_strength": 0.75,
        "max_polyphony": 4,
        "bus": "Master",
        "area_layers": [1, 3],
        "playback_type": "stream",
    }

    await service.audio_stream_player_2d_get(
        path, session_id="project@a1b2", scene_file=scene_file
    )
    await service.audio_stream_player_2d_set(path, properties, scene_file=scene_file)

    assert bridge.calls == [
        (
            "audio_stream_player_2d_get",
            {"path": path, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "audio_stream_player_2d_set",
            {"path": path, "properties": properties, "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_audio_stream_player_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/AmbientSound"

    with pytest.raises(ValueError, match="non-empty"):
        await service.audio_stream_player_2d_set(path, {})
    with pytest.raises(ValueError, match="unsupported AudioStreamPlayer2D"):
        await service.audio_stream_player_2d_set(path, {"playing": True})
    with pytest.raises(ValueError, match="stream_path"):
        await service.audio_stream_player_2d_set(path, {"stream_path": "../sound.ogg"})
    with pytest.raises(ValueError, match="pitch_scale"):
        await service.audio_stream_player_2d_set(path, {"pitch_scale": 0.0})
    with pytest.raises(ValueError, match="max_polyphony"):
        await service.audio_stream_player_2d_set(path, {"max_polyphony": True})
    with pytest.raises(ValueError, match="area_layers"):
        await service.audio_stream_player_2d_set(path, {"area_layers": [1, 1]})
    with pytest.raises(ValueError, match="playback_type"):
        await service.audio_stream_player_2d_set(path, {"playback_type": "runtime"})
    with pytest.raises(ValueError, match="bus"):
        await service.audio_stream_player_2d_set(path, {"bus": ""})


@pytest.mark.asyncio
async def test_gpu_particles_2d_tools_forward_semantic_edits() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Fire"
    scene_file = "res://main.tscn"
    properties = {
        "emitting": True,
        "amount": 128,
        "amount_ratio": 0.75,
        "sub_emitter_path": "/Main/Sparks",
        "texture_path": "res://particles.png",
        "process_material_path": "res://fire_particles.tres",
        "lifetime": 2.5,
        "interp_to_end": 0.25,
        "one_shot": False,
        "preprocess": 1.0,
        "speed_scale": 1.5,
        "explosiveness": 0.4,
        "randomness": 0.2,
        "use_fixed_seed": True,
        "seed": 42,
        "fixed_fps": 30,
        "interpolate": True,
        "fractional_delta": False,
        "collision_base_size": 2.0,
        "visibility_rect": {
            "position": {"x": -128.0, "y": -64.0},
            "size": {"x": 256.0, "y": 128.0},
        },
        "local_coords": True,
        "draw_order": "reverse_lifetime",
        "trail_enabled": True,
        "trail_lifetime": 0.5,
        "trail_sections": 8,
        "trail_section_subdivisions": 4,
    }

    await service.gpu_particles_2d_get(path, session_id="project@a1b2", scene_file=scene_file)
    await service.gpu_particles_2d_set(path, properties, scene_file=scene_file)

    assert bridge.calls == [
        (
            "gpu_particles_2d_get",
            {"path": path, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "gpu_particles_2d_set",
            {"path": path, "properties": properties, "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_gpu_particles_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/Fire"

    with pytest.raises(ValueError, match="non-empty"):
        await service.gpu_particles_2d_set(path, {})
    with pytest.raises(ValueError, match="unsupported GPUParticles2D"):
        await service.gpu_particles_2d_set(path, {"playing": True})
    with pytest.raises(ValueError, match="amount"):
        await service.gpu_particles_2d_set(path, {"amount": 0})
    with pytest.raises(ValueError, match="seed"):
        await service.gpu_particles_2d_set(path, {"seed": True})
    with pytest.raises(ValueError, match="draw_order"):
        await service.gpu_particles_2d_set(path, {"draw_order": "front_to_back"})
    with pytest.raises(ValueError, match="texture_path"):
        await service.gpu_particles_2d_set(path, {"texture_path": "../particle.png"})
    with pytest.raises(ValueError, match="sub_emitter_path"):
        await service.gpu_particles_2d_set(path, {"sub_emitter_path": 42})
    with pytest.raises(ValueError, match="visibility_rect"):
        await service.gpu_particles_2d_set(path, {"visibility_rect": {"x": 1.0}})


@pytest.mark.asyncio
async def test_cpu_particles_2d_tools_forward_semantic_edits() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Fire"
    scene_file = "res://main.tscn"
    properties = {
        "emitting": True,
        "amount": 96,
        "texture_path": "res://particles.png",
        "lifetime": 2.5,
        "one_shot": True,
        "preprocess": 1.0,
        "speed_scale": 1.5,
        "explosiveness": 0.4,
        "randomness": 0.2,
        "use_fixed_seed": True,
        "seed": 42,
        "lifetime_randomness": 0.3,
        "fixed_fps": 30,
        "fractional_delta": False,
        "local_coords": True,
        "draw_order": "lifetime",
        "emission_shape": "directed_points",
        "emission_sphere_radius": 12.0,
        "emission_rect_extents": {"x": 32.0, "y": 16.0},
        "emission_points": [{"x": -8.0, "y": 4.0}, {"x": 8.0, "y": -4.0}],
        "emission_normals": [{"x": 0.0, "y": -1.0}, {"x": 1.0, "y": 0.0}],
        "emission_colors": ["ff8040cc", {"r": 0.1, "g": 0.2, "b": 0.3, "a": 0.4}],
        "emission_ring_inner_radius": 4.0,
        "emission_ring_radius": 10.0,
        "align_y_to_velocity": True,
        "direction": {"x": 0.5, "y": -1.0},
        "spread": 20.0,
        "gravity": {"x": 0.0, "y": 98.0},
        "initial_velocity_min": 32.0,
        "initial_velocity_max": 64.0,
        "angular_velocity_min": -10.0,
        "angular_velocity_max": 20.0,
        "orbit_velocity_min": -0.5,
        "orbit_velocity_max": 0.75,
        "linear_accel_min": -5.0,
        "linear_accel_max": 10.0,
        "radial_accel_min": -4.0,
        "radial_accel_max": 6.0,
        "tangential_accel_min": -3.0,
        "tangential_accel_max": 7.0,
        "damping_min": 0.1,
        "damping_max": 0.8,
        "angle_min": -15.0,
        "angle_max": 30.0,
        "scale_amount_min": 0.5,
        "scale_amount_max": 1.5,
        "hue_variation_min": -0.25,
        "hue_variation_max": 0.5,
        "anim_speed_min": 0.25,
        "anim_speed_max": 1.0,
        "anim_offset_min": 0.0,
        "anim_offset_max": 0.5,
        "split_scale": True,
        "color": {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
    }

    await service.cpu_particles_2d_get(path, session_id="project@a1b2", scene_file=scene_file)
    await service.cpu_particles_2d_set(path, properties, scene_file=scene_file)

    assert bridge.calls == [
        (
            "cpu_particles_2d_get",
            {"path": path, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "cpu_particles_2d_set",
            {"path": path, "properties": properties, "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_cpu_particles_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/Fire"

    with pytest.raises(ValueError, match="non-empty"):
        await service.cpu_particles_2d_set(path, {})
    with pytest.raises(ValueError, match="unsupported CPUParticles2D"):
        await service.cpu_particles_2d_set(path, {"process_material_path": "res://fire.tres"})
    with pytest.raises(ValueError, match="amount"):
        await service.cpu_particles_2d_set(path, {"amount": 0})
    with pytest.raises(ValueError, match="texture_path"):
        await service.cpu_particles_2d_set(path, {"texture_path": "../particle.png"})
    with pytest.raises(ValueError, match="emission_shape"):
        await service.cpu_particles_2d_set(path, {"emission_shape": "line"})
    with pytest.raises(ValueError, match="emission_rect_extents"):
        await service.cpu_particles_2d_set(
            path, {"emission_rect_extents": {"x": -1.0, "y": 2.0}}
        )
    with pytest.raises(ValueError, match="emission_points"):
        await service.cpu_particles_2d_set(
            path,
            {"emission_points": [{"x": float("inf"), "y": 0.0}]},
        )
    with pytest.raises(ValueError, match="emission_colors"):
        await service.cpu_particles_2d_set(path, {"emission_colors": [42]})
    with pytest.raises(ValueError, match="emission_ring_inner_radius"):
        await service.cpu_particles_2d_set(
            path,
            {"emission_ring_inner_radius": 8.0, "emission_ring_radius": 4.0},
        )


@pytest.mark.asyncio
async def test_cpu_particles_2d_resource_tools_forward_safe_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Fire"
    scene_file = "res://main.tscn"
    curve_properties = {
        "min_domain": 0.0,
        "max_domain": 1.0,
        "min_value": -2.0,
        "max_value": 2.0,
        "bake_resolution": 64,
        "points": [
            {
                "position": {"x": 0.0, "y": -1.0},
                "left_tangent": 0.0,
                "right_tangent": 1.0,
                "left_mode": "free",
                "right_mode": "linear",
            },
            {"position": {"x": 1.0, "y": 1.0}},
        ],
    }
    gradient_properties = {
        "points": [
            {"offset": 0.0, "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}},
            {"offset": 1.0, "color": "0000ffff"},
        ],
        "interpolation_mode": "cubic",
        "interpolation_color_space": "oklab",
    }

    await service.cpu_particles_2d_curve_get(
        path, "initial_velocity", session_id="project@a1b2", scene_file=scene_file
    )
    await service.cpu_particles_2d_curve_bind(
        path, "initial_velocity", "res://curve.tres", scene_file=scene_file
    )
    await service.cpu_particles_2d_curve_set(
        path, "initial_velocity", curve_properties, scene_file=scene_file
    )
    await service.cpu_particles_2d_curve_clear(path, "initial_velocity", scene_file=scene_file)
    await service.cpu_particles_2d_gradient_get(
        path, "color", session_id="project@a1b2", scene_file=scene_file
    )
    await service.cpu_particles_2d_gradient_bind(
        path, "color", "res://gradient.tres", scene_file=scene_file
    )
    await service.cpu_particles_2d_gradient_set(
        path, "color", gradient_properties, scene_file=scene_file
    )
    await service.cpu_particles_2d_gradient_clear(path, "color", scene_file=scene_file)

    assert bridge.calls == [
        (
            "cpu_particles_2d_curve_get",
            {"path": path, "curve": "initial_velocity", "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "cpu_particles_2d_curve_bind",
            {
                "path": path,
                "curve": "initial_velocity",
                "resource_path": "res://curve.tres",
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "cpu_particles_2d_curve_set",
            {
                "path": path,
                "curve": "initial_velocity",
                "properties": curve_properties,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "cpu_particles_2d_curve_clear",
            {"path": path, "curve": "initial_velocity", "scene_file": scene_file},
            None,
        ),
        (
            "cpu_particles_2d_gradient_get",
            {"path": path, "gradient": "color", "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "cpu_particles_2d_gradient_bind",
            {
                "path": path,
                "gradient": "color",
                "resource_path": "res://gradient.tres",
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "cpu_particles_2d_gradient_set",
            {
                "path": path,
                "gradient": "color",
                "properties": gradient_properties,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "cpu_particles_2d_gradient_clear",
            {"path": path, "gradient": "color", "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_cpu_particles_2d_resource_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/Fire"

    with pytest.raises(ValueError, match="curve"):
        await service.cpu_particles_2d_curve_get(path, "velocity")
    with pytest.raises(ValueError, match="resource_path"):
        await service.cpu_particles_2d_curve_bind(path, "angle", "../curve.tres")
    with pytest.raises(ValueError, match="min_domain"):
        await service.cpu_particles_2d_curve_set(
            path,
            "angle",
            {"min_domain": 1.0, "max_domain": 0.0},
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        await service.cpu_particles_2d_curve_set(
            path,
            "angle",
            {
                "points": [
                    {"position": {"x": 0.5, "y": 0.0}},
                    {"position": {"x": 0.25, "y": 0.0}},
                ]
            },
        )
    with pytest.raises(ValueError, match="left_mode"):
        await service.cpu_particles_2d_curve_set(
            path,
            "angle",
            {"points": [{"position": {"x": 0.0, "y": 0.0}, "left_mode": "cubic"}]},
        )
    with pytest.raises(ValueError, match="gradient"):
        await service.cpu_particles_2d_gradient_get(path, "ramp")
    with pytest.raises(ValueError, match="between 2 and 512"):
        await service.cpu_particles_2d_gradient_set(
            path,
            "color",
            {"points": [{"offset": 0.0, "color": "ffffff"}]},
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        await service.cpu_particles_2d_gradient_set(
            path,
            "color",
            {
                "points": [
                    {"offset": 0.5, "color": "ffffff"},
                    {"offset": 0.5, "color": "000000"},
                ]
            },
        )
    with pytest.raises(ValueError, match="interpolation_color_space"):
        await service.cpu_particles_2d_gradient_set(
            path,
            "color",
            {"interpolation_color_space": "display_p3"},
        )


@pytest.mark.asyncio
async def test_particle_process_material_2d_tools_forward_copy_on_write_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Fire"
    scene_file = "res://main.tscn"
    properties = {
        "lifetime_randomness": 0.25,
        "align_y_to_velocity": True,
        "disable_z": True,
        "emission_shape": "box",
        "emission_shape_offset": {"x": 4.0, "y": 8.0},
        "emission_box_extents": {"x": 32.0, "y": 16.0},
        "direction": {"x": 1.0, "y": -0.5},
        "spread": 20.0,
        "initial_velocity_min": 32.0,
        "initial_velocity_max": 64.0,
        "gravity": {"x": 0.0, "y": 98.0},
        "scale_min": 0.5,
        "scale_max": 1.5,
        "color": {"r": 1.0, "g": 0.5, "b": 0.25, "a": 1.0},
        "collision_mode": "rigid",
        "sub_emitter_mode": "at_collision",
        "sub_emitter_amount_at_collision": 2,
    }

    await service.particle_process_material_2d_get(
        path, session_id="project@a1b2", scene_file=scene_file
    )
    await service.particle_process_material_2d_create(path, scene_file=scene_file)
    await service.particle_process_material_2d_set(path, properties, scene_file=scene_file)

    assert bridge.calls == [
        (
            "particle_process_material_2d_get",
            {"path": path, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "particle_process_material_2d_create",
            {"path": path, "replace_existing": False, "scene_file": scene_file},
            None,
        ),
        (
            "particle_process_material_2d_set",
            {"path": path, "properties": properties, "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_particle_process_material_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/Fire"

    with pytest.raises(ValueError, match="replace_existing"):
        await service.particle_process_material_2d_create(path, replace_existing=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        await service.particle_process_material_2d_set(path, {})
    with pytest.raises(ValueError, match="unsupported ParticleProcessMaterial"):
        await service.particle_process_material_2d_set(path, {"color_ramp_path": "res://ramp.tres"})
    with pytest.raises(ValueError, match="emission_shape"):
        await service.particle_process_material_2d_set(path, {"emission_shape": "line"})
    with pytest.raises(ValueError, match="emission_box_extents"):
        await service.particle_process_material_2d_set(
            path, {"emission_box_extents": {"x": -1.0, "y": 2.0}}
        )
    with pytest.raises(ValueError, match="scale_min"):
        await service.particle_process_material_2d_set(path, {"scale_min": -0.1})
    with pytest.raises(ValueError, match="emission_ring_inner_radius"):
        await service.particle_process_material_2d_set(
            path,
            {"emission_ring_inner_radius": 8.0, "emission_ring_radius": 4.0},
        )


@pytest.mark.asyncio
async def test_particle_process_material_2d_resource_tools_forward_safe_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Fire"
    scene_file = "res://main.tscn"
    curve_properties = {
        "width": 128,
        "texture_mode": "red",
        "min_domain": 0.0,
        "max_domain": 1.0,
        "min_value": -2.0,
        "max_value": 2.0,
        "bake_resolution": 64,
        "points": [
            {"position": {"x": 0.0, "y": -1.0}, "right_mode": "linear"},
            {"position": {"x": 1.0, "y": 1.0}, "left_mode": "linear"},
        ],
    }
    gradient_properties = {
        "width": 512,
        "use_hdr": True,
        "points": [
            {"offset": 0.0, "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}},
            {"offset": 1.0, "color": "0000ffff"},
        ],
        "interpolation_mode": "cubic",
        "interpolation_color_space": "oklab",
    }

    await service.particle_process_material_2d_curve_get(
        path, "scale", session_id="project@a1b2", scene_file=scene_file
    )
    await service.particle_process_material_2d_curve_bind(
        path, "scale", "res://curve_texture.tres", scene_file=scene_file
    )
    await service.particle_process_material_2d_curve_set(
        path, "scale", curve_properties, scene_file=scene_file
    )
    await service.particle_process_material_2d_curve_clear(path, "scale", scene_file=scene_file)
    await service.particle_process_material_2d_gradient_get(
        path, "color", session_id="project@a1b2", scene_file=scene_file
    )
    await service.particle_process_material_2d_gradient_bind(
        path, "color", "res://gradient_texture.tres", scene_file=scene_file
    )
    await service.particle_process_material_2d_gradient_set(
        path, "color", gradient_properties, scene_file=scene_file
    )
    await service.particle_process_material_2d_gradient_clear(path, "color", scene_file=scene_file)

    assert bridge.calls == [
        (
            "particle_process_material_2d_curve_get",
            {"path": path, "curve": "scale", "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "particle_process_material_2d_curve_bind",
            {
                "path": path,
                "curve": "scale",
                "resource_path": "res://curve_texture.tres",
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "particle_process_material_2d_curve_set",
            {
                "path": path,
                "curve": "scale",
                "properties": curve_properties,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "particle_process_material_2d_curve_clear",
            {"path": path, "curve": "scale", "scene_file": scene_file},
            None,
        ),
        (
            "particle_process_material_2d_gradient_get",
            {"path": path, "gradient": "color", "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "particle_process_material_2d_gradient_bind",
            {
                "path": path,
                "gradient": "color",
                "resource_path": "res://gradient_texture.tres",
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "particle_process_material_2d_gradient_set",
            {
                "path": path,
                "gradient": "color",
                "properties": gradient_properties,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "particle_process_material_2d_gradient_clear",
            {"path": path, "gradient": "color", "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_particle_process_material_2d_resource_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/Fire"

    with pytest.raises(ValueError, match="curve"):
        await service.particle_process_material_2d_curve_get(path, "initial_velocity")
    with pytest.raises(ValueError, match="resource_path"):
        await service.particle_process_material_2d_curve_bind(path, "scale", "../curve.tres")
    with pytest.raises(ValueError, match="width"):
        await service.particle_process_material_2d_curve_set(path, "scale", {"width": 16})
    with pytest.raises(ValueError, match="texture_mode"):
        await service.particle_process_material_2d_curve_set(
            path, "scale", {"texture_mode": "alpha"}
        )
    with pytest.raises(ValueError, match="min_domain"):
        await service.particle_process_material_2d_curve_set(
            path, "scale", {"min_domain": 1.0, "max_domain": 0.0}
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        await service.particle_process_material_2d_gradient_set(
            path,
            "color",
            {
                "points": [
                    {"offset": 0.5, "color": "ffffffff"},
                    {"offset": 0.25, "color": "ffffffff"},
                ]
            },
        )
    with pytest.raises(ValueError, match="use_hdr"):
        await service.particle_process_material_2d_gradient_set(path, "color", {"use_hdr": 1})


@pytest.mark.asyncio
async def test_canvas_item_material_tools_forward_copy_on_write_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Badge"
    scene_file = "res://main.tscn"
    properties = {
        "blend_mode": "add",
        "light_mode": "unshaded",
        "particles_animation": True,
        "particles_anim_h_frames": 4,
        "particles_anim_v_frames": 2,
        "particles_anim_loop": True,
    }

    await service.canvas_item_material_get(path, session_id="project@a1b2", scene_file=scene_file)
    await service.canvas_item_material_create(path, scene_file=scene_file)
    await service.canvas_item_material_bind(
        path, "res://canvas_material.tres", scene_file=scene_file
    )
    await service.canvas_item_material_set(path, properties, scene_file=scene_file)
    await service.canvas_item_material_clear(path, scene_file=scene_file)

    assert bridge.calls == [
        (
            "canvas_item_material_get",
            {"path": path, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "canvas_item_material_create",
            {"path": path, "replace_existing": False, "scene_file": scene_file},
            None,
        ),
        (
            "canvas_item_material_bind",
            {
                "path": path,
                "resource_path": "res://canvas_material.tres",
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "canvas_item_material_set",
            {"path": path, "properties": properties, "scene_file": scene_file},
            None,
        ),
        (
            "canvas_item_material_clear",
            {"path": path, "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_canvas_item_material_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/Badge"

    with pytest.raises(ValueError, match="replace_existing"):
        await service.canvas_item_material_create(path, replace_existing=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="resource_path"):
        await service.canvas_item_material_bind(path, "canvas_material.tres")
    with pytest.raises(ValueError, match="non-empty"):
        await service.canvas_item_material_set(path, {})
    with pytest.raises(ValueError, match="unsupported CanvasItemMaterial"):
        await service.canvas_item_material_set(path, {"shader": "res://shader.gdshader"})
    with pytest.raises(ValueError, match="blend_mode"):
        await service.canvas_item_material_set(path, {"blend_mode": "screen"})
    with pytest.raises(ValueError, match="particles_anim_h_frames"):
        await service.canvas_item_material_set(path, {"particles_anim_h_frames": 0})
    with pytest.raises(ValueError, match="particles_anim_loop"):
        await service.canvas_item_material_set(path, {"particles_anim_loop": 1})


@pytest.mark.asyncio
async def test_canvas_item_shader_tools_forward_copy_on_write_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Badge"
    scene_file = "res://main.tscn"
    source = "shader_type canvas_item;\nvoid fragment() { COLOR = vec4(1.0); }\n"

    await service.canvas_item_shader_get(path, session_id="project@a1b2", scene_file=scene_file)
    await service.canvas_item_shader_create(path, source=source, scene_file=scene_file)
    await service.canvas_item_shader_bind(
        path, "res://canvas_item_shader_material.tres", scene_file=scene_file
    )
    await service.canvas_item_shader_set(path, source, scene_file=scene_file)
    await service.canvas_item_shader_clear(path, scene_file=scene_file)

    assert bridge.calls == [
        (
            "canvas_item_shader_get",
            {"path": path, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "canvas_item_shader_create",
            {
                "path": path,
                "source": source,
                "replace_existing": False,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "canvas_item_shader_bind",
            {
                "path": path,
                "resource_path": "res://canvas_item_shader_material.tres",
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "canvas_item_shader_set",
            {"path": path, "source": source, "scene_file": scene_file},
            None,
        ),
        (
            "canvas_item_shader_clear",
            {"path": path, "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_canvas_item_shader_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())
    path = "/Main/Badge"

    with pytest.raises(ValueError, match="replace_existing"):
        await service.canvas_item_shader_create(path, replace_existing=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="source"):
        await service.canvas_item_shader_create(path, source="")
    with pytest.raises(ValueError, match="source"):
        await service.canvas_item_shader_set(path, "x" * 65_537)
    with pytest.raises(ValueError, match="resource_path"):
        await service.canvas_item_shader_bind(path, "canvas_item_shader_material.tres")


@pytest.mark.asyncio
async def test_lighting_tools_forward_atomic_semantic_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    light_path = "/Main/KeyLight"
    occluder_path = "/Main/WallOccluder"
    scene_file = "res://main.tscn"
    light_properties = {
        "enabled": True,
        "color": {"r": 1.0, "g": 0.8, "b": 0.4, "a": 1.0},
        "energy": 2.5,
        "blend_mode": "add",
        "range_item_cull_layers": [1, 3],
        "shadow_enabled": True,
        "shadow_filter": "pcf5",
        "shadow_item_cull_layers": [2],
        "height": 64.0,
        "texture_path": "res://light.png",
        "offset": {"x": 4.0, "y": -2.0},
        "texture_scale": 1.25,
    }
    polygon = {
        "points": [
            {"x": -8.0, "y": -8.0},
            {"x": 8.0, "y": -8.0},
            {"x": 8.0, "y": 8.0},
            {"x": -8.0, "y": 8.0},
        ],
        "closed": True,
        "cull_mode": "counter_clockwise",
    }

    await service.light_2d_get(light_path, session_id="project@a1b2", scene_file=scene_file)
    await service.light_occluder_2d_get(occluder_path, scene_file=scene_file)
    await service.light_2d_set(light_path, light_properties, scene_file=scene_file)
    await service.light_occluder_2d_set(
        occluder_path,
        layers=[2, 5],
        sdf_collision=True,
        polygon=polygon,
        scene_file=scene_file,
    )
    await service.light_occluder_2d_set(occluder_path, clear=True, scene_file=scene_file)

    assert bridge.calls == [
        ("light_2d_get", {"path": light_path, "scene_file": scene_file}, "project@a1b2"),
        ("light_occluder_2d_get", {"path": occluder_path, "scene_file": scene_file}, None),
        (
            "light_2d_set",
            {"path": light_path, "properties": light_properties, "scene_file": scene_file},
            None,
        ),
        (
            "light_occluder_2d_set",
            {
                "path": occluder_path,
                "layers": [2, 5],
                "sdf_collision": True,
                "polygon": polygon,
                "clear": False,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "light_occluder_2d_set",
            {
                "path": occluder_path,
                "layers": None,
                "sdf_collision": None,
                "polygon": None,
                "clear": True,
                "scene_file": scene_file,
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_lighting_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="non-empty"):
        await service.light_2d_set("/Main/KeyLight", {})
    with pytest.raises(ValueError, match="unsupported light property"):
        await service.light_2d_set("/Main/KeyLight", {"texture": "res://light.png"})
    with pytest.raises(ValueError, match="texture_path"):
        await service.light_2d_set("/Main/KeyLight", {"texture_path": "/tmp/light.png"})
    with pytest.raises(ValueError, match="range_item_cull_layers"):
        await service.light_2d_set("/Main/KeyLight", {"range_item_cull_layers": [1, 1]})
    with pytest.raises(ValueError, match="shadow_filter_smooth"):
        await service.light_2d_set("/Main/KeyLight", {"shadow_filter_smooth": 65.0})
    with pytest.raises(ValueError, match="layers, sdf_collision, polygon, or clear"):
        await service.light_occluder_2d_set("/Main/WallOccluder")
    with pytest.raises(ValueError, match="sdf_collision"):
        await service.light_occluder_2d_set("/Main/WallOccluder", sdf_collision=1)
    with pytest.raises(ValueError, match="clear cannot"):
        await service.light_occluder_2d_set(
            "/Main/WallOccluder",
            polygon={"points": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}]},
            clear=True,
        )
    with pytest.raises(ValueError, match="between two"):
        await service.light_occluder_2d_set(
            "/Main/WallOccluder",
            polygon={"points": [{"x": 0.0, "y": 0.0}], "closed": False},
        )
    with pytest.raises(ValueError, match="cull_mode"):
        await service.light_occluder_2d_set(
            "/Main/WallOccluder",
            polygon={
                "points": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 1.0, "y": 0.0},
                    {"x": 0.0, "y": 1.0},
                ],
                "cull_mode": "front",
            },
        )


@pytest.mark.asyncio
async def test_tilemap_tools_forward_semantic_edits() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    cells = [
        {
            "coords": {"x": -2, "y": 3},
            "source_id": 4,
            "atlas_coords": {"x": 1, "y": 2},
            "alternative_tile": 0,
        }
    ]

    await service.tile_map_layer_get(
        "/Main/Tiles", session_id="project@a1b2", scene_file="res://main.tscn"
    )
    await service.tile_map_layer_cells_get(
        "/Main/Tiles", offset=10, limit=50, scene_file="res://main.tscn"
    )
    await service.tile_set_get("/Main/Tiles", scene_file="res://main.tscn")
    await service.tile_set_create(
        "/Main/Tiles", tile_size={"x": 32, "y": 16}, scene_file="res://main.tscn"
    )
    await service.tile_set_atlas_source_create(
        "/Main/Tiles",
        texture_path="res://tiles.svg",
        source_id=4,
        texture_region_size={"x": 32, "y": 32},
        margins={"x": 1, "y": 2},
        separation={"x": 3, "y": 4},
        scene_file="res://main.tscn",
    )
    await service.tile_set_atlas_tile_create(
        "/Main/Tiles",
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        size={"x": 2, "y": 1},
        scene_file="res://main.tscn",
    )
    await service.tile_map_layer_cells_set("/Main/Tiles", cells, scene_file="res://main.tscn")
    await service.tile_map_layer_cells_clear(
        "/Main/Tiles", [{"x": -2, "y": 3}], scene_file="res://main.tscn"
    )
    await service.tile_set_clear("/Main/Tiles", scene_file="res://main.tscn")

    assert bridge.calls == [
        (
            "tile_map_layer_get",
            {"path": "/Main/Tiles", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "tile_map_layer_cells_get",
            {
                "path": "/Main/Tiles",
                "offset": 10,
                "limit": 50,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "tile_set_get",
            {
                "path": "/Main/Tiles",
                "offset": 0,
                "limit": 100,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "tile_set_create",
            {
                "path": "/Main/Tiles",
                "tile_size": {"x": 32, "y": 16},
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "tile_set_atlas_source_create",
            {
                "path": "/Main/Tiles",
                "texture_path": "res://tiles.svg",
                "source_id": 4,
                "texture_region_size": {"x": 32, "y": 32},
                "margins": {"x": 1, "y": 2},
                "separation": {"x": 3, "y": 4},
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "tile_set_atlas_tile_create",
            {
                "path": "/Main/Tiles",
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "size": {"x": 2, "y": 1},
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "tile_map_layer_cells_set",
            {"path": "/Main/Tiles", "cells": cells, "scene_file": "res://main.tscn"},
            None,
        ),
        (
            "tile_map_layer_cells_clear",
            {
                "path": "/Main/Tiles",
                "coords": [{"x": -2, "y": 3}],
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "tile_set_clear",
            {"path": "/Main/Tiles", "scene_file": "res://main.tscn"},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_tileset_semantic_tools_forward_atomic_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Tiles"
    scene_file = "res://main.tscn"

    collision_polygons = [
        {
            "points": [
                {"x": -8.0, "y": -8.0},
                {"x": 8.0, "y": -8.0},
                {"x": 8.0, "y": 8.0},
            ],
            "one_way": True,
            "one_way_margin": 2.5,
        }
    ]
    navigation_vertices = [
        {"x": -8.0, "y": -8.0},
        {"x": 8.0, "y": -8.0},
        {"x": 8.0, "y": 8.0},
    ]
    occlusion_polygons = [
        {
            "points": [
                {"x": -8.0, "y": -8.0},
                {"x": 8.0, "y": -8.0},
                {"x": 8.0, "y": 8.0},
                {"x": -8.0, "y": 8.0},
            ],
            "closed": True,
            "cull_mode": "counter_clockwise",
        }
    ]

    await service.tile_set_layers_get(path, scene_file=scene_file)
    await service.tile_set_atlas_tile_get(
        path,
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        alternative_tile=1,
        scene_file=scene_file,
    )
    await service.tile_set_physics_layer_create(
        path,
        layers=[2],
        masks=[1, 3],
        priority=0.5,
        scene_file=scene_file,
    )
    await service.tile_set_navigation_layer_create(path, layers=[4], scene_file=scene_file)
    await service.tile_set_occlusion_layer_create(
        path,
        layers=[2, 5],
        sdf_collision=True,
        scene_file=scene_file,
    )
    await service.tile_set_custom_data_layer_create(
        path, name="damage", value_type="int", scene_file=scene_file
    )
    await service.tile_set_terrain_set_create(path, mode="match_sides", scene_file=scene_file)
    await service.tile_set_terrain_create(
        path,
        terrain_set=0,
        name="Ground",
        color="#39b54a",
        scene_file=scene_file,
    )
    await service.tile_set_atlas_alternative_create(
        path,
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        alternative_tile=1,
        scene_file=scene_file,
    )
    await service.tile_set_atlas_tile_terrain_set(
        path,
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        terrain_set=0,
        terrain=0,
        peering_bits={"right_side": 0},
        alternative_tile=1,
        scene_file=scene_file,
    )
    await service.tile_set_atlas_tile_custom_data_set(
        path,
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        values={"damage": 8},
        alternative_tile=1,
        scene_file=scene_file,
    )
    await service.tile_set_atlas_tile_collision_set(
        path,
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        physics_layer=0,
        polygons=collision_polygons,
        alternative_tile=1,
        scene_file=scene_file,
    )
    await service.tile_set_atlas_tile_navigation_set(
        path,
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        navigation_layer=0,
        vertices=navigation_vertices,
        polygons=[[0, 1, 2]],
        agent_radius=0.5,
        alternative_tile=1,
        scene_file=scene_file,
    )
    await service.tile_set_atlas_tile_occlusion_set(
        path,
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        occlusion_layer=0,
        polygons=occlusion_polygons,
        alternative_tile=1,
        scene_file=scene_file,
    )
    await service.tile_set_atlas_tile_navigation_set(
        path,
        source_id=4,
        atlas_coords={"x": 1, "y": 2},
        navigation_layer=0,
        clear=True,
        alternative_tile=1,
        scene_file=scene_file,
    )

    assert bridge.calls == [
        ("tile_set_layers_get", {"path": path, "scene_file": scene_file}, None),
        (
            "tile_set_atlas_tile_get",
            {
                "path": path,
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "alternative_tile": 1,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_physics_layer_create",
            {
                "path": path,
                "layers": [2],
                "masks": [1, 3],
                "priority": 0.5,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_navigation_layer_create",
            {"path": path, "layers": [4], "scene_file": scene_file},
            None,
        ),
        (
            "tile_set_occlusion_layer_create",
            {
                "path": path,
                "layers": [2, 5],
                "sdf_collision": True,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_custom_data_layer_create",
            {
                "path": path,
                "name": "damage",
                "value_type": "int",
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_terrain_set_create",
            {"path": path, "mode": "match_sides", "scene_file": scene_file},
            None,
        ),
        (
            "tile_set_terrain_create",
            {
                "path": path,
                "terrain_set": 0,
                "name": "Ground",
                "color": "#39b54a",
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_atlas_alternative_create",
            {
                "path": path,
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "alternative_tile": 1,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_atlas_tile_terrain_set",
            {
                "path": path,
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "terrain_set": 0,
                "terrain": 0,
                "peering_bits": {"right_side": 0},
                "alternative_tile": 1,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_atlas_tile_custom_data_set",
            {
                "path": path,
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "values": {"damage": 8},
                "alternative_tile": 1,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_atlas_tile_collision_set",
            {
                "path": path,
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "physics_layer": 0,
                "polygons": collision_polygons,
                "alternative_tile": 1,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_atlas_tile_navigation_set",
            {
                "path": path,
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "navigation_layer": 0,
                "clear": False,
                "alternative_tile": 1,
                "vertices": navigation_vertices,
                "polygons": [[0, 1, 2]],
                "agent_radius": 0.5,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_atlas_tile_occlusion_set",
            {
                "path": path,
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "occlusion_layer": 0,
                "polygons": occlusion_polygons,
                "alternative_tile": 1,
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "tile_set_atlas_tile_navigation_set",
            {
                "path": path,
                "source_id": 4,
                "atlas_coords": {"x": 1, "y": 2},
                "navigation_layer": 0,
                "clear": True,
                "alternative_tile": 1,
                "scene_file": scene_file,
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_tilemap_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="limit"):
        await service.tile_map_layer_cells_get("/Main/Tiles", limit=0)
    with pytest.raises(ValueError, match="tile_size"):
        await service.tile_set_create("/Main/Tiles", tile_size={"x": 0, "y": 16})
    with pytest.raises(ValueError, match="texture_path"):
        await service.tile_set_atlas_source_create("/Main/Tiles", texture_path="/tmp/tiles.png")
    with pytest.raises(ValueError, match="source_id"):
        await service.tile_set_atlas_tile_create(
            "/Main/Tiles", source_id=-1, atlas_coords={"x": 0, "y": 0}
        )
    with pytest.raises(ValueError, match="alternative_tile"):
        await service.tile_map_layer_cells_set(
            "/Main/Tiles",
            [
                {
                    "coords": {"x": 0, "y": 0},
                    "source_id": 0,
                    "atlas_coords": {"x": 0, "y": 0},
                    "alternative_tile": -1,
                }
            ],
        )
    with pytest.raises(ValueError, match="duplicates"):
        await service.tile_map_layer_cells_clear(
            "/Main/Tiles", [{"x": 0, "y": 0}, {"x": 0, "y": 0}]
        )
    with pytest.raises(ValueError, match="priority"):
        await service.tile_set_physics_layer_create("/Main/Tiles", priority=-0.1)
    with pytest.raises(ValueError, match="value_type"):
        await service.tile_set_custom_data_layer_create(
            "/Main/Tiles", name="damage", value_type="resource"
        )
    with pytest.raises(ValueError, match="terrain_set"):
        await service.tile_set_terrain_create("/Main/Tiles", terrain_set=-1)
    with pytest.raises(ValueError, match="alternative_tile"):
        await service.tile_set_atlas_alternative_create(
            "/Main/Tiles", source_id=0, atlas_coords={"x": 0, "y": 0}, alternative_tile=0
        )
    with pytest.raises(ValueError, match="terrain must be -1"):
        await service.tile_set_atlas_tile_terrain_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            terrain_set=-1,
            terrain=0,
        )
    with pytest.raises(ValueError, match="values"):
        await service.tile_set_atlas_tile_custom_data_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            values={},
        )
    with pytest.raises(ValueError, match="physics_layer"):
        await service.tile_set_atlas_tile_collision_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            physics_layer=-1,
            polygons=[],
        )
    with pytest.raises(ValueError, match="between three"):
        await service.tile_set_atlas_tile_collision_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            physics_layer=0,
            polygons=[{"points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}],
        )
    with pytest.raises(ValueError, match="vertices and polygons"):
        await service.tile_set_atlas_tile_navigation_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            navigation_layer=0,
        )
    with pytest.raises(ValueError, match="clear cannot"):
        await service.tile_set_atlas_tile_navigation_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            navigation_layer=0,
            vertices=[],
            clear=True,
        )
    with pytest.raises(ValueError, match="sdf_collision"):
        await service.tile_set_occlusion_layer_create("/Main/Tiles", sdf_collision=1)
    with pytest.raises(ValueError, match="occlusion_layer"):
        await service.tile_set_atlas_tile_occlusion_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            occlusion_layer=-1,
            polygons=[],
        )
    with pytest.raises(ValueError, match="between two"):
        await service.tile_set_atlas_tile_occlusion_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            occlusion_layer=0,
            polygons=[{"points": [{"x": 0, "y": 0}], "closed": False}],
        )
    with pytest.raises(ValueError, match="cull_mode"):
        await service.tile_set_atlas_tile_occlusion_set(
            "/Main/Tiles",
            source_id=0,
            atlas_coords={"x": 0, "y": 0},
            occlusion_layer=0,
            polygons=[
                {
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 1, "y": 0},
                        {"x": 0, "y": 1},
                    ],
                    "cull_mode": "front",
                }
            ],
        )
