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
