"""A stand-in for a partner model outside platoon: an OpenAI-compatible chat endpoint that plays
signal_game by rule.

It answers ``POST /v1/chat/completions`` with the scripted player's next tool call, read from the
last message of the request, so that ``glossogen run`` can send one seat to it while platoon serves
the other.
"""

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aiohttp import web

HOST = "127.0.0.1"
CALLS_KEY = web.AppKey("calls", list[str])
DIRECTIONS = ("up", "down", "left", "right")


class PartnerStub:
    """A running stub: its ``/v1`` URL and the tool names it answered with, in order."""

    def __init__(self, *, url: str, calls: list[str]) -> None:
        self.url = url
        self.calls = calls


def next_tool_call(*, messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """The scripted player's next tool call and its arguments, or None once the game is done."""
    last = messages[-1]
    content = str(last["content"])
    if last["role"] != "tool":
        return "read_notifications", {"wait_for": "any"}
    if '"type":"done"' in content:
        return None
    if '"briefings":["ROUND' in content:
        return "move", {
            "directions": [DIRECTIONS[len(messages) % 4]],
            "reasoning": "A partner move.",
        }
    if "You finished round" in content:
        return "read_notifications", {"wait_for": "next_round"}
    return "end_round", {"reasoning": "The partner ends."}


def completion_message(*, call: tuple[str, dict[str, Any]] | None) -> dict[str, Any]:
    """The assistant message that answers with ``call``, or with text when the game is done."""
    if call is None:
        return {"role": "assistant", "content": "The game is over."}
    name, arguments = call
    tool_call = {
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }
    return {"role": "assistant", "content": None, "tool_calls": [tool_call]}


async def chat_completions(request: web.Request) -> web.Response:
    """Answer one chat completion request with the next tool call."""
    body = await request.json()
    call = next_tool_call(messages=body["messages"])
    if call is None:
        request.app[CALLS_KEY].append("done")
        finish = "stop"
    else:
        request.app[CALLS_KEY].append(call[0])
        finish = "tool_calls"
    return web.json_response(
        {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [
                {"index": 0, "message": completion_message(call=call), "finish_reason": finish}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )


@asynccontextmanager
async def partner_stub() -> AsyncIterator[PartnerStub]:
    """Serve the stub on a free local port while the block runs."""
    app = web.Application()
    calls: list[str] = []
    app[CALLS_KEY] = calls
    app.router.add_post("/v1/chat/completions", chat_completions)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=HOST, port=0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        yield PartnerStub(url=f"http://{HOST}:{port}/v1", calls=calls)
    finally:
        await runner.cleanup()
