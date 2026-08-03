"""Command-line entry point for the Godot 2D MCP server."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from godot_2d_mcp.server import create_application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Godot 2D MCP server")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ws-host", default="127.0.0.1")
    parser.add_argument("--ws-port", type=int, default=9500)
    parser.add_argument("--command-timeout", type=float, default=10.0)
    parser.add_argument("--log-level", default="WARNING")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = create_application(
        ws_host=args.ws_host,
        ws_port=args.ws_port,
        command_timeout=args.command_timeout,
    )
    if args.transport == "http":
        app.mcp.run(transport="http", host=args.host, port=args.port)
    else:
        app.mcp.run(transport="stdio")
