"""How the Claude SDK adapter starts the CLI and translates a turn, against a stand-in client.

The SDK's client is replaced by one that records the options it was built with
and plays back a turn's messages, so the launcher, the options, the item
translation and the transcript copy run without a Claude Code process.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
)

from glossogen.runners.claude_agent_sdk import claude_sdk_seat_session  # noqa: E402
from glossogen.runners.claude_agent_sdk.claude_sdk_seat_session import (  # noqa: E402
    TOOL_NAME_PREFIX,
    TOOL_SERVER_NAME,
    TOOL_TIMEOUT_MILLISECONDS,
    ClaudeSdkSeatSession,
)
from glossogen.runners.claude_agent_sdk.cli_launcher import LAUNCHER_FILE_NAME  # noqa: E402
from glossogen.runners.harness_names import HARNESS_STATE_DIR_NAME  # noqa: E402
from glossogen.runners.session_harness.seat_session import (  # noqa: E402
    CycleEnded,
    ResponseCompleted,
    ResponseStarted,
    SeatOptions,
    SessionStarted,
    TextChunk,
)


class FakeClient:
    """Stands in for ``ClaudeSDKClient``: records its options and plays ``messages``."""

    built: list["FakeClient"] = []
    connect_error: Exception | None = None

    def __init__(self, options: ClaudeAgentOptions) -> None:
        self.options = options
        self.prompts: list[str] = []
        self.messages: list[Any] = []
        self.interrupted = False
        self.disconnected = False
        FakeClient.built.append(self)

    async def connect(self) -> None:
        if FakeClient.connect_error is not None:
            raise FakeClient.connect_error

    async def query(self, prompt: str) -> None:
        self.prompts.append(prompt)

    async def receive_response(self) -> AsyncIterator[Any]:
        for message in self.messages:
            yield message

    async def interrupt(self) -> None:
        self.interrupted = True

    async def disconnect(self) -> None:
        self.disconnected = True


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> type[FakeClient]:
    FakeClient.built = []
    FakeClient.connect_error = None
    monkeypatch.setattr(claude_sdk_seat_session, "ClaudeSDKClient", FakeClient)
    return FakeClient


def seat_options(seat_dir: Path, resume_session_id: str | None) -> SeatOptions:
    return SeatOptions(
        model="claude-sonnet-4-6",
        system_prompt="You observe.",
        tools=(),
        max_output_tokens=2048,
        seat_dir=seat_dir,
        resume_session_id=resume_session_id,
    )


async def test_the_cli_is_started_with_only_the_seats_tools_in_its_own_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_client: type[FakeClient]
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "a credential the seat must not use")
    seat_dir = tmp_path / "harness" / "field_observer"
    session = ClaudeSdkSeatSession()

    await session.connect(options=seat_options(seat_dir=seat_dir, resume_session_id="s-1"))

    options = fake_client.built[0].options
    state_dir = seat_dir / HARNESS_STATE_DIR_NAME
    assert options.model == "claude-sonnet-4-6"
    assert options.system_prompt == "You observe."
    assert options.tools == []
    assert options.allowed_tools == [f"{TOOL_NAME_PREFIX}*"]
    assert options.permission_mode == "dontAsk"
    assert list(cast(dict[str, Any], options.mcp_servers)) == [TOOL_SERVER_NAME]
    assert options.strict_mcp_config is True
    assert options.setting_sources == []
    assert options.cwd == state_dir / "workspace"
    assert options.thinking == {"type": "disabled"}
    assert options.include_partial_messages is True
    assert options.resume == "s-1"
    assert options.env == {
        "CLAUDE_CONFIG_DIR": str(state_dir / "claude_config"),
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "2048",
        "MCP_TOOL_TIMEOUT": str(TOOL_TIMEOUT_MILLISECONDS),
    }
    assert options.cli_path == state_dir / LAUNCHER_FILE_NAME
    launcher = Path(str(options.cli_path)).read_text()
    assert "-u CLAUDE_CODE_OAUTH_TOKEN" in launcher
    assert "-u CLAUDE_CONFIG_DIR" not in launcher
    await session.close()
    assert fake_client.built[0].disconnected


async def test_a_turn_is_sent_read_back_as_items_and_the_transcript_kept(
    tmp_path: Path, fake_client: type[FakeClient]
) -> None:
    seat_dir = tmp_path / "harness" / "field_observer"
    session = ClaudeSdkSeatSession()
    await session.connect(options=seat_options(seat_dir=seat_dir, resume_session_id=None))
    client = fake_client.built[0]
    client.messages = [
        SystemMessage(subtype="init", data={"session_id": "s-1"}),
        StreamEvent(
            uuid="u", session_id="s-1", event={"type": "message_start", "message": {"id": "m1"}}
        ),
        AssistantMessage(content=[TextBlock(text="ok")], model="m", message_id="m1"),
        StreamEvent(
            uuid="u",
            session_id="s-1",
            event={"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {}},
        ),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s-1",
        ),
    ]
    transcript = (
        seat_dir / HARNESS_STATE_DIR_NAME / "claude_config" / "projects" / "ws" / "s-1.jsonl"
    )
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}\n")

    await session.send(prompt="Begin.")
    items = [item async for item in session.items()]
    await session.interrupt()
    await session.close()

    assert client.prompts == ["Begin."]
    assert [type(item) for item in items] == [
        SessionStarted,
        ResponseStarted,
        TextChunk,
        ResponseCompleted,
        CycleEnded,
    ]
    assert client.interrupted
    assert (seat_dir / "transcripts" / "ws" / "s-1.jsonl").read_text() == "{}\n"


async def test_a_session_whose_client_fails_to_connect_is_left_unconnected(
    tmp_path: Path, fake_client: type[FakeClient]
) -> None:
    fake_client.connect_error = RuntimeError("the CLI exited at once")
    session = ClaudeSdkSeatSession()

    with pytest.raises(RuntimeError, match="exited at once"):
        await session.connect(options=seat_options(seat_dir=tmp_path, resume_session_id=None))

    await session.close()
    with pytest.raises(RuntimeError, match="not connected"):
        await session.send(prompt="Begin.")
