"""A stand-in for an agent CLI that connects to a seat's tool endpoint over MCP.

Run as a process the way the ``external_cli`` runner runs Claude Code or Codex:
it connects to the URL it is given with the bearer token, lists the tools, and
plays a script read from the file named by ``FAKE_CLI_SCRIPT``. Each step is
``{"call": {"tool", "arguments"}}``, ``{"say": text}``, which ends the turn,
``{"exit": code}``, which ends the process with that code and no result, or
``{"garbage": true}``, which ends the turn with a line that is not JSON. The
steps the turn consumed are removed from the file, so a later turn carries on
where the last one stopped. Once the script is spent the process idles the way
a model would: ``read_notifications`` until the wake says the run is over,
then it ends the turn.

It prints one JSON line at the end: the session id it was given, the tool
names it saw, the usage it claims, and whether the turn failed. ``FakeAgentCli``
is the ``AgentCli`` that starts it.
"""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from glossogen.models.event_base import TokenUsage
from glossogen.runners.external_cli.cli_protocol import CliSeat, CliTurn, CliTurnResult

SCRIPT_ENV = "FAKE_CLI_SCRIPT"
TOKEN_ENV = "FAKE_CLI_TOKEN"
STATE_DIR_ENV = "FAKE_CLI_STATE_DIR"
TURN_USAGE = {"input_tokens": 100, "output_tokens": 10}
DONE_TYPE = "done"
IDLE_CALL_LIMIT = 50
IDLE_STEP: dict[str, Any] = {"call": {"tool": "read_notifications", "arguments": {}}}


class FakeAgentCli:
    """Starts the stand-in CLI for a seat, as a harness's ``AgentCli`` does."""

    def __init__(self, script_path: Path) -> None:
        self._script_path = script_path
        self.prepared: list[CliSeat] = []

    def prepare(self, seat: CliSeat) -> None:
        self.prepared.append(seat)

    def command(self, seat: CliSeat, turn: CliTurn) -> list[str]:
        command = [sys.executable, __file__, "--url", seat.tool_url, "--prompt", turn.prompt]
        if turn.resume_session_id is None:
            command.extend(["--session-id", f"session-{seat.agent_id}"])
        else:
            command.extend(["--resume", turn.resume_session_id])
        return command

    def environment(self, seat: CliSeat) -> Mapping[str, str]:
        return {
            **os.environ,
            SCRIPT_ENV: str(self._script_path),
            TOKEN_ENV: seat.tool_token,
            STATE_DIR_ENV: str(seat.state_dir),
        }

    def transcripts_dir(self, seat: CliSeat) -> Path:
        return seat.state_dir / "fake_sessions"

    def parse_output(self, stdout: str) -> CliTurnResult:
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            raise ValueError("the fake CLI wrote no result")
        try:
            raw = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"the fake CLI's result is not JSON: {lines[-1]!r}") from exc
        return CliTurnResult(
            session_id=raw["session_id"],
            usage=TokenUsage(
                input_tokens=raw["usage"]["input_tokens"],
                output_tokens=raw["usage"]["output_tokens"],
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
            reported_cost_usd=None,
            is_error=raw["is_error"],
            error_text=raw["error_text"],
        )


def _take_steps(script_path: Path) -> list[dict[str, Any]]:
    raw = cast(list[Any], json.loads(script_path.read_text()))
    return [cast(dict[str, Any], step) for step in raw]


def _leave_steps(script_path: Path, steps: list[dict[str, Any]]) -> None:
    script_path.write_text(json.dumps(steps))


async def _play(url: str, token: str, session_id: str, script_path: Path) -> int:
    steps = _take_steps(script_path=script_path)
    tool_names: list[str] = []
    http_client = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=httpx2.Timeout(None)
    )
    async with (
        http_client,
        streamable_http_client(url, http_client=http_client) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()
        listed = await session.list_tools()
        tool_names = [tool.name for tool in listed.tools]
        idle_calls = 0
        step: dict[str, Any]
        while True:
            if steps:
                step = steps.pop(0)
                _leave_steps(script_path=script_path, steps=steps)
            else:
                idle_calls += 1
                if idle_calls > IDLE_CALL_LIMIT:
                    print(f"idled {IDLE_CALL_LIMIT} times without the run ending", file=sys.stderr)
                    return 2
                step = IDLE_STEP
            if "exit" in step:
                return int(cast(int, step["exit"]))
            if step.get("garbage"):
                print("this is not json")
                return 0
            if "say" in step:
                break
            call = cast(dict[str, Any], step["call"])
            tool_name = str(call["tool"])
            arguments = cast(dict[str, Any], call["arguments"])
            result = await session.call_tool(tool_name, arguments)
            text = "".join(getattr(part, "text", "") for part in result.content)
            if tool_name == "read_notifications" and not steps and _is_done(text=text):
                break
    transcript = (
        Path(os.environ[STATE_DIR_ENV]) / "fake_sessions" / "nested" / f"{session_id}.jsonl"
    )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    with transcript.open("a") as handle:
        handle.write(json.dumps({"tools": tool_names}) + "\n")
    print(
        json.dumps(
            {
                "session_id": session_id,
                "tools": tool_names,
                "usage": TURN_USAGE,
                "is_error": False,
                "error_text": "",
            }
        )
    )
    return 0


def _is_done(text: str) -> bool:
    try:
        delivered: object = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(delivered, dict):
        return False
    return cast(dict[str, Any], delivered).get("type") == DONE_TYPE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--resume")
    args = parser.parse_args()
    session_id = args.session_id if args.resume is None else args.resume
    return asyncio.run(
        _play(
            url=args.url,
            token=os.environ[TOKEN_ENV],
            session_id=session_id,
            script_path=Path(os.environ[SCRIPT_ENV]),
        )
    )


if __name__ == "__main__":
    sys.exit(main())
