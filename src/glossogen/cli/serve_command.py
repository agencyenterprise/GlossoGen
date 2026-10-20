"""The ``serve`` subcommand: the web server, and the web UI beside it on request."""

import argparse
import logging
import os

import uvicorn

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.frontend_container import (
    allow_ui_origin,
    default_frontend_image,
    start_frontend_container,
    stop_frontend_container,
)

logger = logging.getLogger(__name__)


def add_serve_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``serve`` subcommand and its flags."""
    serve_parser = subparsers.add_parser("serve", help="Start the web server")
    serve_parser.add_argument(
        "--runs-dir", type=str, required=True, help="Root directory containing simulation runs"
    )
    serve_parser.add_argument("--port", type=int, required=True, help="Port to listen on")
    serve_parser.add_argument(
        "--ui-port",
        type=int,
        default=None,
        help=(
            "Also start the web UI on this port, from the published frontend "
            "image, wired to this server. Requires Docker. Omit to run the "
            "backend alone."
        ),
    )
    serve_parser.add_argument(
        "--ui-image",
        type=str,
        default=None,
        help=(
            "Frontend image to run with --ui-port. Defaults to the latest "
            "published one; pass a version tag to pin the UI to a release."
        ),
    )


def handle_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI web server, and the web UI when ``--ui-port`` asks for it."""
    logger.info("Starting web server on port %d, runs dir: %s", args.port, args.runs_dir)
    os.environ["GLOSSOGEN_RUNS_DIR"] = args.runs_dir
    if args.ui_port is None:
        _run_uvicorn(port=args.port)
        return

    allow_ui_origin(ui_port=args.ui_port)
    container = start_frontend_container(
        api_port=args.port,
        ui_port=args.ui_port,
        image=_resolve_ui_image(requested_image=args.ui_image),
    )
    logger.info("Web UI at %s", container.url)
    try:
        _run_uvicorn(port=args.port)
    finally:
        stop_frontend_container(container_id=container.container_id)


def _run_uvicorn(port: int) -> None:
    """Serve the FastAPI app until interrupted."""
    uvicorn.run(
        app="glossogen.server.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


def _resolve_ui_image(requested_image: str | None) -> str:
    """Return the frontend image to run, defaulting to the installed version's."""
    if requested_image is not None:
        return requested_image
    return default_frontend_image()
