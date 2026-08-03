from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from godot_2d_mcp.protocol import HandshakeMessage, find_non_finite_float


def test_find_non_finite_float_reports_nested_path() -> None:
    value = {"nodes": [{"position": {"x": 1.0, "y": math.inf}}]}

    assert find_non_finite_float(value) == "params.nodes[0].position.y"


def test_handshake_rejects_unbounded_session_id() -> None:
    with pytest.raises(ValidationError):
        HandshakeMessage(
            session_id="x" * 129,
            plugin_version="0.1.0",
            godot_version="4.7.stable",
            project_name="test",
            project_path="/tmp/test",
        )
