"""The ``claude-code`` harness: a seat run by the Claude Code CLI connected over MCP.

Each turn is one ``claude --print`` process. It is started with the platform's
system prompt in place of Claude Code's, no built-in tools, no settings files,
and only the seat's MCP server, in a configuration directory private to the
seat. A later turn resumes the session the first one started with
``--session-id``. The inherited ``CLAUDE*`` variables and
``ANTHROPIC_IDENTITY_TOKEN`` are removed from its environment, so a run started
from inside a Claude Code session does not hand that session's variables, or
another credential, to its seats; ``ANTHROPIC_API_KEY`` is what the CLI bills.

The turn's result is read from the ``--output-format json`` object the CLI
prints last: its session id, usage and cost.
"""

import json
import shutil
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from glossogen.model_catalog import Provider
from glossogen.models.event_base import TokenUsage
from glossogen.runners.external_cli.cli_protocol import NO_USAGE, CliSeat, CliTurn, CliTurnResult
from glossogen.runners.external_cli.cli_seat_runner import (
    ExternalCliRunner,
    inherited_environment,
    pause_after_failures,
)
from glossogen.runners.harness_names import CLAUDE_CODE_HARNESS_NAME
from glossogen.runners.harness_protocol import AgentHarness, HarnessSeat, RunnerBuildContext

BINARY_NAME = "claude"
TOOL_SERVER_NAME = "glossogen"
INHERITED_PREFIX = "CLAUDE"
INHERITED_NAMES = frozenset({"ANTHROPIC_IDENTITY_TOKEN"})
TOOL_TIMEOUT_MILLISECONDS = 24 * 60 * 60 * 1000
"""How long the CLI waits on one tool call. ``read_notifications`` parks for as
long as a round lasts, so the CLI must never give up on it first."""


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _ClaudeUsage(_Lenient):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class _ClaudeResult(_Lenient):
    """The ``result`` object ``claude --print --output-format json`` ends with."""

    type: str
    subtype: str = ""
    is_error: bool = False
    session_id: str | None = None
    total_cost_usd: float | None = None
    usage: _ClaudeUsage | None = None
    result: str | None = None
    errors: list[str] | None = None


class ClaudeCodeCli:
    """How a seat's turns are run with ``claude``."""

    def __init__(self, binary: str) -> None:
        self._binary = binary

    def prepare(self, seat: CliSeat) -> None:
        """The CLI's configuration directory, so nothing it writes leaves the run."""
        (seat.state_dir / "claude_config").mkdir(parents=True, exist_ok=True)

    def command(self, seat: CliSeat, turn: CliTurn) -> list[str]:
        mcp_config = {
            "mcpServers": {
                TOOL_SERVER_NAME: {
                    "type": "http",
                    "url": seat.tool_url,
                    "headers": {"Authorization": f"Bearer {seat.tool_token}"},
                }
            }
        }
        command = [
            self._binary,
            "--print",
            "--output-format",
            "json",
            "--model",
            seat.model,
            "--system-prompt",
            seat.system_prompt,
            "--mcp-config",
            json.dumps(mcp_config),
            "--strict-mcp-config",
            "--tools",
            "",
            "--allowed-tools",
            f"mcp__{TOOL_SERVER_NAME}__*",
            "--permission-mode",
            "dontAsk",
            "--setting-sources",
            "",
        ]
        if turn.resume_session_id is None:
            command.extend(["--session-id", str(uuid.uuid4())])
        else:
            command.extend(["--resume", turn.resume_session_id])
        command.extend(["--", turn.prompt])
        return command

    def environment(self, seat: CliSeat) -> Mapping[str, str]:
        return {
            **inherited_environment(removed_prefix=INHERITED_PREFIX, removed_names=INHERITED_NAMES),
            "CLAUDE_CONFIG_DIR": str(seat.state_dir / "claude_config"),
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(seat.max_output_tokens),
            "MCP_TOOL_TIMEOUT": str(TOOL_TIMEOUT_MILLISECONDS),
            "MAX_THINKING_TOKENS": "0",
        }

    def transcripts_dir(self, seat: CliSeat) -> Path:
        return seat.state_dir / "claude_config" / "projects"

    def parse_output(self, stdout: str) -> CliTurnResult:
        """The last JSON object on stdout, which is the turn's result."""
        text = stdout.strip()
        if not text:
            raise ValueError("claude wrote no result")
        try:
            raw: Any = json.loads(text.splitlines()[-1])
            parsed = _ClaudeResult.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"claude's result is not the expected JSON: {exc}") from exc
        usage = NO_USAGE
        if parsed.usage is not None:
            usage = _token_usage(usage=parsed.usage)
        error_text = ""
        if parsed.is_error:
            reasons: list[str] = []
            if parsed.result is not None:
                reasons.append(parsed.result)
            if parsed.errors is not None:
                reasons.extend(parsed.errors)
            if not reasons:
                reasons.append(parsed.subtype)
            error_text = "; ".join(reasons)
        return CliTurnResult(
            session_id=parsed.session_id,
            usage=usage,
            reported_cost_usd=parsed.total_cost_usd,
            is_error=parsed.is_error,
            error_text=error_text,
        )


def _token_usage(usage: _ClaudeUsage) -> TokenUsage:
    """Anthropic counts only uncached input in ``input_tokens``; ``TokenUsage`` counts all of it."""
    return TokenUsage(
        input_tokens=usage.input_tokens
        + usage.cache_read_input_tokens
        + usage.cache_creation_input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
    )


class ClaudeCodeHarness(AgentHarness):
    """Builds ``ExternalCliRunner`` instances over the ``claude`` binary on ``PATH``."""

    @classmethod
    def name(cls) -> str:
        return CLAUDE_CODE_HARNESS_NAME

    @classmethod
    def gates_model_responses(cls) -> bool:
        return False

    @classmethod
    def preflight(cls, seats: tuple[HarnessSeat, ...]) -> tuple[str, ...]:
        remedies: list[str] = []
        if shutil.which(BINARY_NAME) is None:
            remedies.append(
                f"put the Claude Code CLI ({BINARY_NAME}) on PATH; "
                "npm install -g @anthropic-ai/claude-code installs it"
            )
        other_providers = sorted({seat.provider.value for seat in seats} - {Provider.ANTHROPIC})
        if other_providers:
            remedies.append(
                f"run these seats under provider {Provider.ANTHROPIC.value}; Claude Code "
                f"drives Claude models only, not {', '.join(other_providers)}"
            )
        return tuple(remedies)

    @classmethod
    def build_runner(cls, context: RunnerBuildContext) -> ExternalCliRunner:
        binary = shutil.which(BINARY_NAME)
        if binary is None:
            raise RuntimeError(f"{BINARY_NAME} is not on PATH")
        return ExternalCliRunner(
            context=context,
            harness_name=CLAUDE_CODE_HARNESS_NAME,
            cli=ClaudeCodeCli(binary=binary),
            pause_after_failure=pause_after_failures,
        )
