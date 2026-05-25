"""Embedded mini-server that streams simulation events via SSE.

Started automatically by ``schmidt run``. Exposes a single SSE endpoint
that streams live events from the in-process EventBus. The ``schmidt serve``
process discovers this server via the ``stream.json`` manifest and proxies
its output to the frontend.
"""

# FastAPI route handlers below are registered via the ``@app.get(...)``
# decorator; pyright can't see the framework's runtime use of them.
# pyright: reportUnusedFunction=false

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import orjson
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from schmidt.event_bus import EventBus
from schmidt.port_allocator import find_free_port
from schmidt.server.response_models import HealthResponse, HealthStatus
from schmidt.stream_manifest import StreamManifest, delete_manifest, write_manifest

logger = logging.getLogger(__name__)


def _create_simulation_app(event_bus: EventBus) -> FastAPI:
    """Create a FastAPI app with a single SSE endpoint for simulation streaming."""
    app = FastAPI(title="Schmidt Simulation Stream")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.state.event_bus = event_bus

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Liveness check for the simulation server."""
        return HealthResponse(status=HealthStatus.OK)

    @app.get("/events")
    async def stream_events(
        request: Request,
    ) -> StreamingResponse:
        """Stream live simulation events as SSE from the in-process EventBus."""
        bus: EventBus = request.app.state.event_bus

        return StreamingResponse(
            content=_stream_bus_events(event_bus=bus),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


async def _stream_bus_events(
    event_bus: EventBus,
) -> AsyncGenerator[bytes, None]:
    """Stream live events from the EventBus as SSE frames."""
    bus_queue = event_bus.create_subscriber_queue()

    try:
        while True:
            event_dict = await bus_queue.get()
            yield _format_sse_frame(event_bus=event_bus, event_dict=event_dict)
            event_type = str(event_dict.get("event_type", ""))
            if event_type == "simulation_ended":
                return
    finally:
        event_bus.remove_subscriber_queue(queue=bus_queue)


def _format_sse_frame(event_bus: EventBus, event_dict: dict[str, object]) -> bytes:
    """Format a bus event dict as an SSE frame with a monotonic sequence ID."""
    event_type = str(event_dict.get("event_type", "unknown"))
    seq = event_bus.next_event_seq()
    data_bytes = orjson.dumps(event_dict)
    return f"id: {seq}\nevent: {event_type}\ndata: ".encode() + data_bytes + b"\n\n"


def _on_server_task_done(task: asyncio.Task[None]) -> None:
    """Log exceptions from the server task instead of silently swallowing them."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception("Simulation server task failed", exc_info=exc)


async def start_simulation_server(
    event_bus: EventBus,
    run_dir: Path,
    run_id: str,
) -> tuple[uvicorn.Server, int]:
    """Start the simulation's embedded streaming server.

    Binds to an ephemeral port, writes a stream manifest for discovery,
    and returns the server instance and assigned port. The server runs
    as an asyncio task in the caller's event loop.
    """
    port = find_free_port()
    app = _create_simulation_app(event_bus=event_bus)

    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config=config)

    manifest = StreamManifest(
        host="127.0.0.1",
        port=port,
        run_id=run_id,
        pid=os.getpid(),
    )
    write_manifest(run_dir=run_dir, manifest=manifest)

    task = asyncio.create_task(server.serve())
    task.add_done_callback(_on_server_task_done)

    # Give the server a moment to bind
    await asyncio.sleep(0.1)

    logger.info("Simulation server started on port %d for run %s", port, run_id)
    return server, port


async def stop_simulation_server(
    server: uvicorn.Server,
    run_dir: Path,
) -> None:
    """Stop the simulation server and clean up the stream manifest."""
    delete_manifest(run_dir=run_dir)
    server.should_exit = True
    # Give SSE clients time to receive the final event
    await asyncio.sleep(1)
    logger.info("Simulation server stopped")
