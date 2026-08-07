from __future__ import annotations

import struct
import zlib

import pytest

from godot_2d_mcp.screenshot_assertions import (
    ScreenshotAssertionError,
    assert_png_screenshot,
    decode_png,
    validate_screenshot_assertions,
)


def _png(width: int, height: int, rows: list[bytes], filters: list[int] | None = None) -> bytes:
    filters = filters or [0] * height
    raw = bytearray()
    previous = bytes(width * 3)
    for row, filter_type in zip(rows, filters, strict=True):
        raw.append(filter_type)
        raw.extend(_filter_row(row, previous, 3, filter_type))
        previous = row
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(
        b"IDAT", zlib.compress(bytes(raw))
    ) + _chunk(b"IEND", b"")


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _filter_row(row: bytes, previous: bytes, channels: int, filter_type: int) -> bytes:
    filtered = bytearray()
    for index, value in enumerate(row):
        left = row[index - channels] if index >= channels else 0
        up = previous[index]
        up_left = previous[index - channels] if index >= channels else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = up
        elif filter_type == 3:
            predictor = (left + up) // 2
        else:
            predictor = _paeth(left, up, up_left)
        filtered.append((value - predictor) & 0xFF)
    return bytes(filtered)


def _paeth(left: int, up: int, up_left: int) -> int:
    prediction = left + up - up_left
    left_distance = abs(prediction - left)
    up_distance = abs(prediction - up)
    up_left_distance = abs(prediction - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


def test_decoder_supports_all_png_filters() -> None:
    rows = [
        bytes([10, 20, 30, 40, 50, 60]),
        bytes([70, 80, 90, 100, 110, 120]),
        bytes([130, 140, 150, 160, 170, 180]),
        bytes([190, 200, 210, 220, 230, 240]),
        bytes([1, 2, 3, 4, 5, 6]),
    ]

    decoded = decode_png(_png(2, 5, rows, filters=[0, 1, 2, 3, 4]))

    assert decoded.width == 2
    assert decoded.height == 5
    assert decoded.channels == 3
    assert decoded.pixel_at(1, 4) == {"r": 4, "g": 5, "b": 6, "a": 255}


def test_decoder_preserves_rgba_alpha() -> None:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    rgba_png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(
        b"IDAT", zlib.compress(b"\x00\x01\x02\x03\x04")
    ) + _chunk(b"IEND", b"")

    decoded = decode_png(rgba_png)

    assert decoded.channels == 4
    assert decoded.pixel_at(0, 0) == {"r": 1, "g": 2, "b": 3, "a": 4}


def test_png_assertions_evaluate_dimensions_pixels_regions_and_colors() -> None:
    screenshot = _png(
        2,
        2,
        [bytes([255, 0, 0, 0, 255, 0]), bytes([255, 0, 0, 0, 0, 255])],
    )
    assertions = validate_screenshot_assertions(
        [
            {"kind": "dimensions", "width": 2, "height": 2},
            {"kind": "pixel", "x": 0, "y": 0, "color": {"r": 255, "g": 0, "b": 0}},
            {
                "kind": "region_mean",
                "x": 0,
                "y": 0,
                "width": 2,
                "height": 2,
                "color": {"r": 127, "g": 63, "b": 63},
                "tolerance": 1,
            },
            {
                "kind": "color_presence",
                "color": {"r": 255, "g": 0, "b": 0},
                "min_pixels": 2,
            },
        ]
    )

    result = assert_png_screenshot(screenshot, assertions)

    assert result["passed"] is True
    assert [item["passed"] for item in result["assertions"]] == [True, True, True, True]


def test_png_assertions_return_a_normal_failure_for_non_matching_pixels() -> None:
    screenshot = _png(1, 1, [bytes([255, 0, 0])])
    assertions = validate_screenshot_assertions(
        [{"kind": "pixel", "x": 0, "y": 0, "color": {"r": 0, "g": 0, "b": 255}}]
    )

    result = assert_png_screenshot(screenshot, assertions)

    assert result["passed"] is False
    assert result["assertions"][0]["actual"] == {"r": 255, "g": 0, "b": 0, "a": 255}


def test_assertion_definitions_and_png_integrity_are_strict() -> None:
    with pytest.raises(ScreenshotAssertionError, match="requires r, g, and b"):
        validate_screenshot_assertions(
            [{"kind": "pixel", "x": 0, "y": 0, "color": {"r": 1, "g": 2}}]
        )
    with pytest.raises(ScreenshotAssertionError, match="unsupported fields"):
        validate_screenshot_assertions(
            [{"kind": "dimensions", "width": 1, "height": 1, "unexpected": True}]
        )

    png = bytearray(_png(1, 1, [bytes([0, 0, 0])]))
    png[-5] ^= 1
    with pytest.raises(ScreenshotAssertionError, match="checksum"):
        decode_png(bytes(png))
