"""``SeatSession`` over the Claude Agent SDK.

The only module that imports ``claude_agent_sdk``. The harness loads it with
``importlib`` once the ``harness-claude-agent-sdk`` extra is known to be
installed, so the platform imports cleanly without it.

The CLI is started with no built-in tools, no filesystem settings, no MCP
servers but the seat's own, and a system prompt that replaces Claude Code's.
Its configuration directory is ``harness_state/claude_config`` under the seat's
directory rather than the user's home, so nothing it writes leaves the run;
archives drop ``harness_state/``, and the session transcripts are copied to
``transcripts/`` beside it when the session closes. Partial messages are
requested because a response's stop reason and final usage arrive only on the
raw ``message_delta`` stream event.

The SDK copies the whole parent environment into the CLI's, so the CLI is
started through a launcher (:mod:`.cli_launcher`) that removes the inherited
``CLAUDE*`` variables first. The CLI then bills ``ANTHROPIC_API_KEY`` as a
pydantic-ai seat does, and a run started from inside a Claude Code session does
not hand that session's variables to its seats.

When a request fails for good, the CLI reports it as an assistant message
carrying an ``error`` and the API's error text. That message is not the model's
output, so it is logged as a warning and kept out of the seat's responses; the
turn's result reports the failure.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SdkMcpTool,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)

from glossogen.models.event_base import TokenUsage
from glossogen.runners.agent_tools import serialize_tool_result
from glossogen.runners.claude_agent_sdk.cli_launcher import (
    bundled_cli_path,
    removed_variables,
    write_cli_launcher,
)
from glossogen.runners.harness_names import HARNESS_STATE_DIR_NAME
from glossogen.runners.session_harness.seat_session import (
    CompactionBoundary,
    CycleEnded,
    ResponseCompleted,
    ResponseStarted,
    SeatOptions,
    SeatTool,
    SessionItem,
    SessionStarted,
    TextChunk,
    ThinkingChunk,
    ToolResultChunk,
    ToolUseChunk,
)
from glossogen.runners.session_harness.session_transcripts import keep_session_transcripts

logger = logging.getLogger(__name__)

TOOL_SERVER_NAME = "glossogen"
TOOL_NAME_PREFIX = f"mcp__{TOOL_SERVER_NAME}__"
COMPACTION_SUBTYPE = "compact_boundary"
INIT_SUBTYPE = "init"
THINKING_PROVIDER_NAME = "anthropic"
TOOL_TIMEOUT_MILLISECONDS = 24 * 60 * 60 * 1000
"""How long the CLI waits on one tool call. ``read_notifications`` parks for as
long as a round lasts, so the CLI must never give up on it first."""


class ClaudeSdkSeatSession:
    """One seat's ``ClaudeSDKClient``, translated into ``SessionItem``s."""

    def __init__(self) -> None:
        self._client: ClaudeSDKClient | None = None
        self._translator = SdkMessageTranslator()
        self._seat_dir: Path | None = None

    async def connect(self, options: SeatOptions) -> None:
        """Start the CLI with the seat's tools served from this process."""
        seat_dir = options.seat_dir.resolve()
        state_dir = seat_dir / HARNESS_STATE_DIR_NAME
        workspace = state_dir / "workspace"
        config_dir = state_dir / "claude_config"
        workspace.mkdir(parents=True, exist_ok=True)
        config_dir.mkdir(parents=True, exist_ok=True)
        self._seat_dir = seat_dir
        cli_env = {
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(options.max_output_tokens),
            "MCP_TOOL_TIMEOUT": str(TOOL_TIMEOUT_MILLISECONDS),
        }
        launcher = write_cli_launcher(
            directory=state_dir,
            cli=bundled_cli_path(),
            removed=removed_variables(environ=os.environ, kept=cli_env),
        )
        server = create_sdk_mcp_server(
            name=TOOL_SERVER_NAME,
            version="1.0.0",
            tools=[_sdk_tool(seat_tool=seat_tool) for seat_tool in options.tools],
        )
        client = ClaudeSDKClient(
            options=ClaudeAgentOptions(
                model=options.model,
                system_prompt=options.system_prompt,
                tools=[],
                allowed_tools=[f"{TOOL_NAME_PREFIX}*"],
                permission_mode="dontAsk",
                mcp_servers={TOOL_SERVER_NAME: server},
                strict_mcp_config=True,
                setting_sources=[],
                cwd=workspace,
                thinking={"type": "disabled"},
                include_partial_messages=True,
                resume=options.resume_session_id,
                cli_path=launcher,
                env=cli_env,
            )
        )
        await client.connect()
        self._client = client

    async def send(self, prompt: str) -> None:
        """Send the next user turn."""
        await self._connected().query(prompt)

    async def items(self) -> AsyncIterator[SessionItem]:
        """Translate the CLI's messages for the current turn, ending with ``CycleEnded``."""
        async for message in self._connected().receive_response():
            for item in self._translator.translate(message=message):
                yield item

    async def interrupt(self) -> None:
        """Stop the turn in progress."""
        await self._connected().interrupt()

    async def close(self) -> None:
        """End the CLI process and keep its session transcripts with the run."""
        if self._client is None:
            return
        client = self._client
        self._client = None
        try:
            await client.disconnect()
        finally:
            if self._seat_dir is not None:
                await asyncio.to_thread(
                    keep_session_transcripts,
                    seat_dir=self._seat_dir,
                    source_dir=self._seat_dir
                    / HARNESS_STATE_DIR_NAME
                    / "claude_config"
                    / "projects",
                )

    def _connected(self) -> ClaudeSDKClient:
        if self._client is None:
            raise RuntimeError("the seat session is not connected")
        return self._client


class SdkMessageTranslator:
    """Turns the SDK's messages into ``SessionItem``s, remembering the open response."""

    def __init__(self) -> None:
        self._open_message_id = ""

    def translate(self, message: object) -> list[SessionItem]:
        """The items one SDK message carries; messages the runner has no use for carry none."""
        if isinstance(message, StreamEvent):
            return self._translate_stream_event(event=message.event)
        if isinstance(message, AssistantMessage) and message.error is not None:
            logger.warning(
                "The CLI reported a failed request (%s): %s",
                message.error,
                _block_texts(blocks=message.content),
            )
            return []
        if isinstance(message, AssistantMessage):
            message_id = self._open_message_id
            if message.message_id is not None:
                message_id = message.message_id
            return _translate_blocks(message_id=message_id, blocks=message.content)
        if isinstance(message, UserMessage):
            return _translate_tool_results(content=message.content)
        if isinstance(message, ResultMessage):
            return [_cycle_ended(result=message)]
        if isinstance(message, SystemMessage) and message.subtype == COMPACTION_SUBTYPE:
            return [CompactionBoundary(details=message.data)]
        if isinstance(message, SystemMessage) and message.subtype == INIT_SUBTYPE:
            return [SessionStarted(session_id=str(message.data["session_id"]))]
        return []

    def _translate_stream_event(self, event: dict[str, Any]) -> list[SessionItem]:
        """A response opens on ``message_start`` and closes on ``message_delta``."""
        kind = event.get("type")
        if kind == "message_start":
            message = cast(dict[str, Any], event["message"])
            self._open_message_id = str(message["id"])
            return [ResponseStarted(message_id=self._open_message_id)]
        if kind == "message_delta":
            delta = cast(dict[str, Any], event.get("delta", {}))
            stop_reason = delta.get("stop_reason")
            if stop_reason is None:
                stop_reason = ""
            usage = cast(dict[str, Any], event.get("usage", {}))
            return [
                ResponseCompleted(
                    message_id=self._open_message_id,
                    stop_reason=str(stop_reason),
                    usage=_token_usage(usage=usage),
                )
            ]
        return []


def _sdk_tool(seat_tool: SeatTool) -> SdkMcpTool[Any]:
    """Serve one seat tool through the SDK's in-process MCP server.

    The ``{"content": ..., "is_error": ...}`` dict is the SDK's handler contract.
    """

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        outcome = await seat_tool.handler(arguments)
        return {
            "content": [{"type": "text", "text": serialize_tool_result(content=outcome.content)}],
            "is_error": outcome.is_error,
        }

    return tool(
        name=seat_tool.name,
        description=seat_tool.description,
        input_schema=seat_tool.input_schema,
    )(handle)


def _block_texts(blocks: list[Any]) -> str:
    """The text blocks of a message, joined."""
    return " ".join(block.text for block in blocks if isinstance(block, TextBlock))


def _translate_blocks(message_id: str, blocks: list[Any]) -> list[SessionItem]:
    """Text, thinking and tool-use blocks of a response."""
    items: list[SessionItem] = []
    for block in blocks:
        if isinstance(block, TextBlock):
            items.append(TextChunk(message_id=message_id, text=block.text))
        elif isinstance(block, ThinkingBlock):
            items.append(
                ThinkingChunk(
                    message_id=message_id,
                    thinking=block.thinking,
                    signature=block.signature,
                    provider_name=THINKING_PROVIDER_NAME,
                )
            )
        elif isinstance(block, ToolUseBlock):
            items.append(
                ToolUseChunk(
                    message_id=message_id,
                    call_id=block.id,
                    tool_name=block.name.removeprefix(TOOL_NAME_PREFIX),
                    arguments=block.input,
                    answered_by_cli=False,
                )
            )
        else:
            logger.warning("Ignoring an assistant block of type %s", type(block).__name__)
    return items


def _translate_tool_results(content: object) -> list[SessionItem]:
    """The tool results a user message carries back to the model."""
    if not isinstance(content, list):
        return []
    items: list[SessionItem] = []
    for block in cast(list[Any], content):
        if isinstance(block, ToolResultBlock):
            items.append(
                ToolResultChunk(
                    call_id=block.tool_use_id,
                    content=_tool_result_text(content=block.content),
                )
            )
    return items


def _tool_result_text(content: object) -> str:
    """A tool result's text, whether the CLI sent a string or a list of content parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            str(part.get("text", ""))
            for part in cast(list[dict[str, Any]], content)
            if part.get("type") == "text"
        ]
        return "".join(texts)
    return str(content)


def _token_usage(usage: dict[str, Any]) -> TokenUsage:
    """A response's final usage from its ``message_delta`` event.

    Anthropic's ``input_tokens`` counts only the uncached input; ``TokenUsage``
    counts all of it, cache reads and writes included, so they are added back.
    """
    uncached = int(usage.get("input_tokens", 0))
    cache_read = int(usage.get("cache_read_input_tokens", 0))
    cache_write = int(usage.get("cache_creation_input_tokens", 0))
    return TokenUsage(
        input_tokens=uncached + cache_read + cache_write,
        output_tokens=int(usage.get("output_tokens", 0)),
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
    )


def _cycle_ended(result: ResultMessage) -> CycleEnded:
    """The end of one turn, with the CLI's explanation when it failed."""
    error_text = ""
    if result.is_error:
        reasons: list[str] = []
        if result.result is not None:
            reasons.append(result.result)
        if result.errors is not None:
            reasons.extend(result.errors)
        if not reasons:
            reasons.append(result.subtype)
        error_text = "; ".join(reasons)
    return CycleEnded(
        session_id=result.session_id,
        is_error=result.is_error,
        error_text=error_text,
        reported_cost_usd=result.total_cost_usd,
    )
