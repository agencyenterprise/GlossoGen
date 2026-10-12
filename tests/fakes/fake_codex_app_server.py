"""A stand-in for ``codex app-server`` that plays a scripted agent over the same protocol.

Launched the way the Codex harness launches the real binary, with ``app-server``
and the restriction flags appended, which it records. It reads its script from
the JSON file named by ``FAKE_CODEX_SCRIPT``: a list of steps, one per model
response, each ``{"say": text}``, ``{"call": {"tool", "arguments"}}``,
``{"parallel": [call, ...]}``, ``{"exit": true}``, ``{"malformed": true}``,
which sends a notification the schema does not allow, or ``{"say": text,
"then_garbage": true}``, which ends the turn and then writes a line that is not
JSON. Once the script is spent
it idles the way scripted seats do: a ``read_notifications`` call, then a reply.

The order of what it sends follows a live session: a response's raw function
call items, then the request to run its first call, then the response's usage,
then the calls one at a time, each followed by its completed item. A call the
client answers with an error completes as a failed call carrying the error's
message.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_ENV = "FAKE_CODEX_SCRIPT"
RECORD_FILE_NAME = "fake_codex_record.json"
USAGE = {
    "totalTokens": 120,
    "inputTokens": 100,
    "cachedInputTokens": 40,
    "cacheWriteInputTokens": 0,
    "outputTokens": 20,
    "reasoningOutputTokens": 5,
}
IDLE_CYCLE: list[dict[str, Any]] = [
    {"call": {"tool": "read_notifications", "arguments": {}}},
    {"say": "idle"},
]


class FakeAppServer:
    """One fake server process: its script position and the requests it has in flight."""

    def __init__(self, script: list[dict[str, Any]], codex_home: Path) -> None:
        self._script = script
        self._codex_home = codex_home
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._thread_id = ""
        self._turns = 0
        self._interrupted = False
        self._record: dict[str, Any] = {"argv": sys.argv[1:], "requests": []}

    def send(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.send(payload={"method": method, "params": params})

    async def call_client(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[self._next_id] = future
        self.send(payload={"id": self._next_id, "method": method, "params": params})
        return await future

    def next_step(self) -> dict[str, Any]:
        if not self._script:
            self._script.extend(IDLE_CYCLE)
        return self._script.pop(0)

    def answer(self, message: dict[str, Any]) -> None:
        method = message["method"]
        params = message.get("params", {})
        self._record["requests"].append({"method": method, "params": params})
        (self._codex_home / RECORD_FILE_NAME).write_text(json.dumps(self._record))
        result: dict[str, Any] = {}
        if method == "thread/start":
            self._thread_id = "fake-thread"
            result = {"thread": {"id": self._thread_id}}
        elif method == "turn/start":
            self._turns += 1
            turn_id = f"turn-{self._turns}"
            result = {"turn": {"id": turn_id}}
            asyncio.get_running_loop().create_task(self.play_turn(turn_id=turn_id))
        elif method == "turn/interrupt":
            self._interrupted = True
        self.send(payload={"id": message["id"], "result": result})

    def raw_item(self, turn_id: str, item: dict[str, Any]) -> None:
        self.notify(
            method="rawResponseItem/completed",
            params={"threadId": self._thread_id, "turnId": turn_id, "item": item},
        )

    def response_completed(self, turn_id: str) -> None:
        self.notify(
            method="rawResponse/completed",
            params={"threadId": self._thread_id, "turnId": turn_id, "usage": USAGE},
        )

    def turn_completed(self, turn_id: str, status: str) -> None:
        self.notify(
            method="turn/completed",
            params={"threadId": self._thread_id, "turn": {"id": turn_id, "status": status}},
        )
        rollout = self._codex_home / "sessions" / f"rollout-{self._thread_id}.jsonl"
        rollout.parent.mkdir(parents=True, exist_ok=True)
        with rollout.open("a") as handle:
            handle.write(json.dumps({"turn": turn_id, "status": status}) + "\n")

    async def play_turn(self, turn_id: str) -> None:
        responses = 0
        while True:
            step = self.next_step()
            responses += 1
            if step.get("exit"):
                os._exit(3)
            if step.get("malformed"):
                self.notify(method="rawResponse/completed", params={"threadId": self._thread_id})
                return
            if "say" in step:
                self.raw_item(
                    turn_id=turn_id,
                    item={
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": step["say"]}],
                    },
                )
                self.response_completed(turn_id=turn_id)
                self.turn_completed(turn_id=turn_id, status="completed")
                if step.get("then_garbage"):
                    sys.stdout.write("this is not json\n")
                    sys.stdout.flush()
                return
            if "parallel" in step:
                calls: list[dict[str, Any]] = step["parallel"]
            else:
                calls = [step["call"]]
            call_ids = [f"call-{turn_id}-{responses}-{index}" for index in range(len(calls))]
            for call_id, call in zip(call_ids, calls, strict=True):
                self.raw_item(
                    turn_id=turn_id,
                    item={
                        "type": "function_call",
                        "name": call["tool"],
                        "arguments": json.dumps(call["arguments"]),
                        "call_id": call_id,
                    },
                )
            for index, (call_id, call) in enumerate(zip(call_ids, calls, strict=True)):
                request = asyncio.ensure_future(
                    self.call_client(
                        method="item/tool/call",
                        params={
                            "threadId": self._thread_id,
                            "turnId": turn_id,
                            "callId": call_id,
                            "tool": call["tool"],
                            "arguments": call["arguments"],
                        },
                    )
                )
                if index == 0:
                    await asyncio.sleep(0)
                    self.response_completed(turn_id=turn_id)
                result = await request
                self.notify(
                    method="item/completed",
                    params={
                        "threadId": self._thread_id,
                        "turnId": turn_id,
                        "item": {
                            "type": "dynamicToolCall",
                            "id": call_id,
                            "tool": call["tool"],
                            "success": result["success"],
                            "contentItems": result["contentItems"],
                        },
                    },
                )
            if self._interrupted:
                self._interrupted = False
                self.turn_completed(turn_id=turn_id, status="interrupted")
                return

    def settle(self, message: dict[str, Any]) -> None:
        future = self._pending.pop(message["id"])
        if "error" in message:
            future.set_result(
                {
                    "success": False,
                    "contentItems": [{"type": "inputText", "text": message["error"]["message"]}],
                }
            )
            return
        future.set_result(message["result"])


async def serve() -> None:
    codex_home = Path(os.environ["CODEX_HOME"])
    script = json.loads(Path(os.environ[SCRIPT_ENV]).read_text())
    server = FakeAppServer(script=script, codex_home=codex_home)
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=1 << 24)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while line := await reader.readline():
        message = json.loads(line)
        if "method" in message and "id" in message:
            server.answer(message=message)
        elif "method" not in message:
            server.settle(message=message)


if __name__ == "__main__":
    asyncio.run(serve())
