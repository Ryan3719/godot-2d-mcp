"""Bounded, dependency-free assertions for runtime PNG screenshots."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Any

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 1_000_000
MAX_DIMENSION = 1024
MAX_PIXELS = MAX_DIMENSION * MAX_DIMENSION
MAX_ASSERTIONS = 32


class ScreenshotAssertionError(ValueError):
    """Raised when supplied screenshot data or assertion definitions are unsafe."""


@dataclass(frozen=True, slots=True)
class DecodedPng:
    width: int
    height: int
    channels: int
    pixels: bytes

    def pixel_at(self, x: int, y: int) -> dict[str, int]:
        offset = (y * self.width + x) * self.channels
        color = {
            "r": self.pixels[offset],
            "g": self.pixels[offset + 1],
            "b": self.pixels[offset + 2],
        }
        color["a"] = self.pixels[offset + 3] if self.channels == 4 else 255
        return color


def validate_screenshot_assertions(assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a small assertion language before any image data is decoded."""
    if not isinstance(assertions, list) or not 1 <= len(assertions) <= MAX_ASSERTIONS:
        raise ScreenshotAssertionError(
            f"assertions must contain between 1 and {MAX_ASSERTIONS} items"
        )

    normalized: list[dict[str, Any]] = []
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            raise ScreenshotAssertionError(f"assertions[{index}] must be an object")
        kind = assertion.get("kind")
        if kind == "dimensions":
            _reject_unknown_fields(assertion, {"kind", "width", "height"}, index)
            normalized.append(
                {
                    "kind": kind,
                    "width": _positive_int(assertion.get("width"), f"assertions[{index}].width"),
                    "height": _positive_int(assertion.get("height"), f"assertions[{index}].height"),
                }
            )
            continue
        if kind == "pixel":
            _reject_unknown_fields(assertion, {"kind", "x", "y", "color", "tolerance"}, index)
            normalized.append(
                {
                    "kind": kind,
                    "x": _non_negative_int(assertion.get("x"), f"assertions[{index}].x"),
                    "y": _non_negative_int(assertion.get("y"), f"assertions[{index}].y"),
                    "color": _color(assertion.get("color"), f"assertions[{index}].color"),
                    "tolerance": _tolerance(assertion.get("tolerance", 0), index),
                }
            )
            continue
        if kind == "region_mean":
            _reject_unknown_fields(
                assertion,
                {"kind", "x", "y", "width", "height", "color", "tolerance"},
                index,
            )
            normalized.append(
                {
                    "kind": kind,
                    **_region(assertion, index, required=True),
                    "color": _color(assertion.get("color"), f"assertions[{index}].color"),
                    "tolerance": _tolerance(assertion.get("tolerance", 0), index),
                }
            )
            continue
        if kind == "color_presence":
            _reject_unknown_fields(
                assertion,
                {
                    "kind",
                    "x",
                    "y",
                    "width",
                    "height",
                    "color",
                    "tolerance",
                    "min_pixels",
                },
                index,
            )
            normalized.append(
                {
                    "kind": kind,
                    **_region(assertion, index, required=False),
                    "color": _color(assertion.get("color"), f"assertions[{index}].color"),
                    "tolerance": _tolerance(assertion.get("tolerance", 0), index),
                    "min_pixels": _positive_int(
                        assertion.get("min_pixels", 1), f"assertions[{index}].min_pixels"
                    ),
                }
            )
            continue
        raise ScreenshotAssertionError(
            f"assertions[{index}].kind must be dimensions, pixel, region_mean, or color_presence"
        )
    return normalized


def assert_png_screenshot(encoded: bytes, assertions: list[dict[str, Any]]) -> dict[str, Any]:
    """Decode one bounded RGB/RGBA PNG and evaluate normalized assertions against it."""
    image = decode_png(encoded)
    results = [
        _evaluate_assertion(image, assertion, index) for index, assertion in enumerate(assertions)
    ]
    return {
        "passed": all(result["passed"] for result in results),
        "image": {"width": image.width, "height": image.height, "channels": image.channels},
        "assertions": results,
    }


def decode_png(encoded: bytes) -> DecodedPng:
    """Decode only the non-interlaced 8-bit RGB/RGBA PNG form emitted by Godot."""
    if not isinstance(encoded, bytes) or not PNG_SIGNATURE == encoded[: len(PNG_SIGNATURE)]:
        raise ScreenshotAssertionError("Screenshot is not a PNG file")
    if len(encoded) > MAX_PNG_BYTES:
        raise ScreenshotAssertionError(f"PNG exceeds the {MAX_PNG_BYTES}-byte limit")

    offset = len(PNG_SIGNATURE)
    width = height = channels = 0
    idat_chunks: list[bytes] = []
    saw_ihdr = False
    saw_iend = False
    while offset < len(encoded):
        if offset + 12 > len(encoded):
            raise ScreenshotAssertionError("PNG chunk is truncated")
        length = struct.unpack_from(">I", encoded, offset)[0]
        chunk_start = offset + 8
        chunk_end = chunk_start + length
        if chunk_end + 4 > len(encoded):
            raise ScreenshotAssertionError("PNG chunk length exceeds the file")
        chunk_type = encoded[offset + 4 : offset + 8]
        chunk_data = encoded[chunk_start:chunk_end]
        expected_crc = struct.unpack_from(">I", encoded, chunk_end)[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ScreenshotAssertionError("PNG chunk checksum is invalid")
        offset = chunk_end + 4

        if chunk_type == b"IHDR":
            if saw_ihdr or length != 13:
                raise ScreenshotAssertionError("PNG IHDR is invalid")
            unpacked_header = struct.unpack(">IIBBBBB", chunk_data)
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = unpacked_header
            if not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION:
                raise ScreenshotAssertionError("PNG dimensions exceed runtime screenshot bounds")
            if bit_depth != 8 or color_type not in {2, 6}:
                raise ScreenshotAssertionError(
                    "Only 8-bit RGB or RGBA PNG screenshots are supported"
                )
            if compression != 0 or filter_method != 0 or interlace != 0:
                raise ScreenshotAssertionError(
                    "PNG compression, filter method, or interlacing is unsupported"
                )
            channels = 3 if color_type == 2 else 4
            saw_ihdr = True
        elif chunk_type == b"IDAT":
            if not saw_ihdr or saw_iend:
                raise ScreenshotAssertionError("PNG IDAT order is invalid")
            idat_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            if length != 0 or saw_iend:
                raise ScreenshotAssertionError("PNG IEND is invalid")
            saw_iend = True
            if offset != len(encoded):
                raise ScreenshotAssertionError("PNG contains trailing data")
            break

    if not saw_ihdr or not saw_iend or not idat_chunks:
        raise ScreenshotAssertionError("PNG must contain IHDR, IDAT, and IEND chunks")
    row_bytes = width * channels
    expected_length = height * (row_bytes + 1)
    compressed = b"".join(idat_chunks)
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, expected_length + 1)
    if len(raw) > expected_length or decoder.unconsumed_tail:
        raise ScreenshotAssertionError("PNG decompressed data exceeds expected image bounds")
    raw += decoder.flush(expected_length + 1 - len(raw))
    if not decoder.eof or decoder.unused_data or len(raw) != expected_length:
        raise ScreenshotAssertionError("PNG decompressed data length is invalid")

    pixels = bytearray(width * height * channels)
    previous = bytearray(row_bytes)
    source_offset = 0
    destination_offset = 0
    for _ in range(height):
        filter_type = raw[source_offset]
        source_offset += 1
        filtered = raw[source_offset : source_offset + row_bytes]
        source_offset += row_bytes
        current = bytearray(row_bytes)
        for column in range(row_bytes):
            left = current[column - channels] if column >= channels else 0
            up = previous[column]
            up_left = previous[column - channels] if column >= channels else 0
            value = filtered[column]
            if filter_type == 0:
                current[column] = value
            elif filter_type == 1:
                current[column] = (value + left) & 0xFF
            elif filter_type == 2:
                current[column] = (value + up) & 0xFF
            elif filter_type == 3:
                current[column] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                current[column] = (value + _paeth(left, up, up_left)) & 0xFF
            else:
                raise ScreenshotAssertionError("PNG scanline uses an unknown filter")
        pixels[destination_offset : destination_offset + row_bytes] = current
        destination_offset += row_bytes
        previous = current
    return DecodedPng(width=width, height=height, channels=channels, pixels=bytes(pixels))


def _evaluate_assertion(image: DecodedPng, assertion: dict[str, Any], index: int) -> dict[str, Any]:
    kind = assertion["kind"]
    if kind == "dimensions":
        actual = {"width": image.width, "height": image.height}
        expected = {"width": assertion["width"], "height": assertion["height"]}
        return {
            "index": index,
            "kind": kind,
            "passed": actual == expected,
            "expected": expected,
            "actual": actual,
        }
    if kind == "pixel":
        expected_color = assertion["color"]
        actual: dict[str, Any]
        if not _in_image(image, assertion["x"], assertion["y"]):
            actual = {"error": "coordinate is outside the screenshot"}
            return _assertion_result(
                index, kind, False, expected_color, actual, assertion["tolerance"]
            )
        actual = image.pixel_at(assertion["x"], assertion["y"])
        return _assertion_result(
            index,
            kind,
            _color_matches(actual, expected_color, assertion["tolerance"]),
            expected_color,
            actual,
            assertion["tolerance"],
        )

    region = _resolve_region(image, assertion)
    expected_color = assertion["color"]
    if region is None:
        return _assertion_result(
            index,
            kind,
            False,
            expected_color,
            {"error": "region is outside the screenshot"},
            assertion["tolerance"],
        )
    x, y, width, height = region
    if kind == "region_mean":
        totals = {channel: 0 for channel in ("r", "g", "b", "a")}
        for row in range(y, y + height):
            for column in range(x, x + width):
                color = image.pixel_at(column, row)
                for channel in totals:
                    totals[channel] += color[channel]
        pixel_count = width * height
        actual = {channel: totals[channel] / pixel_count for channel in expected_color}
        return _assertion_result(
            index,
            kind,
            _color_matches(actual, expected_color, assertion["tolerance"]),
            expected_color,
            actual,
            assertion["tolerance"],
            region,
        )

    matching = 0
    for row in range(y, y + height):
        for column in range(x, x + width):
            if _color_matches(image.pixel_at(column, row), expected_color, assertion["tolerance"]):
                matching += 1
    actual = {"matching_pixels": matching, "region": _region_dict(region)}
    return {
        "index": index,
        "kind": kind,
        "passed": matching >= assertion["min_pixels"],
        "expected": {
            "color": expected_color,
            "tolerance": assertion["tolerance"],
            "min_pixels": assertion["min_pixels"],
        },
        "actual": actual,
    }


def _assertion_result(
    index: int,
    kind: str,
    passed: bool,
    expected: dict[str, int],
    actual: dict[str, Any],
    tolerance: int,
    region: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "index": index,
        "kind": kind,
        "passed": passed,
        "expected": {"color": expected, "tolerance": tolerance},
        "actual": actual,
    }
    if region is not None:
        result["region"] = _region_dict(region)
    return result


def _resolve_region(
    image: DecodedPng, assertion: dict[str, Any]
) -> tuple[int, int, int, int] | None:
    if assertion.get("x") is None:
        return (0, 0, image.width, image.height)
    x = assertion["x"]
    y = assertion["y"]
    width = assertion["width"]
    height = assertion["height"]
    if x + width > image.width or y + height > image.height:
        return None
    return (x, y, width, height)


def _region_dict(region: tuple[int, int, int, int]) -> dict[str, int]:
    x, y, width, height = region
    return {"x": x, "y": y, "width": width, "height": height}


def _color_matches(
    actual: dict[str, float | int], expected: dict[str, int], tolerance: int
) -> bool:
    return all(abs(float(actual[channel]) - expected[channel]) <= tolerance for channel in expected)


def _in_image(image: DecodedPng, x: int, y: int) -> bool:
    return x < image.width and y < image.height


def _reject_unknown_fields(assertion: dict[str, Any], allowed: set[str], index: int) -> None:
    unknown = sorted(set(assertion) - allowed)
    if unknown:
        raise ScreenshotAssertionError(
            f"assertions[{index}] contains unsupported fields: {', '.join(unknown)}"
        )


def _region(assertion: dict[str, Any], index: int, required: bool) -> dict[str, int | None]:
    fields = ("x", "y", "width", "height")
    supplied = [field for field in fields if field in assertion]
    if not supplied and not required:
        return {field: None for field in fields}
    if len(supplied) != len(fields):
        raise ScreenshotAssertionError(
            f"assertions[{index}] region requires x, y, width, and height together"
        )
    return {
        "x": _non_negative_int(assertion["x"], f"assertions[{index}].x"),
        "y": _non_negative_int(assertion["y"], f"assertions[{index}].y"),
        "width": _positive_int(assertion["width"], f"assertions[{index}].width"),
        "height": _positive_int(assertion["height"], f"assertions[{index}].height"),
    }


def _color(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or not {"r", "g", "b"}.issubset(value):
        raise ScreenshotAssertionError(f"{label} requires r, g, and b channels")
    unknown = sorted(set(value) - {"r", "g", "b", "a"})
    if unknown:
        raise ScreenshotAssertionError(
            f"{label} contains unsupported channels: {', '.join(unknown)}"
        )
    color: dict[str, int] = {}
    for channel, channel_value in value.items():
        if (
            isinstance(channel_value, bool)
            or not isinstance(channel_value, int)
            or not 0 <= channel_value <= 255
        ):
            raise ScreenshotAssertionError(
                f"{label}.{channel} must be an integer between 0 and 255"
            )
        color[channel] = channel_value
    return color


def _tolerance(value: Any, index: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ScreenshotAssertionError(
            f"assertions[{index}].tolerance must be an integer between 0 and 255"
        )
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_DIMENSION:
        raise ScreenshotAssertionError(f"{label} must be an integer between 1 and {MAX_DIMENSION}")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < MAX_DIMENSION:
        raise ScreenshotAssertionError(
            f"{label} must be an integer between 0 and {MAX_DIMENSION - 1}"
        )
    return value


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
