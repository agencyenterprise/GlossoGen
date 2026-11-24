"""The server keeps `?token=` credentials out of uvicorn's access log.

The browser sends its session token as a query parameter on event-stream requests,
and uvicorn logs each request's path with its query string. The first test does
what every way of starting the server does: it applies uvicorn's default logging
config, then imports the server app. It serves one such request through each of
uvicorn's HTTP protocols (production picks httptools) and reads the access log line
printed. No socket is opened: the request bytes go straight to the protocol.
"""

import asyncio
import importlib
import logging
from collections.abc import Iterator
from typing import Any, NamedTuple

import pytest
from uvicorn.config import LOGGING_CONFIG, Config
from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol
from uvicorn.server import ServerState

from glossogen.server.access_log_redaction import REDACTED_VALUE, redact_query_credentials

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
    """Undo the logging config the test applies, so other tests see the loggers as before.

    The redaction filter stays: the app attaches it once, when first imported.
    """
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
        entry.logger.setLevel(entry.level)
        entry.logger.propagate = entry.propagate


@pytest.mark.parametrize(argnames="protocol_class", argvalues=[H11Protocol, HttpToolsProtocol])
async def test_access_log_omits_the_query_token(
    protocol_class: type[H11Protocol] | type[HttpToolsProtocol],
    capsys: pytest.CaptureFixture[str],
    restored_uvicorn_loggers: None,  # noqa: ARG001 — fixture for its teardown
) -> None:
    config = Config(app=_ok_app, log_config=LOGGING_CONFIG, lifespan="off")
    importlib.import_module(name="glossogen.server.app")
    server_state = ServerState()
    protocol = protocol_class(config=config, server_state=server_state, app_state={})
    transport = _RecordingTransport()
    protocol.connection_made(transport=transport)

    protocol.data_received(
        data=(
            f"GET /api/g/lab/runs/veyru/1/events?token={_SECRET}&after=3 HTTP/1.1\r\n"
            "Host: localhost\r\n\r\n"
        ).encode()
    )
    await asyncio.gather(*server_state.tasks)

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
