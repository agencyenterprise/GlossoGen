"""The ``serve`` subcommand: the web server, and the web UI beside it on request."""

import argparse
import logging
import os
import signal
from types import FrameType

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
            "published one; pass a full reference to pin the UI to a release, "
            "e.g. ghcr.io/agencyenterprise/glossogen-frontend:v0.17.16."
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
    # Installed before the container starts, so a `kill` during its readiness
    # wait reaches the cleanup in `start_frontend_container` too.
    previous_sigterm_handler = signal.signal(signal.SIGTERM, _exit_on_sigterm)
    try:
        container = start_frontend_container(
            api_port=args.port,
            ui_port=args.ui_port,
            image=_resolve_ui_image(requested_image=args.ui_image),
        )
    except BaseException:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)
        raise
    logger.info("Web UI at %s", container.url)
    try:
        _run_uvicorn(port=args.port)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)
        stop_frontend_container(container_id=container.container_id)


def _exit_on_sigterm(
    signum: int,
    frame: FrameType | None,  # noqa: ARG001 — signature-required
) -> None:
    """Turn SIGTERM into ``SystemExit`` so the UI container is removed on the way out.

    uvicorn shuts down on SIGTERM, then raises the signal again under the handler
    that was installed before it started. Under the default handler that ends the
    process before the ``finally`` that removes the container, so a ``kill`` left
    the container running and holding the UI port.
    """
    raise SystemExit(128 + signum)


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
    """Return the frontend image to run, defaulting to the latest published one."""
    if requested_image is not None:
        return requested_image
    return default_frontend_image()
