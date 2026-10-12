"""A JSON-RPC connection to one ``codex app-server`` process over stdio.

Messages are newline-delimited JSON objects. A message with a ``method`` and an
``id`` is a request from the server, one with a ``method`` and no ``id`` is a
notification, and one with an ``id`` and no ``method`` answers a request this
side sent.

Every server request is answered from its own task. A tool call can park for as
long as a round lasts, and the notifications that arrive meanwhile must still be
read, which is why the published Codex SDK, whose reader answers server requests
inline, is not used here.

Every server request gets an answer, an error when its handler raised. A message
that cannot be read or handled ends the connection the way the process exiting
does, so whoever waits on it is told rather than left waiting.
"""

import asyncio
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

STREAM_LIMIT_BYTES = 64 * 1024 * 1024
"""The largest single message read from the server."""
TERMINATE_GRACE_SECONDS = 10.0
"""How long ``close`` waits for the process to end before killing it."""
STDERR_TAIL_LINES = 20
"""How many of the server's last stderr lines an exit reports."""
METHOD_NOT_FOUND_CODE = -32601
INTERNAL_ERROR_CODE = -32603

ResultT = TypeVar("ResultT", bound=BaseModel)


class ServerNotification(NamedTuple):
    """A notification the server sent."""

    method: str
    params: dict[str, Any]


class AppServerExited(RuntimeError):
    """The app-server process ended while the connection was in use."""


ServerRequestHandler = Callable[[str, dict[str, Any]], Awaitable[BaseModel]]
"""Answers one server request, given its method and params, with the response body.
Raising ``ValueError`` answers it with a JSON-RPC error carrying the message; any
other exception answers it with an error naming the exception's type."""

NotificationHandler = Callable[[ServerNotification], None]
ExitHandler = Callable[[str], None]
"""Called once the connection has ended on its own, with the reason."""


class AppServerConnection:
    """One app-server process and the requests in flight to it."""

    def __init__(
        self,
        on_notification: NotificationHandler,
        on_server_request: ServerRequestHandler,
        on_exit: ExitHandler,
    ) -> None:
        self._on_notification = on_notification
        self._on_server_request = on_server_request
        self._on_exit = on_exit
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._ended_reason: str | None = None

    async def start(self, command: Sequence[str], env: Mapping[str, str], cwd: Path) -> None:
        """Launch the server and start reading what it sends."""
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(env),
            cwd=cwd,
            limit=STREAM_LIMIT_BYTES,
        )
        self._spawn(coroutine=self._read_messages())
        self._spawn(coroutine=self._drain_stderr())

    async def request(
        self, method: str, params: dict[str, Any], result_model: type[ResultT]
    ) -> ResultT:
        """Send a request and return its result parsed as ``result_model``.

        Raises ``AppServerExited`` once the connection has ended, since nothing
        would answer.
        """
        self._raise_if_ended()
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._write(payload={"id": request_id, "method": method, "params": params})
        result = await future
        return result_model.model_validate(result)

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification, which the server does not answer."""
        self._raise_if_ended()
        await self._write(payload={"method": method, "params": params})

    async def close(self) -> None:
        """End the process, killing it if it outlives the grace period, and stop reading."""
        process = self._process
        self._process = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=TERMINATE_GRACE_SECONDS)
            except TimeoutError:
                logger.exception("The codex app server ignored terminate; killing it")
                process.kill()
                await process.wait()
        for task in list(self._tasks):
            task.cancel()
        self._fail_pending(reason="the connection was closed")

    def _spawn(self, coroutine: Awaitable[None]) -> None:
        task: asyncio.Task[None] = asyncio.ensure_future(coro_or_future=coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _write(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise AppServerExited("the app server is not running")
        async with self._write_lock:
            process.stdin.write((json.dumps(payload) + "\n").encode())
            await process.stdin.drain()

    async def _read_messages(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                if not line.strip():
                    continue
                self._dispatch(message=json.loads(line))
        except Exception as error:
            logger.exception("Could not handle a message from the codex app server")
            reason = f"a message from the app server could not be handled: {error!r}"
        else:
            reason = await self._exit_reason(process=process)
        self._ended_reason = reason
        self._fail_pending(reason=reason)
        self._on_exit(reason)

    def _raise_if_ended(self) -> None:
        if self._ended_reason is not None:
            raise AppServerExited(self._ended_reason)

    async def _exit_reason(self, process: asyncio.subprocess.Process) -> str:
        """Why the server stopped: its exit code and the last lines it wrote to stderr."""
        return_code = await process.wait()
        reason = f"the app server exited with code {return_code}"
        if self._stderr_tail:
            reason = f"{reason}; its last stderr lines: " + " | ".join(self._stderr_tail)
        return reason

    def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method is not None and "id" in message:
            self._spawn(
                coroutine=self._answer(
                    request_id=message["id"], method=method, params=message.get("params", {})
                )
            )
        elif method is not None:
            self._on_notification(
                ServerNotification(method=method, params=message.get("params", {}))
            )
        else:
            self._settle(message=message)

    def _settle(self, message: dict[str, Any]) -> None:
        future = self._pending.pop(message["id"], None)
        if future is None or future.done():
            return
        if "error" in message:
            future.set_exception(RuntimeError(json.dumps(message["error"])))
        else:
            future.set_result(message.get("result", {}))

    async def _answer(self, request_id: object, method: str, params: dict[str, Any]) -> None:
        """Answer one server request; whatever happens, the server gets a reply if it can."""
        try:
            result = await self._on_server_request(method, params)
        except ValueError as error:
            logger.exception("Refused app-server request %s", method)
            payload: dict[str, Any] = {
                "id": request_id,
                "error": {"code": METHOD_NOT_FOUND_CODE, "message": str(error)},
            }
        except Exception as error:
            logger.exception("App-server request %s failed", method)
            payload = {
                "id": request_id,
                "error": {
                    "code": INTERNAL_ERROR_CODE,
                    "message": f"{method} failed: {type(error).__name__}",
                },
            }
        else:
            payload = {"id": request_id, "result": result.model_dump(mode="json", by_alias=True)}
        try:
            await self._write(payload=payload)
        except (AppServerExited, OSError):
            logger.exception("Could not answer app-server request %s", method)

    async def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while True:
            line = await process.stderr.readline()
            if not line:
                return
            text = line.decode(errors="replace").rstrip()
            if text:
                self._stderr_tail.append(text)
                logger.debug("codex app-server: %s", text)

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(AppServerExited(reason))
        self._pending.clear()
