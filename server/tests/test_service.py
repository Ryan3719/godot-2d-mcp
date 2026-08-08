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


class CoverageBridge(FakeBridge):
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        super().__init__()
        self.pages = pages

    async def call(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((command, params or {}, session_id))
        if command != "class_2d_coverage" or not self.pages:
            raise AssertionError(f"Unexpected coverage bridge call: {command}")
        return self.pages.pop(0)


def _coverage_entry(
    name: str,
    *,
    kind: str = "node",
    parent: str = "Control",
    instantiable: bool = True,
    semantic_tools: list[str] | None = None,
) -> dict[str, Any]:
    tools = semantic_tools or []
    return {
        "name": name,
        "parent": parent,
        "kind": kind,
        "category": "ui" if kind == "node" else "resource",
        "instantiable": instantiable,
        "property_count": 12,
        "signal_count": 2,
        "base_support": {
            "create": kind == "node",
            "inspect_properties": kind == "node",
            "scene_structure": kind == "node",
            "set_properties": kind == "node",
        },
        "semantic_tools": tools,
        "support_level": "semantic" if tools else "generic",
        "test_status": "semantic_smoke" if tools else "not_directly_smoke_covered",
    }


def _coverage_page(
    entries: list[dict[str, Any]], *, has_more: bool = False, total: int | None = None
) -> dict[str, Any]:
    return {
        "audit_version": 1,
        "engine": {"major": 4, "minor": 7, "patch": 0, "status": "stable"},
        "entries": entries,
        "total": len(entries) if total is None else total,
        "has_more": has_more,
    }


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
async def test_animated_sprite_and_sprite_frames_tools_forward_validated_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    frames = [{"texture_path": "res://art/idle.png", "duration": 0.25}]

    await service.animated_sprite_2d_get(
        "/Main/Actor", scene_file="res://main.tscn", session_id="project@a1b2"
    )
    await service.sprite_frames_get(
        "/Main/Actor",
        animation=" idle ",
        frame_offset=2,
        frame_limit=20,
        scene_file="res://main.tscn",
    )
    await service.animated_sprite_2d_set(
        "/Main/Actor",
        {"sprite_frames_path": "res://art/actor_frames.tres", "speed_scale": 1.5},
        scene_file="res://main.tscn",
    )
    await service.sprite_frames_animation_upsert(
        "/Main/Actor",
        " idle ",
        speed=12.0,
        loop_mode=" PINGPONG ",
        frames=frames,
        scene_file="res://main.tscn",
    )
    await service.sprite_frames_animation_rename(
        "/Main/Actor", "idle", "run", scene_file="res://main.tscn"
    )
    await service.sprite_frames_animation_remove(
        "/Main/Actor", "run", scene_file="res://main.tscn"
    )

    assert bridge.calls == [
        (
            "animated_sprite_2d_get",
            {"path": "/Main/Actor", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "sprite_frames_get",
            {
                "path": "/Main/Actor",
                "animation": "idle",
                "frame_offset": 2,
                "frame_limit": 20,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "animated_sprite_2d_set",
            {
                "path": "/Main/Actor",
                "properties": {
                    "sprite_frames_path": "res://art/actor_frames.tres",
                    "speed_scale": 1.5,
                },
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "sprite_frames_animation_upsert",
            {
                "path": "/Main/Actor",
                "animation": "idle",
                "speed": 12.0,
                "loop_mode": "pingpong",
                "frames": frames,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "sprite_frames_animation_rename",
            {
                "path": "/Main/Actor",
                "animation": "idle",
                "new_name": "run",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "sprite_frames_animation_remove",
            {"path": "/Main/Actor", "animation": "run", "scene_file": "res://main.tscn"},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_sprite_frames_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="frame_limit"):
        await service.sprite_frames_get("/Main/Actor", frame_limit=257)
    with pytest.raises(ValueError, match="animation"):
        await service.animated_sprite_2d_set("/Main/Actor", {"animation": "bad/name"})
    with pytest.raises(ValueError, match="speed"):
        await service.sprite_frames_animation_upsert("/Main/Actor", "idle", speed=-1.0)
    with pytest.raises(ValueError, match="loop_mode"):
        await service.sprite_frames_animation_upsert("/Main/Actor", "idle", loop_mode="once")
    with pytest.raises(ValueError, match="texture_path"):
        await service.sprite_frames_animation_upsert(
            "/Main/Actor", "idle", frames=[{"texture_path": "../outside.png"}]
        )
    with pytest.raises(ValueError, match="must differ"):
        await service.sprite_frames_animation_rename("/Main/Actor", "idle", " idle ")


@pytest.mark.asyncio
async def test_button_2d_tools_forward_validated_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    properties = {
        "toggle_mode": True,
        "button_pressed": True,
        "action_mode": " PRESS ",
        "button_mask": ["left", "right"],
        "button_group_path": "res://ui/group.tres",
        "text": "Launch",
        "icon_path": "res://ui/launch.svg",
        "alignment": "left",
        "autowrap_trim_flags": ["trim_start"],
        "uri": "https://godotengine.org",
        "underline": "on_hover",
        "ellipsis_char": ">",
        "texture_normal_path": "res://ui/normal.svg",
        "stretch_mode": "keep_aspect_centered",
    }

    await service.button_2d_get(
        "/Main/Launch", scene_file="res://main.tscn", session_id="project@a1b2"
    )
    await service.button_2d_set(
        "/Main/Launch",
        properties,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )

    assert bridge.calls == [
        (
            "button_2d_get",
            {"path": "/Main/Launch", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "button_2d_set",
            {
                "path": "/Main/Launch",
                "properties": properties,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
    ]


@pytest.mark.asyncio
async def test_button_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="toggle_mode"):
        await service.button_2d_set(
            "/Main/Launch", {"toggle_mode": False, "button_pressed": True}
        )
    with pytest.raises(ValueError, match="button_mask"):
        await service.button_2d_set("/Main/Launch", {"button_mask": ["left", "left"]})
    with pytest.raises(ValueError, match="alignment"):
        await service.button_2d_set("/Main/Launch", {"alignment": "fill"})
    with pytest.raises(ValueError, match="click_mask_path"):
        await service.button_2d_set("/Main/Launch", {"click_mask_path": "../mask.tres"})
    with pytest.raises(ValueError, match="underline"):
        await service.button_2d_set("/Main/Launch", {"underline": "sometimes"})
    with pytest.raises(ValueError, match="uri"):
        await service.button_2d_set("/Main/Launch", {"uri": "x" * 4097})
    with pytest.raises(ValueError, match="ellipsis_char"):
        await service.button_2d_set("/Main/Launch", {"ellipsis_char": "..."})
    with pytest.raises(ValueError, match="unsupported BaseButton property"):
        await service.button_2d_set("/Main/Launch", {"unknown": True})


@pytest.mark.asyncio
async def test_container_2d_tools_forward_validated_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    container_properties = {"alignment": " center "}
    child_properties = {
        "custom_minimum_size": {"x": 320.0, "y": 48.0},
        "size_flags_horizontal": ["fill", "expand"],
        "size_flags_vertical": ["shrink_end"],
        "size_flags_stretch_ratio": 2.5,
    }
    tab_item_properties = {
        "title": "Setup",
        "tooltip": "Configure the game",
        "icon_path": "res://ui/setup.svg",
        "icon_max_width": 24,
        "disabled": False,
        "hidden": True,
        "metadata": {"section": "setup", "steps": [1, 2]},
        "button_icon_path": "",
    }

    await service.container_2d_get(
        "/Main/Layout",
        child_offset=2,
        child_limit=20,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.tab_container_items_get(
        "/Main/Tabs",
        item_offset=1,
        item_limit=20,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.container_2d_set(
        "/Main/Layout",
        container_properties,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.tab_container_item_set(
        "/Main/Tabs",
        "/Main/Tabs/Setup",
        tab_item_properties,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.container_child_layout_set(
        "/Main/Layout",
        "/Main/Layout/Primary",
        child_properties,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )

    assert bridge.calls == [
        (
            "container_2d_get",
            {
                "path": "/Main/Layout",
                "child_offset": 2,
                "child_limit": 20,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "tab_container_items_get",
            {
                "path": "/Main/Tabs",
                "item_offset": 1,
                "item_limit": 20,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "container_2d_set",
            {
                "path": "/Main/Layout",
                "properties": container_properties,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "tab_container_item_set",
            {
                "path": "/Main/Tabs",
                "child_path": "/Main/Tabs/Setup",
                "properties": tab_item_properties,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "container_child_layout_set",
            {
                "path": "/Main/Layout",
                "child_path": "/Main/Layout/Primary",
                "properties": child_properties,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
    ]


@pytest.mark.asyncio
async def test_container_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="child_offset"):
        await service.container_2d_get("/Main/Layout", child_offset=-1)
    with pytest.raises(ValueError, match="unsupported Container property"):
        await service.container_2d_set("/Main/Layout", {"vertical": True})
    with pytest.raises(ValueError, match="ratio"):
        await service.container_2d_set("/Main/Layout", {"ratio": 0.0})
    with pytest.raises(ValueError, match="split_offsets"):
        await service.container_2d_set("/Main/Layout", {"split_offsets": [1.5]})
    with pytest.raises(ValueError, match="item_offset"):
        await service.tab_container_items_get("/Main/Tabs", item_offset=-1)
    with pytest.raises(ValueError, match="properties"):
        await service.tab_container_item_set("/Main/Tabs", "/Main/Tabs/Setup", {})
    with pytest.raises(ValueError, match="icon_path"):
        await service.tab_container_item_set(
            "/Main/Tabs", "/Main/Tabs/Setup", {"icon_path": "../setup.svg"}
        )
    with pytest.raises(ValueError, match="icon_max_width"):
        await service.tab_container_item_set(
            "/Main/Tabs", "/Main/Tabs/Setup", {"icon_max_width": 24.5}
        )
    with pytest.raises(ValueError, match="metadata"):
        await service.tab_container_item_set(
            "/Main/Tabs", "/Main/Tabs/Setup", {"metadata": {"invalid": {1, 2}}}
        )
    with pytest.raises(ValueError, match="size_flags_horizontal"):
        await service.container_child_layout_set(
            "/Main/Layout",
            "/Main/Layout/Primary",
            {"size_flags_horizontal": ["fill", "fill"]},
        )
    with pytest.raises(ValueError, match="custom_minimum_size"):
        await service.container_child_layout_set(
            "/Main/Layout",
            "/Main/Layout/Primary",
            {"custom_minimum_size": {"x": -1.0, "y": 1.0}},
        )


@pytest.mark.asyncio
async def test_button_menu_item_tools_forward_validated_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    items = [
        {
            "kind": "normal",
            "text": "Open",
            "id": 10,
            "icon_path": "res://ui/open.svg",
            "metadata": {"action": "open"},
            "disabled": False,
            "tooltip": "Open a scene",
            "indent": 1,
            "text_direction": "ltr",
            "auto_translate_mode": "always",
            "icon_max_width": 32,
            "icon_modulate": {"r": 1.0, "g": 0.8, "b": 0.2, "a": 1.0},
        },
        {"kind": "check", "text": "Grid", "checked": True},
        {"kind": "multistate", "text": "Quality", "max_states": 3, "state": 1},
        {"kind": "separator", "text": "Advanced"},
    ]

    await service.button_menu_items_get(
        "/Main/Actions", offset=4, limit=50, scene_file="res://main.tscn", session_id="project@a1b2"
    )
    await service.button_menu_items_set(
        "/Main/Actions",
        items,
        selected_index=1,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.button_menu_items_clear(
        "/Main/Actions", scene_file="res://main.tscn", session_id="project@a1b2"
    )

    assert bridge.calls == [
        (
            "button_menu_items_get",
            {"path": "/Main/Actions", "offset": 4, "limit": 50, "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "button_menu_items_set",
            {
                "path": "/Main/Actions",
                "items": items,
                "selected_index": 1,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "button_menu_items_clear",
            {"path": "/Main/Actions", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
    ]


@pytest.mark.asyncio
async def test_button_menu_item_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="offset"):
        await service.button_menu_items_get("/Main/Actions", offset=-1)
    with pytest.raises(ValueError, match="items"):
        await service.button_menu_items_set("/Main/Actions", [])
    with pytest.raises(ValueError, match="max_states"):
        await service.button_menu_items_set(
            "/Main/Actions", [{"kind": "multistate", "text": "Quality", "max_states": 1}]
        )
    with pytest.raises(ValueError, match="unsupported menu item field"):
        await service.button_menu_items_set(
            "/Main/Actions", [{"kind": "separator", "text": "Tools", "disabled": True}]
        )
    with pytest.raises(ValueError, match="JSON-compatible"):
        await service.button_menu_items_set(
            "/Main/Actions", [{"kind": "normal", "text": "Open", "metadata": {"bad": {1, 2}}}]
        )
    with pytest.raises(ValueError, match="selected_index"):
        await service.button_menu_items_set(
            "/Main/Actions", [{"kind": "normal", "text": "Open"}], selected_index=2
        )


@pytest.mark.asyncio
async def test_editor_run_and_stop_forward_validated_modes() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    await service.editor_run(
        mode=" custom ",
        scene_file="res://scenes/game.tscn",
        session_id="project@a1b2",
    )
    await service.editor_stop(session_id="project@a1b2")

    assert bridge.calls == [
        (
            "editor_run",
            {"mode": "custom", "scene_file": "res://scenes/game.tscn"},
            "project@a1b2",
        ),
        ("editor_stop", {}, "project@a1b2"),
    ]


@pytest.mark.asyncio
async def test_editor_run_rejects_invalid_modes_and_scene_paths() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="mode"):
        await service.editor_run(mode="remote")
    with pytest.raises(ValueError, match="only accepted"):
        await service.editor_run(mode="main", scene_file="res://scenes/game.tscn")
    with pytest.raises(ValueError, match="res://"):
        await service.editor_run(mode="custom", scene_file="../game.tscn")


@pytest.mark.asyncio
async def test_input_map_tools_forward_validated_project_actions() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    events = [
        {"type": "key", "physical_keycode": 65, "shift": True},
        {"type": "mouse_button", "button": 1, "device": -1},
        {"type": "joypad_button", "button": 0, "device": 2},
        {"type": "joypad_motion", "axis": 0, "axis_value": -1.0},
    ]

    await service.input_map_get(
        query=" move ", offset=4, limit=20, session_id="project@a1b2"
    )
    await service.input_map_action_upsert(
        " player_move_left ",
        events,
        deadzone=0.35,
        replace_existing=True,
        session_id="project@a1b2",
    )
    await service.input_map_action_delete(
        "player_move_left", confirm=True, session_id="project@a1b2"
    )
    await service.input_map_undo(session_id="project@a1b2")
    await service.input_map_redo(session_id="project@a1b2")

    assert bridge.calls == [
        ("input_map_get", {"query": "move", "offset": 4, "limit": 20}, "project@a1b2"),
        (
            "input_map_action_upsert",
            {
                "action": "player_move_left",
                "events": events,
                "replace_existing": True,
                "deadzone": 0.35,
            },
            "project@a1b2",
        ),
        (
            "input_map_action_delete",
            {"action": "player_move_left", "confirm": True},
            "project@a1b2",
        ),
        ("input_map_undo", {}, "project@a1b2"),
        ("input_map_redo", {}, "project@a1b2"),
    ]


@pytest.mark.asyncio
async def test_input_map_tools_reject_invalid_project_actions() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="action"):
        await service.input_map_action_upsert(" ", [])
    with pytest.raises(ValueError, match="exactly one"):
        await service.input_map_action_upsert(
            "jump", [{"type": "key", "keycode": 65, "unicode": 65}]
        )
    with pytest.raises(ValueError, match="command_or_control_autoremap"):
        await service.input_map_action_upsert(
            "jump",
            [{"type": "key", "keycode": 65, "command_or_control_autoremap": True, "ctrl": True}],
        )
    with pytest.raises(ValueError, match="button"):
        await service.input_map_action_upsert("jump", [{"type": "mouse_button", "button": 10}])
    with pytest.raises(ValueError, match="axis_value"):
        await service.input_map_action_upsert(
            "jump", [{"type": "joypad_motion", "axis": 0, "axis_value": 0}]
        )
    with pytest.raises(ValueError, match="deadzone"):
        await service.input_map_action_upsert(
            "jump", [{"type": "joypad_button", "button": 0}], deadzone=1.1
        )
    with pytest.raises(ValueError, match="replace_existing"):
        await service.input_map_action_upsert(
            "jump", [{"type": "joypad_button", "button": 0}], replace_existing="yes"  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="confirm"):
        await service.input_map_action_delete("jump", confirm="yes")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="offset"):
        await service.input_map_get(offset=-1)


@pytest.mark.asyncio
async def test_runtime_feedback_tools_forward_validated_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    events = [
        {"type": "action", "action": "ui_accept", "pressed": True},
        {"type": "key", "keycode": 65, "pressed": False, "shift": True},
        {
            "type": "mouse_button",
            "button": 1,
            "pressed": True,
            "position": {"x": 24, "y": 48},
        },
        {
            "type": "mouse_motion",
            "position": {"x": 30, "y": 50},
            "relative": {"x": 6, "y": 2},
        },
        {
            "type": "screen_touch",
            "index": 1,
            "position": {"x": 24, "y": 48},
            "pressed": True,
            "double_tap": True,
        },
        {
            "type": "screen_drag",
            "index": 1,
            "position": {"x": 48, "y": 72},
            "relative": {"x": 24, "y": 24},
            "screen_relative": {"x": 48, "y": 48},
            "pressure": 0.5,
            "tilt": {"x": 0.25, "y": -0.25},
            "pen_inverted": True,
        },
        {
            "type": "screen_touch",
            "index": 1,
            "position": {"x": 48, "y": 72},
            "pressed": False,
            "canceled": True,
        },
    ]

    await service.runtime_get_state(session_id="project@a1b2")
    await service.runtime_logs_get(after_sequence=4, limit=20, session_id="project@a1b2")
    await service.runtime_screenshot_request(
        format="jpeg",
        max_width=320,
        max_height=180,
        quality=0.75,
        session_id="project@a1b2",
    )
    await service.runtime_screenshot_get("screenshot-123", session_id="project@a1b2")
    await service.runtime_input_send(events, session_id="project@a1b2")
    await service.runtime_input_result_get("input-123", session_id="project@a1b2")
    await service.runtime_audio_stream_player_2d_control(
        "/RuntimeSmoke/RuntimeSound",
        "seek",
        position_seconds=1.25,
        session_id="project@a1b2",
    )
    await service.runtime_audio_stream_player_2d_control_result_get(
        "audio-123", session_id="project@a1b2"
    )
    await service.runtime_performance_sample_request(1.5, session_id="project@a1b2")
    await service.runtime_performance_sample_result_get(
        "performance-123", session_id="project@a1b2"
    )

    assert bridge.calls == [
        ("runtime_get_state", {}, "project@a1b2"),
        ("runtime_logs_get", {"after_sequence": 4, "limit": 20}, "project@a1b2"),
        (
            "runtime_screenshot_request",
            {"format": "jpeg", "max_width": 320, "max_height": 180, "quality": 0.75},
            "project@a1b2",
        ),
        ("runtime_screenshot_get", {"request_id": "screenshot-123"}, "project@a1b2"),
        ("runtime_input_send", {"events": events}, "project@a1b2"),
        ("runtime_input_result_get", {"request_id": "input-123"}, "project@a1b2"),
        (
            "runtime_audio_stream_player_2d_control",
            {
                "path": "/RuntimeSmoke/RuntimeSound",
                "action": "seek",
                "position_seconds": 1.25,
            },
            "project@a1b2",
        ),
        (
            "runtime_audio_stream_player_2d_control_result_get",
            {"request_id": "audio-123"},
            "project@a1b2",
        ),
        (
            "runtime_performance_sample_request",
            {"duration_seconds": 1.5},
            "project@a1b2",
        ),
        (
            "runtime_performance_sample_result_get",
            {"request_id": "performance-123"},
            "project@a1b2",
        ),
    ]


@pytest.mark.asyncio
async def test_runtime_feedback_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="format"):
        await service.runtime_screenshot_request(format="webp")
    with pytest.raises(ValueError, match="max_width"):
        await service.runtime_screenshot_request(max_width=0)
    with pytest.raises(ValueError, match="quality"):
        await service.runtime_screenshot_request(quality=1.1)
    with pytest.raises(ValueError, match="request_id"):
        await service.runtime_screenshot_get("")
    with pytest.raises(ValueError, match="between 1 and 64"):
        await service.runtime_input_send([])
    with pytest.raises(ValueError, match="exactly one"):
        await service.runtime_input_send(
            [{"type": "key", "keycode": 65, "unicode": 65, "pressed": True}]
        )
    with pytest.raises(ValueError, match="position"):
        await service.runtime_input_send(
            [{"type": "mouse_button", "button": 1, "pressed": True, "position": {"x": 1}}]
        )
    with pytest.raises(ValueError, match="index"):
        await service.runtime_input_send(
            [{"type": "screen_touch", "index": -1, "position": {"x": 1, "y": 1}, "pressed": True}]
        )
    with pytest.raises(ValueError, match="pressure"):
        await service.runtime_input_send(
            [
                {
                    "type": "screen_drag",
                    "index": 0,
                    "position": {"x": 1, "y": 1},
                    "relative": {"x": 1, "y": 1},
                    "pressure": 1.1,
                }
            ]
        )
    with pytest.raises(ValueError, match="unsupported fields"):
        await service.runtime_input_send(
            [
                {
                    "type": "screen_touch",
                    "index": 0,
                    "position": {"x": 1, "y": 1},
                    "pressed": True,
                    "device": 1,
                }
            ]
        )
    with pytest.raises(ValueError, match="action"):
        await service.runtime_audio_stream_player_2d_control("/Main/Sound", "resume")
    with pytest.raises(ValueError, match="requires position_seconds"):
        await service.runtime_audio_stream_player_2d_control("/Main/Sound", "seek")
    with pytest.raises(ValueError, match="only accepted"):
        await service.runtime_audio_stream_player_2d_control(
            "/Main/Sound", "stop", position_seconds=1.0
        )
    with pytest.raises(ValueError, match="between 0 and 3600"):
        await service.runtime_audio_stream_player_2d_control(
            "/Main/Sound", "play", position_seconds=3601.0
        )
    with pytest.raises(ValueError, match="request_id"):
        await service.runtime_audio_stream_player_2d_control_result_get("")
    with pytest.raises(ValueError, match="duration_seconds"):
        await service.runtime_performance_sample_request(0.01)
    with pytest.raises(ValueError, match="request_id"):
        await service.runtime_performance_sample_result_get("")
    with pytest.raises(ValueError, match="requires a screenshot"):
        await service.runtime_test_run(
            screenshot_assertions=[{"kind": "dimensions", "width": 1, "height": 1}]
        )


@pytest.mark.asyncio
async def test_runtime_screenshot_assert_reports_pending_without_decoding() -> None:
    class PendingScreenshotBridge(FakeBridge):
        async def call(
            self,
            command: str,
            params: dict[str, Any] | None = None,
            session_id: str | None = None,
        ) -> dict[str, Any]:
            self.calls.append((command, params or {}, session_id))
            assert command == "runtime_screenshot_get"
            return {"status": "pending"}

    bridge = PendingScreenshotBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.runtime_screenshot_assert(
        "screenshot-123",
        [{"kind": "dimensions", "width": 1, "height": 1}],
        session_id="project@a1b2",
    )

    assert result == {
        "request_id": "screenshot-123",
        "status": "pending",
        "passed": None,
        "assertions": [],
    }
    assert bridge.calls == [
        ("runtime_screenshot_get", {"request_id": "screenshot-123"}, "project@a1b2")
    ]


class RuntimeTestBridge(FakeBridge):
    def __init__(self) -> None:
        super().__init__()
        self.stopped = False

    async def call(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((command, params or {}, session_id))
        if command == "editor_run":
            return {"requested": True, "requested_scene": "res://runtime_smoke.tscn"}
        if command == "editor_get_state":
            return {"play_state": "stopped" if self.stopped else "playing"}
        if command == "runtime_get_state":
            return {"connected": True}
        if command == "runtime_screenshot_request":
            return {"request_id": "screenshot-123", "status": "pending"}
        if command == "runtime_screenshot_get":
            return {
                "status": "ready",
                "result": {
                    "ok": True,
                    "mime_type": "image/png",
                    "width": 1,
                    "height": 1,
                    "byte_size": 1,
                },
            }
        if command == "editor_stop":
            self.stopped = True
            return {"requested": True, "was_playing": True}
        raise AssertionError(f"Unexpected runtime test command: {command}")


@pytest.mark.asyncio
async def test_runtime_test_run_orchestrates_bounded_launch_and_cleanup() -> None:
    bridge = RuntimeTestBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.runtime_test_run(
        mode="custom",
        scene_file="res://runtime_smoke.tscn",
        settle_seconds=0.0,
        timeout_seconds=3.0,
        session_id="project@a1b2",
    )

    assert result["status"] == "passed"
    assert result["passed"] is True
    assert result["cleanup"]["editor_state"]["play_state"] == "stopped"
    assert [call[0] for call in bridge.calls] == [
        "editor_run",
        "editor_get_state",
        "runtime_get_state",
        "editor_stop",
        "editor_get_state",
    ]


@pytest.mark.asyncio
async def test_runtime_test_run_preserves_full_image_assertion_wire_form() -> None:
    bridge = RuntimeTestBridge()
    service = GodotService(SessionRegistry(), bridge)
    assertions = [
        {
            "kind": "color_presence",
            "color": {"r": 1, "g": 2, "b": 3},
            "min_pixels": 1,
        }
    ]

    async def runtime_screenshot_assert(
        request_id: str,
        raw_assertions: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        assert request_id == "screenshot-123"
        assert raw_assertions == assertions
        assert session_id == "project@a1b2"
        return {"status": "ready", "passed": True, "assertions": []}

    service.runtime_screenshot_assert = runtime_screenshot_assert  # type: ignore[method-assign]
    result = await service.runtime_test_run(
        mode="custom",
        scene_file="res://runtime_smoke.tscn",
        settle_seconds=0.0,
        screenshot={"format": "png", "max_width": 1, "max_height": 1},
        screenshot_assertions=assertions,
        timeout_seconds=3.0,
        session_id="project@a1b2",
    )

    assert result["status"] == "passed"
    assert result["screenshot_assertions"]["passed"] is True


@pytest.mark.asyncio
async def test_hierarchy_rejects_unbounded_page() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="limit"):
        await service.scene_get_hierarchy(limit=1001)


@pytest.mark.asyncio
async def test_class_2d_describe_forwards_a_bounded_reflection_request() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.class_2d_describe(
        " Button ",
        section=" SIGNALS ",
        offset=4,
        limit=20,
        session_id="project@a1b2",
    )

    assert result == {"command": "class_2d_describe"}
    assert bridge.calls == [
        (
            "class_2d_describe",
            {"type": "Button", "section": "signals", "offset": 4, "limit": 20},
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_class_2d_describe_rejects_invalid_filters() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="type"):
        await service.class_2d_describe(" ")
    with pytest.raises(ValueError, match="section"):
        await service.class_2d_describe("Button", section="all")
    with pytest.raises(ValueError, match="offset"):
        await service.class_2d_describe("Button", offset=-1)
    with pytest.raises(ValueError, match="limit"):
        await service.class_2d_describe("Button", limit=501)


@pytest.mark.asyncio
async def test_class_2d_coverage_forwards_a_bounded_audit_request() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.class_2d_coverage(
        query="Audio",
        scope=" RESOURCE ",
        offset=4,
        limit=20,
        session_id="project@a1b2",
    )

    assert result == {"command": "class_2d_coverage"}
    assert bridge.calls == [
        (
            "class_2d_coverage",
            {"query": "Audio", "scope": "resource", "offset": 4, "limit": 20},
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_class_2d_coverage_rejects_invalid_filters() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="query"):
        await service.class_2d_coverage(query="x" * 257)
    with pytest.raises(ValueError, match="scope"):
        await service.class_2d_coverage(scope="scene")
    with pytest.raises(ValueError, match="offset"):
        await service.class_2d_coverage(offset=-1)
    with pytest.raises(ValueError, match="limit"):
        await service.class_2d_coverage(limit=501)


@pytest.mark.asyncio
async def test_class_2d_coverage_snapshot_collects_all_pages() -> None:
    bridge = CoverageBridge(
        [
            _coverage_page(
                [_coverage_entry("Button", semantic_tools=["button_2d_get"])],
                has_more=True,
                total=2,
            ),
            _coverage_page([_coverage_entry("Theme", kind="resource")], total=2),
        ]
    )
    service = GodotService(SessionRegistry(), bridge)

    result = await service.class_2d_coverage_snapshot(session_id="project@a1b2")

    assert result == {
        "snapshot_version": 1,
        "audit_version": 1,
        "engine": {"major": 4, "minor": 7, "patch": 0, "status": "stable"},
        "entries": [
            _coverage_entry("Button", semantic_tools=["button_2d_get"]),
            _coverage_entry("Theme", kind="resource"),
        ],
        "total": 2,
        "summary": {
            "node": 1,
            "resource": 1,
            "semantic": 1,
            "generic": 1,
            "semantic_smoke": 1,
        },
    }
    assert bridge.calls == [
        (
            "class_2d_coverage",
            {"query": "", "scope": "all", "offset": 0, "limit": 500},
            "project@a1b2",
        ),
        (
            "class_2d_coverage",
            {"query": "", "scope": "all", "offset": 1, "limit": 500},
            "project@a1b2",
        ),
    ]


@pytest.mark.asyncio
async def test_class_2d_coverage_diff_reports_additions_removals_and_breaking_changes() -> None:
    baseline = {
        "snapshot_version": 1,
        "audit_version": 1,
        "engine": {"major": 4, "minor": 7, "patch": 0, "status": "stable"},
        "entries": [
            _coverage_entry("Button", semantic_tools=["button_2d_get", "button_2d_set"]),
            _coverage_entry("RemovedControl"),
        ],
        "total": 2,
    }
    bridge = CoverageBridge(
        [
            _coverage_page(
                [
                    _coverage_entry("AddedControl"),
                    _coverage_entry("Button", semantic_tools=["button_2d_get"]),
                ],
                total=2,
            )
        ]
    )
    service = GodotService(SessionRegistry(), bridge)

    result = await service.class_2d_coverage_diff(baseline, session_id="project@a1b2")

    assert [entry["name"] for entry in result["added"]] == ["AddedControl"]
    assert [entry["name"] for entry in result["removed"]] == ["RemovedControl"]
    assert result["changed"] == [
        {
            "name": "Button",
            "changes": {
                "semantic_tools": {
                    "before": ["button_2d_get", "button_2d_set"],
                    "after": ["button_2d_get"],
                }
            },
        }
    ]
    assert result["breaking_changes"] == {
        "removed": ["RemovedControl"],
        "changed": [
            {
                "name": "Button",
                "reasons": ["semantic_tool_removed:button_2d_set"],
            }
        ],
    }
    assert result["summary"] == {"added": 1, "removed": 1, "changed": 1, "breaking": 2}


@pytest.mark.asyncio
async def test_class_2d_coverage_diff_rejects_incomplete_baselines() -> None:
    bridge = CoverageBridge([])
    service = GodotService(SessionRegistry(), bridge)

    with pytest.raises(ValueError, match="baseline.total"):
        await service.class_2d_coverage_diff(
            {
                "snapshot_version": 1,
                "audit_version": 1,
                "engine": {"major": 4, "minor": 7, "patch": 0, "status": "stable"},
                "entries": [],
                "total": 1,
            }
        )
    assert bridge.calls == []


@pytest.mark.asyncio
async def test_node_create_forwards_scene_guard_and_session() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.node_create(
        type_name="Button",
        name="ConfirmButton",
        parent_path="/Main/UI",
        script_path="res://scripts/confirm_button.gd",
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
                "script_path": "res://scripts/confirm_button.gd",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_node_script_tools_forward_scene_guard_and_validate_paths() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    await service.node_script_bind(
        path="/Main/Player",
        script_path="res://scripts/player.gd",
        replace_existing=True,
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.node_script_clear(
        path="/Main/Player",
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "node_script_bind",
            {
                "path": "/Main/Player",
                "script_path": "res://scripts/player.gd",
                "replace_existing": True,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        ("node_script_clear", {"path": "/Main/Player", "scene_file": "res://main.tscn"}, None),
    ]

    with pytest.raises(ValueError, match="res://"):
        await service.node_script_bind("/Main/Player", "../player.gd")
    with pytest.raises(ValueError, match="replace_existing"):
        await service.node_script_bind("/Main/Player", "res://scripts/player.gd", 1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_node_instance_scene_forwards_project_scene_and_rejects_invalid_paths() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.node_instance_scene(
        scene_path="res://scenes/player.tscn",
        name="AgentPlayer",
        parent_path="/Main/Actors",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )

    assert result == {"command": "node_instance_scene"}
    assert bridge.calls == [
        (
            "node_instance_scene",
            {
                "scene_path": "res://scenes/player.tscn",
                "name": "AgentPlayer",
                "parent_path": "/Main/Actors",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        )
    ]
    with pytest.raises(ValueError, match="scene_path"):
        await service.node_instance_scene("../player.tscn")
    with pytest.raises(ValueError, match="scene_path"):
        await service.node_instance_scene("res://../player.tscn")


@pytest.mark.asyncio
async def test_packed_scene_instance_tools_forward_scene_guards_and_validate_paths() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    inspected = await service.packed_scene_instance_get(
        "/Main/PlayerVisual",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    enabled = await service.packed_scene_instance_editable_children_enable(
        "/Main/PlayerVisual",
        scene_file="res://main.tscn",
    )

    assert inspected == {"command": "packed_scene_instance_get"}
    assert enabled == {"command": "packed_scene_instance_editable_children_enable"}
    assert bridge.calls == [
        (
            "packed_scene_instance_get",
            {"path": "/Main/PlayerVisual", "scene_file": "res://main.tscn"},
            "project@a1b2",
        ),
        (
            "packed_scene_instance_editable_children_enable",
            {"path": "/Main/PlayerVisual", "scene_file": "res://main.tscn"},
            None,
        ),
    ]
    with pytest.raises(ValueError, match="path"):
        await service.packed_scene_instance_get("")
    with pytest.raises(ValueError, match="path"):
        await service.packed_scene_instance_editable_children_enable("")


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
async def test_draw_2d_tools_forward_semantic_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    scene_file = "res://main.tscn"
    sprite_path = "/Main/Hero"
    line_path = "/Main/Trail"
    polygon_path = "/Main/Ground"
    sprite_properties = {
        "texture_path": "res://art/hero.png",
        "hframes": 4,
        "vframes": 2,
        "frame_coords": {"x": 2, "y": 1},
        "offset": {"x": 8.0, "y": -4.0},
    }
    line_properties = {
        "points": [{"x": 0.0, "y": 0.0}, {"x": 32.0, "y": 16.0}],
        "width": 3.0,
        "default_color": {"r": 1.0, "g": 0.4, "b": 0.1, "a": 1.0},
        "joint_mode": "round",
    }
    polygon_properties = {
        "polygon": [
            {"x": 0.0, "y": 0.0},
            {"x": 64.0, "y": 0.0},
            {"x": 32.0, "y": 32.0},
        ],
        "uv": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 0.5, "y": 1.0}],
        "texture_path": "res://art/ground.png",
        "texture_scale": {"x": 1.0, "y": 1.0},
    }

    await service.sprite_2d_get(sprite_path, session_id="project@a1b2", scene_file=scene_file)
    await service.line_2d_get(line_path, scene_file=scene_file)
    await service.polygon_2d_get(polygon_path, scene_file=scene_file)
    await service.sprite_2d_set(sprite_path, sprite_properties, scene_file=scene_file)
    await service.line_2d_set(line_path, line_properties, scene_file=scene_file)
    await service.polygon_2d_set(polygon_path, polygon_properties, scene_file=scene_file)

    assert bridge.calls == [
        ("sprite_2d_get", {"path": sprite_path, "scene_file": scene_file}, "project@a1b2"),
        ("line_2d_get", {"path": line_path, "scene_file": scene_file}, None),
        ("polygon_2d_get", {"path": polygon_path, "scene_file": scene_file}, None),
        (
            "sprite_2d_set",
            {"path": sprite_path, "properties": sprite_properties, "scene_file": scene_file},
            None,
        ),
        (
            "line_2d_set",
            {"path": line_path, "properties": line_properties, "scene_file": scene_file},
            None,
        ),
        (
            "polygon_2d_set",
            {"path": polygon_path, "properties": polygon_properties, "scene_file": scene_file},
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_draw_2d_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="non-empty"):
        await service.sprite_2d_set("/Main/Hero", {})
    with pytest.raises(ValueError, match="unsupported Sprite2D"):
        await service.sprite_2d_set("/Main/Hero", {"texture": "res://art/hero.png"})
    with pytest.raises(ValueError, match="frame and frame_coords"):
        await service.sprite_2d_set("/Main/Hero", {"frame": 1, "frame_coords": {"x": 0, "y": 0}})
    with pytest.raises(ValueError, match="hframes"):
        await service.sprite_2d_set("/Main/Hero", {"hframes": 1.5})
    with pytest.raises(ValueError, match="texture_path"):
        await service.sprite_2d_set("/Main/Hero", {"texture_path": "user://hero.png"})
    with pytest.raises(ValueError, match="closed Line2D"):
        await service.line_2d_set(
            "/Main/Trail",
            {"closed": True, "points": [{"x": 0.0, "y": 0.0}, {"x": 4.0, "y": 0.0}]},
        )
    with pytest.raises(ValueError, match="joint_mode"):
        await service.line_2d_set("/Main/Trail", {"joint_mode": "miter"})
    with pytest.raises(ValueError, match="polygon must be empty"):
        await service.polygon_2d_set(
            "/Main/Ground", {"polygon": [{"x": 0.0, "y": 0.0}, {"x": 4.0, "y": 0.0}]}
        )
    with pytest.raises(ValueError, match="texture_scale"):
        await service.polygon_2d_set("/Main/Ground", {"texture_scale": {"x": 0.0, "y": 1.0}})
    with pytest.raises(ValueError, match="vertex_colors"):
        await service.polygon_2d_set(
            "/Main/Ground",
            {
                "polygon": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 4.0, "y": 0.0},
                    {"x": 0.0, "y": 4.0},
                ],
                "vertex_colors": [{"r": 1.0, "g": 1.0, "b": 1.0}],
            },
        )


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

    await service.scene_create(
        scene_path="res://scenes/agent_ui.tscn",
        root_type="Control",
        root_name="AgentUI",
        session_id="project@a1b2",
    )
    await service.scene_open("res://scenes/main.tscn", session_id="project@a1b2")
    await service.scene_undo(scene_file="res://main.tscn")
    await service.scene_redo(scene_file="res://main.tscn")
    await service.scene_save(scene_file="res://main.tscn")

    assert bridge.calls == [
        (
            "scene_create",
            {
                "scene_path": "res://scenes/agent_ui.tscn",
                "root_type": "Control",
                "root_name": "AgentUI",
            },
            "project@a1b2",
        ),
        ("scene_open", {"scene_path": "res://scenes/main.tscn"}, "project@a1b2"),
        ("scene_undo", {"scene_file": "res://main.tscn"}, None),
        ("scene_redo", {"scene_file": "res://main.tscn"}, None),
        ("scene_save", {"scene_file": "res://main.tscn"}, None),
    ]


@pytest.mark.asyncio
async def test_scene_create_and_open_reject_invalid_client_parameters() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match=".tscn"):
        await service.scene_create("res://scenes/agent_ui.scn")
    with pytest.raises(ValueError, match="res://"):
        await service.scene_create("../agent_ui.tscn")
    with pytest.raises(ValueError, match="root_type"):
        await service.scene_create("res://scenes/agent_ui.tscn", root_type=" ")
    with pytest.raises(ValueError, match=".tscn or .scn"):
        await service.scene_open("res://assets/icon.svg")
    with pytest.raises(ValueError, match="res://"):
        await service.scene_open("user://save.tscn")


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
async def test_animation_method_track_upsert_forwards_strict_safe_payload() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    keys = [
        {"time": 0.0, "method": "show"},
        {"time": 0.15, "method": "hide", "args": []},
    ]

    result = await service.animation_method_track_upsert(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        target_path="/Main/UI/StartButton",
        keys=keys,
        enabled=False,
        library="ui",
        session_id="project@a1b2",
        scene_file="res://main.tscn",
    )

    assert result == {"command": "animation_method_track_upsert"}
    assert bridge.calls == [
        (
            "animation_method_track_upsert",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "target_path": "/Main/UI/StartButton",
                "keys": keys,
                "enabled": False,
                "library": "ui",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        )
    ]
    with pytest.raises(ValueError, match="method"):
        await service.animation_method_track_upsert(
            "/Main/ButtonAnimations",
            "button_hover",
            "/Main/UI/StartButton",
            keys=[{"time": 0.0, "method": ""}],
        )
    with pytest.raises(ValueError, match="args"):
        await service.animation_method_track_upsert(
            "/Main/ButtonAnimations",
            "button_hover",
            "/Main/UI/StartButton",
            keys=[{"time": 0.0, "method": "show", "args": object()}],
        )
    with pytest.raises(ValueError, match="duplicate"):
        await service.animation_method_track_upsert(
            "/Main/ButtonAnimations",
            "button_hover",
            "/Main/UI/StartButton",
            keys=[
                {"time": 0.0, "method": "show"},
                {"time": 0.0, "method": "hide"},
            ],
        )


@pytest.mark.asyncio
async def test_animation_nested_track_upsert_forwards_strict_payload() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    keys = [
        {"time": 0.0, "animation": "ui/button_pulse"},
        {"time": 0.15, "animation": "[stop]"},
    ]

    result = await service.animation_nested_track_upsert(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        target_path="/Main/ChildAnimations",
        keys=keys,
        enabled=False,
        library="ui",
        session_id="project@a1b2",
        scene_file="res://main.tscn",
    )

    assert result == {"command": "animation_nested_track_upsert"}
    assert bridge.calls == [
        (
            "animation_nested_track_upsert",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "target_path": "/Main/ChildAnimations",
                "keys": keys,
                "enabled": False,
                "library": "ui",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        )
    ]
    with pytest.raises(ValueError, match="nested animation"):
        await service.animation_nested_track_upsert(
            "/Main/ButtonAnimations",
            "button_hover",
            "/Main/ChildAnimations",
            keys=[{"time": 0.0, "animation": ""}],
        )
    with pytest.raises(ValueError, match="only time and animation"):
        await service.animation_nested_track_upsert(
            "/Main/ButtonAnimations",
            "button_hover",
            "/Main/ChildAnimations",
            keys=[{"time": 0.0, "animation": "pulse", "unexpected": True}],
        )
    with pytest.raises(ValueError, match="duplicate"):
        await service.animation_nested_track_upsert(
            "/Main/ButtonAnimations",
            "button_hover",
            "/Main/ChildAnimations",
            keys=[
                {"time": 0.0, "animation": "pulse"},
                {"time": 0.0, "animation": "[stop]"},
            ],
        )


@pytest.mark.asyncio
async def test_animation_audio_track_upsert_forwards_strict_payload() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    keys = [
        {
            "time": 0.0,
            "stream_path": "res://audio/click.tres",
            "start_offset": 0.05,
            "end_offset": 0.1,
        }
    ]

    await service.animation_audio_track_upsert(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        target_path="/Main/ClickSound",
        keys=keys,
        enabled=False,
        use_blend=False,
        library="ui",
        session_id="project@a1b2",
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "animation_audio_track_upsert",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "target_path": "/Main/ClickSound",
                "keys": keys,
                "enabled": False,
                "use_blend": False,
                "library": "ui",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_animation_audio_track_upsert_rejects_unsafe_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="stream_path"):
        await service.animation_audio_track_upsert(
            "/Main/ButtonAnimations",
            "hover",
            "/Main/ClickSound",
            keys=[{"time": 0.0, "stream_path": ""}],
        )
    with pytest.raises(ValueError, match="only time"):
        await service.animation_audio_track_upsert(
            "/Main/ButtonAnimations",
            "hover",
            "/Main/ClickSound",
            keys=[{"time": 0.0, "stream_path": "res://audio/click.tres", "value": 1}],
        )
    with pytest.raises(ValueError, match="start_offset"):
        await service.animation_audio_track_upsert(
            "/Main/ButtonAnimations",
            "hover",
            "/Main/ClickSound",
            keys=[
                {
                    "time": 0.0,
                    "stream_path": "res://audio/click.tres",
                    "start_offset": -0.1,
                }
            ],
        )


@pytest.mark.asyncio
async def test_animation_bezier_track_upsert_forwards_strict_payload() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    keys = [
        {
            "time": 0.0,
            "value": 1.0,
            "in_handle": {"x": -0.1, "y": 0.0},
            "out_handle": {"x": 0.1, "y": 0.2},
        },
        {"time": 0.2, "value": 0.0},
    ]

    await service.animation_bezier_track_upsert(
        player_path="/Main/ButtonAnimations",
        animation="button_hover",
        target_path="/Main/UI/StartButton",
        property="modulate:a",
        keys=keys,
        enabled=False,
        library="ui",
        session_id="project@a1b2",
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "animation_bezier_track_upsert",
            {
                "player_path": "/Main/ButtonAnimations",
                "animation": "button_hover",
                "target_path": "/Main/UI/StartButton",
                "property": "modulate:a",
                "keys": keys,
                "enabled": False,
                "library": "ui",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_animation_bezier_track_upsert_rejects_unsafe_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="property"):
        await service.animation_bezier_track_upsert(
            "/Main/ButtonAnimations",
            "hover",
            "/Main/UI/StartButton",
            "modulate:a:invalid",
            keys=[{"time": 0.0, "value": 1.0}],
        )
    with pytest.raises(ValueError, match="only time"):
        await service.animation_bezier_track_upsert(
            "/Main/ButtonAnimations",
            "hover",
            "/Main/UI/StartButton",
            "modulate:a",
            keys=[{"time": 0.0, "value": 1.0, "transition": 0.5}],
        )
    with pytest.raises(ValueError, match="in_handle.x"):
        await service.animation_bezier_track_upsert(
            "/Main/ButtonAnimations",
            "hover",
            "/Main/UI/StartButton",
            "modulate:a",
            keys=[
                {
                    "time": 0.0,
                    "value": 1.0,
                    "in_handle": {"x": 0.1, "y": 0.0},
                }
            ],
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
        await service.control_theme_item_clear("/Main/UI/Root", "color", "Button", "bad/name")


@pytest.mark.asyncio
async def test_collision_shape_and_layer_tools_forward_safe_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    rectangle = {"size": {"x": 96.0, "y": 32.0}}

    await service.collision_shape_get(
        "/Main/Wall/Collider", scene_file="res://main.tscn", session_id="project@a1b2"
    )
    await service.collision_object_get_layers("/Main/Wall", scene_file="res://main.tscn")
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
    await service.physics_body_2d_set("/Main/Player", body_properties, scene_file="res://main.tscn")
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
        await service.shape_cast_2d_set("/Main/PlayerShapeCast", shape_properties={"radius": 12.0})
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
        await service.navigation_2d_set("/Main/NavigationRegion", {"enter_cost": float("inf")})


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
        await service.navigation_polygon_geometry_set("/Main/NavigationRegion", [], [[0, 1, 2]])
    with pytest.raises(ValueError, match="outline"):
        await service.navigation_polygon_outline_set(
            "/Main/NavigationRegion", [{"x": 0.0, "y": 0.0}]
        )
    with pytest.raises(ValueError, match="index"):
        await service.navigation_polygon_outline_remove("/Main/NavigationRegion", True)


@pytest.mark.asyncio
async def test_navigation_polygon_bake_tools_forward_and_validate_requests() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    settings = {
        "agent_radius": 6.0,
        "cell_size": 2.0,
        "border_size": 8.0,
        "baking_rect": {
            "position": {"x": -16.0, "y": -8.0},
            "size": {"x": 256.0, "y": 128.0},
        },
        "baking_rect_offset": {"x": 4.0, "y": 2.0},
        "sample_partition_type": "triangulate",
        "parsed_geometry_type": "static_colliders",
        "parsed_collision_layers": [2, 5],
    }

    await service.navigation_polygon_bake_request(
        "/Main/NavigationRegion",
        source_root_path="/Main/Geometry",
        settings=settings,
        session_id="project@a1b2",
        scene_file="res://main.tscn",
    )
    await service.navigation_polygon_bake_result_get(
        "navigation-bake-123", session_id="project@a1b2"
    )

    assert bridge.calls == [
        (
            "navigation_polygon_bake_request",
            {
                "path": "/Main/NavigationRegion",
                "source_root_path": "/Main/Geometry",
                "settings": settings,
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "navigation_polygon_bake_result_get",
            {"request_id": "navigation-bake-123"},
            "project@a1b2",
        ),
    ]

    with pytest.raises(ValueError, match="source_root_path"):
        await service.navigation_polygon_bake_request(
            "/Main/NavigationRegion", source_root_path=True  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="cell_size"):
        await service.navigation_polygon_bake_request(
            "/Main/NavigationRegion", settings={"cell_size": 0.0}
        )
    with pytest.raises(ValueError, match="baking_rect size"):
        await service.navigation_polygon_bake_request(
            "/Main/NavigationRegion",
            settings={
                "baking_rect": {
                    "position": {"x": 0.0, "y": 0.0},
                    "size": {"x": -1.0, "y": 32.0},
                }
            },
        )
    with pytest.raises(ValueError, match="sample_partition_type"):
        await service.navigation_polygon_bake_request(
            "/Main/NavigationRegion", settings={"sample_partition_type": "bad"}
        )
    with pytest.raises(ValueError, match="parsed_collision_layers"):
        await service.navigation_polygon_bake_request(
            "/Main/NavigationRegion", settings={"parsed_collision_layers": [2, 2]}
        )


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
        await service.parallax_2d_set("/Main/Background", {"repeat_size": {"x": -1.0, "y": 1.0}})
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
    await service.path_2d_curve_point_insert(path, inserted_point, index=1, scene_file=scene_file)
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
        await service.path_2d_curve_point_insert("/Main/PatrolPath", {"in": {"x": 0.0, "y": 0.0}})
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

    await service.skeleton_2d_get(skeleton_path, session_id="project@a1b2", scene_file=scene_file)
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

    await service.audio_stream_player_2d_get(path, session_id="project@a1b2", scene_file=scene_file)
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
        await service.cpu_particles_2d_set(path, {"emission_rect_extents": {"x": -1.0, "y": 2.0}})
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
    await service.canvas_item_shader_uniforms_set(
        path,
        {"amount": 0.75, "tint": {"r": 1.0, "g": 0.5, "b": 0.0, "a": 1.0}},
        scene_file=scene_file,
    )
    await service.canvas_item_shader_uniforms_clear(path, ["amount", "tint"], scene_file=scene_file)
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
            "canvas_item_shader_uniforms_set",
            {
                "path": path,
                "values": {
                    "amount": 0.75,
                    "tint": {"r": 1.0, "g": 0.5, "b": 0.0, "a": 1.0},
                },
                "scene_file": scene_file,
            },
            None,
        ),
        (
            "canvas_item_shader_uniforms_clear",
            {"path": path, "names": ["amount", "tint"], "scene_file": scene_file},
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
    with pytest.raises(ValueError, match="values"):
        await service.canvas_item_shader_uniforms_set(path, {})
    with pytest.raises(ValueError, match="non-null"):
        await service.canvas_item_shader_uniforms_set(path, {"amount": None})
    with pytest.raises(ValueError, match="identifiers"):
        await service.canvas_item_shader_uniforms_set(path, {"bad-name": 1.0})
    with pytest.raises(ValueError, match="duplicate"):
        await service.canvas_item_shader_uniforms_clear(path, ["amount", "amount"])


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
async def test_tileset_layer_lifecycle_and_terrain_paint_tools_forward_payloads() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    path = "/Main/Tiles"
    scene_file = "res://main.tscn"
    layer_properties = {"layers": [2], "masks": [1, 3], "priority": 0.5}
    terrain_coords = [{"x": 3, "y": 4}, {"x": 4, "y": 4}]

    await service.tile_set_layer_set(
        path,
        "physics",
        0,
        layer_properties,
        scene_file=scene_file,
        session_id="project@a1b2",
    )
    await service.tile_set_layer_remove(
        path,
        "custom_data",
        1,
        scene_file=scene_file,
        session_id="project@a1b2",
    )
    await service.tile_set_terrain_set_remove(
        path,
        0,
        scene_file=scene_file,
        session_id="project@a1b2",
    )
    await service.tile_set_terrain_remove(
        path,
        1,
        2,
        scene_file=scene_file,
        session_id="project@a1b2",
    )
    await service.tile_map_layer_terrain_paint(
        path,
        terrain_coords,
        terrain_set=0,
        terrain=0,
        strategy="path",
        ignore_empty_terrains=False,
        scene_file=scene_file,
        session_id="project@a1b2",
    )

    assert bridge.calls == [
        (
            "tile_set_layer_set",
            {
                "path": path,
                "kind": "physics",
                "index": 0,
                "properties": layer_properties,
                "scene_file": scene_file,
            },
            "project@a1b2",
        ),
        (
            "tile_set_layer_remove",
            {"path": path, "kind": "custom_data", "index": 1, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "tile_set_terrain_set_remove",
            {"path": path, "terrain_set": 0, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "tile_set_terrain_remove",
            {"path": path, "terrain_set": 1, "terrain": 2, "scene_file": scene_file},
            "project@a1b2",
        ),
        (
            "tile_map_layer_terrain_paint",
            {
                "path": path,
                "coords": terrain_coords,
                "terrain_set": 0,
                "terrain": 0,
                "strategy": "path",
                "ignore_empty_terrains": False,
                "scene_file": scene_file,
            },
            "project@a1b2",
        ),
    ]


@pytest.mark.asyncio
async def test_tileset_layer_lifecycle_and_terrain_paint_tools_reject_invalid_payloads() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="kind"):
        await service.tile_set_layer_set("/Main/Tiles", "render", 0, {"layers": [1]})
    with pytest.raises(ValueError, match="properties"):
        await service.tile_set_layer_set("/Main/Tiles", "physics", 0, {})
    with pytest.raises(ValueError, match="priority"):
        await service.tile_set_layer_set(
            "/Main/Tiles", "physics", 0, {"priority": -0.1}
        )
    with pytest.raises(ValueError, match="index"):
        await service.tile_set_layer_remove("/Main/Tiles", "navigation", -1)
    with pytest.raises(ValueError, match="terrain"):
        await service.tile_set_terrain_remove("/Main/Tiles", 0, -1)
    with pytest.raises(ValueError, match="coords"):
        await service.tile_map_layer_terrain_paint("/Main/Tiles", [], terrain_set=0, terrain=0)
    with pytest.raises(ValueError, match="strategy"):
        await service.tile_map_layer_terrain_paint(
            "/Main/Tiles", [{"x": 0, "y": 0}], terrain_set=0, terrain=0, strategy="area"
        )
    with pytest.raises(ValueError, match="ignore_empty_terrains"):
        await service.tile_map_layer_terrain_paint(
            "/Main/Tiles",
            [{"x": 0, "y": 0}],
            terrain_set=0,
            terrain=0,
            ignore_empty_terrains=1,
        )


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
