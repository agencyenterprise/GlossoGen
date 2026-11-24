"""`glossogen serve` keeps `?token=` credentials out of uvicorn's access log.

The browser sends its session token as a query parameter on event-stream requests,
and uvicorn logs each request's path with its query string. The first test serves
one such request through each of uvicorn's HTTP protocols (production picks
httptools), configured with the keyword arguments `glossogen serve` passes to
`uvicorn.run`, and reads the access log line it prints. No socket is opened: the
request bytes go straight to the protocol.
"""

import argparse
import asyncio
import logging
from collections.abc import Iterator
from typing import Any, NamedTuple

import pytest
import uvicorn
from uvicorn.config import LOGGING_CONFIG, Config
from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol
from uvicorn.server import ServerState

from glossogen.cli import serve_command
from glossogen.cli.access_log_redaction import (
    REDACTED_VALUE,
    RedactQueryCredentials,
    redact_query_credentials,
)

_SECRET = "eyJhbGciOiJSUzI1NiJ9.session-claims.signature"
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class _RecordingTransport(asyncio.Transport):
    """Collects what the protocol writes, in place of a socket."""

    def __init__(self) -> None:
        super().__init__()
        self.written = bytearray()
        self.closed = False

    def get_extra_info(
        self, name: str, default: Any = None
    ) -> Any:  # noqa: ANN401 — asyncio's signature
        extra = {"sockname": ("127.0.0.1", 8000), "peername": ("127.0.0.1", 54321)}
        return extra.get(name, default)

    def write(self, data: bytes | bytearray | memoryview) -> None:
        self.written.extend(data)

    def close(self) -> None:
        self.closed = True

    def is_closing(self) -> bool:
        return self.closed

    def pause_reading(self) -> None:
        return None

    def resume_reading(self) -> None:
        return None


async def _ok_app(
    scope: dict[str, Any],  # noqa: ARG001 — ASGI signature
    receive: Any,  # noqa: ANN401, ARG001 — ASGI signature
    send: Any,  # noqa: ANN401 — ASGI signature
) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


class _SavedLogger(NamedTuple):
    logger: logging.Logger
    handlers: list[logging.Handler]
    level: int
    propagate: bool


@pytest.fixture
def restored_uvicorn_loggers() -> Iterator[None]:
    """Undo the logging config the test applies, so other tests see the loggers as before."""
    saved: list[_SavedLogger] = []
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        saved.append(
            _SavedLogger(
                logger=logger,
                handlers=list(logger.handlers),
                level=logger.level,
                propagate=logger.propagate,
            )
        )
    yield
    for entry in saved:
        entry.logger.handlers = entry.handlers
        for added in list(entry.logger.filters):
            if isinstance(added, RedactQueryCredentials):
                entry.logger.removeFilter(added)
        entry.logger.setLevel(entry.level)
        entry.logger.propagate = entry.propagate


def _serve_uvicorn_run_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Return the keyword arguments `glossogen serve` passes to `uvicorn.run`."""
    captured: dict[str, Any] = {}

    def fake_uvicorn_run(**kwargs: Any) -> None:  # noqa: ANN401 — uvicorn.run's kwargs
        captured.update(kwargs)

    monkeypatch.setattr(target=uvicorn, name="run", value=fake_uvicorn_run)
    monkeypatch.setenv("GLOSSOGEN_RUNS_DIR", "")
    serve_command.handle_serve(
        args=argparse.Namespace(runs_dir="runs", port=8000, ui_port=None, ui_image=None)
    )
    return captured


@pytest.mark.parametrize(argnames="protocol_class", argvalues=[H11Protocol, HttpToolsProtocol])
async def test_serve_access_log_omits_the_query_token(
    protocol_class: type[H11Protocol] | type[HttpToolsProtocol],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restored_uvicorn_loggers: None,  # noqa: ARG001 — fixture for its teardown
) -> None:
    run_kwargs = _serve_uvicorn_run_kwargs(monkeypatch=monkeypatch)
    config = Config(
        app=_ok_app,
        log_config=run_kwargs.get("log_config", LOGGING_CONFIG),
        lifespan="off",
    )
    protocol = protocol_class(config=config, server_state=ServerState(), app_state={})
    transport = _RecordingTransport()
    protocol.connection_made(transport=transport)

    protocol.data_received(
        data=(
            f"GET /api/g/lab/runs/veyru/1/events?token={_SECRET}&after=3 HTTP/1.1\r\n"
            "Host: localhost\r\n\r\n"
        ).encode()
    )
    for _ in range(100):
        if protocol.cycle.response_complete:
            break
        await asyncio.sleep(0)

    access_line = capsys.readouterr().out
    assert transport.written.startswith(b"HTTP/1.1 200")
    assert "/api/g/lab/runs/veyru/1/events?" in access_line
    assert _SECRET not in access_line
    assert f"token={REDACTED_VALUE}&after=3" in access_line


@pytest.mark.parametrize(
    argnames=("path", "expected"),
    argvalues=[
        ("/api/health", "/api/health"),
        ("/api/x?after=3", "/api/x?after=3"),
        (f"/api/x?token={_SECRET}", f"/api/x?token={REDACTED_VALUE}"),
        (f"/api/x?a=1&token={_SECRET}&b=2", f"/api/x?a=1&token={REDACTED_VALUE}&b=2"),
        (f"/api/x?%74oken={_SECRET}", f"/api/x?%74oken={REDACTED_VALUE}"),
        (
            f"/api/x?token={_SECRET}&token=again",
            f"/api/x?token={REDACTED_VALUE}&token={REDACTED_VALUE}",
        ),
        ("/api/x?tokens=kept&my_token=kept", "/api/x?tokens=kept&my_token=kept"),
        ("/api/x?token", "/api/x?token"),
    ],
)
def test_redact_query_credentials(path: str, expected: str) -> None:
    assert redact_query_credentials(path_with_query=path) == expected
