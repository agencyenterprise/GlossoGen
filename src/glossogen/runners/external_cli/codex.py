"""The ``codex`` harness: a seat run by the Codex CLI connected over MCP.

Each turn is one ``codex exec --json`` process; a later turn is ``codex exec
resume`` on the thread the first one started. Codex is started with the
platform's system prompt as its model instructions, every feature that would
give the model a tool of Codex's own switched off, no approvals, no web search,
no ``AGENTS.md``, and only the seat's MCP server, reached with the seat's token
from ``GLOSSOGEN_AGENT_TOKEN``. The sandbox is ``danger-full-access``: under
any other sandbox mode, ``codex exec`` with ``approval_policy="never"`` denies
every MCP tool call and reports it as cancelled by the user (seen on Codex
0.147.0), and with its own tools off the model has nothing to act on the
filesystem with. Its home is a
directory private to the seat, so no account the user signed in with is read,
and the inherited ``CODEX*`` variables are removed from its environment. A
model provider defined here bills ``OPENAI_API_KEY`` and honours
``OPENAI_BASE_URL``, as a pydantic-ai OpenAI seat does. Reasoning effort and
summaries match the pydantic-ai runner's OpenAI settings. Codex has no
per-response output cap, so ``agent_max_tokens`` is not applied.

The turn's result is read from the JSON lines the CLI prints: the thread id
from ``thread.started``, the usage from ``turn.completed``, and the failure
from ``turn.failed`` or ``error``.
"""

import json
import os
import shutil
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
from glossogen.runners.harness_names import CODEX_HARNESS_NAME
from glossogen.runners.harness_protocol import AgentHarness, HarnessSeat, RunnerBuildContext

BINARY_NAME = "codex"
TOOL_SERVER_NAME = "glossogen"
TOKEN_ENV = "GLOSSOGEN_AGENT_TOKEN"
INHERITED_PREFIX = "CODEX"
MODEL_PROVIDER_ID = "glossogen_openai"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
BASE_URL_ENV = "OPENAI_BASE_URL"
INSTRUCTIONS_FILE_NAME = "model_instructions.md"
TOOL_TIMEOUT_SECONDS = 24 * 60 * 60
"""How long Codex waits on one tool call. ``read_notifications`` parks for as
long as a round lasts, so Codex must never give up on it first."""
STARTUP_TIMEOUT_SECONDS = 60

DISABLED_FEATURES: tuple[str, ...] = (
    "shell_tool",
    "unified_exec",
    "apps",
    "browser_use",
    "browser_use_external",
    "computer_use",
    "image_generation",
    "in_app_browser",
    "multi_agent",
    "plugins",
    "view_image",
    "goals",
    "hooks",
    "skill_search",
    "tool_suggest",
    "shell_snapshot",
    "workspace_dependencies",
    "personality",
    "skill_mcp_dependency_install",
    "remote_plugin",
    "plugin_sharing",
    "code_mode_host",
    "auth_elicitation",
    "tool_call_mcp_elicitation",
)
"""Features that would give the model a tool or a prompt of Codex's own. A name
a Codex release does not know is accepted and ignored."""

CONFIG_OVERRIDES: tuple[str, ...] = (
    'approval_policy="never"',
    'sandbox_mode="danger-full-access"',
    'web_search="disabled"',
    "project_doc_max_bytes=0",
    "include_permissions_instructions=false",
    "include_environment_context=false",
    "include_apps_instructions=false",
    "include_collaboration_mode_instructions=false",
    "tools.experimental_request_user_input={enabled=false}",
    'model_reasoning_effort="high"',
    'model_reasoning_summary="concise"',
    "check_for_update_on_startup=false",
    "analytics.enabled=false",
    "feedback.enabled=false",
    f"mcp_servers.{TOOL_SERVER_NAME}.tool_timeout_sec={TOOL_TIMEOUT_SECONDS}",
    f"mcp_servers.{TOOL_SERVER_NAME}.startup_timeout_sec={STARTUP_TIMEOUT_SECONDS}",
    f'mcp_servers.{TOOL_SERVER_NAME}.bearer_token_env_var="{TOKEN_ENV}"',
    *(f"features.{feature}=false" for feature in DISABLED_FEATURES),
)
"""``-c`` overrides beside the seat's own: no approvals, the sandbox MCP calls
need, no web search, no ``AGENTS.md``, none of Codex's own instructions, no
telemetry, the MCP server's timeouts and credential, and the features off."""


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _CodexUsage(_Lenient):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


class _CodexLine(_Lenient):
    """One line of ``codex exec --json``; the fields read off the kinds that matter."""

    type: str
    thread_id: str | None = None
    usage: _CodexUsage | None = None
    message: str | None = None
    error: dict[str, Any] | None = None


class CodexCli:
    """How a seat's turns are run with ``codex``."""

    def __init__(self, binary: str) -> None:
        self._binary = binary

    def prepare(self, seat: CliSeat) -> None:
        """Codex's home and the instructions file its model reads in place of its own."""
        (seat.state_dir / "codex_home").mkdir(parents=True, exist_ok=True)
        (seat.state_dir / INSTRUCTIONS_FILE_NAME).write_text(seat.system_prompt)

    def command(self, seat: CliSeat, turn: CliTurn) -> list[str]:
        command = [self._binary, "exec"]
        if turn.resume_session_id is not None:
            command.append("resume")
        command.extend(["--json", "--skip-git-repo-check", "--model", seat.model])
        for override in (*self._seat_overrides(seat=seat), *CONFIG_OVERRIDES):
            command.extend(["-c", override])
        if turn.resume_session_id is not None:
            command.append(turn.resume_session_id)
        command.append(turn.prompt)
        return command

    def environment(self, seat: CliSeat) -> Mapping[str, str]:
        return {
            **inherited_environment(removed_prefix=INHERITED_PREFIX, removed_names=frozenset()),
            "CODEX_HOME": str(seat.state_dir / "codex_home"),
            TOKEN_ENV: seat.tool_token,
        }

    def transcripts_dir(self, seat: CliSeat) -> Path:
        return seat.state_dir / "codex_home" / "sessions"

    def parse_output(self, stdout: str) -> CliTurnResult:
        """The thread, usage and failure read off the JSON lines the turn printed."""
        session_id: str | None = None
        usage = NO_USAGE
        errors: list[str] = []
        completed = False
        for raw_line in stdout.splitlines():
            if not raw_line.strip():
                continue
            try:
                line = _CodexLine.model_validate(json.loads(raw_line))
            except (json.JSONDecodeError, ValidationError):
                continue
            if line.type == "thread.started" and line.thread_id is not None:
                session_id = line.thread_id
            elif line.type == "turn.completed":
                completed = True
                if line.usage is not None:
                    usage = _token_usage(usage=line.usage)
            elif line.type in ("turn.failed", "error"):
                errors.append(_error_text(line=line))
        if not completed and not errors:
            raise ValueError("codex printed neither turn.completed nor a failure")
        return CliTurnResult(
            session_id=session_id,
            usage=usage,
            reported_cost_usd=None,
            is_error=bool(errors),
            error_text="; ".join(errors),
        )

    def _seat_overrides(self, seat: CliSeat) -> tuple[str, ...]:
        base_url = os.environ.get(BASE_URL_ENV, "")
        if not base_url:
            base_url = DEFAULT_OPENAI_BASE_URL
        return (
            f'model_provider="{MODEL_PROVIDER_ID}"',
            (
                f"model_providers.{MODEL_PROVIDER_ID}="
                f'{{name="OpenAI",base_url="{base_url}",env_key="OPENAI_API_KEY",'
                'wire_api="responses"}'
            ),
            f'model_instructions_file="{seat.state_dir / INSTRUCTIONS_FILE_NAME}"',
            f'mcp_servers.{TOOL_SERVER_NAME}.url="{seat.tool_url}"',
        )


def _error_text(line: _CodexLine) -> str:
    if line.error is not None and isinstance(line.error.get("message"), str):
        return str(line.error["message"])
    if line.message is not None:
        return line.message
    return line.type


def _token_usage(usage: _CodexUsage) -> TokenUsage:
    """Codex counts cached input inside ``input_tokens``, as ``TokenUsage`` does."""
    return TokenUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=usage.cached_input_tokens,
        cache_creation_input_tokens=0,
    )


class CodexHarness(AgentHarness):
    """Builds ``ExternalCliRunner`` instances over the ``codex`` binary on ``PATH``."""

    @classmethod
    def name(cls) -> str:
        return CODEX_HARNESS_NAME

    @classmethod
    def gates_model_responses(cls) -> bool:
        return False

    @classmethod
    def preflight(cls, seats: tuple[HarnessSeat, ...]) -> tuple[str, ...]:
        remedies: list[str] = []
        if shutil.which(BINARY_NAME) is None:
            remedies.append(
                f"put the Codex CLI ({BINARY_NAME}) on PATH; "
                "npm install -g @openai/codex installs it"
            )
        other_providers = sorted({seat.provider.value for seat in seats} - {Provider.OPENAI})
        if other_providers:
            remedies.append(
                f"run these seats under provider {Provider.OPENAI.value}; Codex drives "
                f"OpenAI models only, not {', '.join(other_providers)}"
            )
        return tuple(remedies)

    @classmethod
    def build_runner(cls, context: RunnerBuildContext) -> ExternalCliRunner:
        binary = shutil.which(BINARY_NAME)
        if binary is None:
            raise RuntimeError(f"{BINARY_NAME} is not on PATH")
        return ExternalCliRunner(
            context=context,
            harness_name=CODEX_HARNESS_NAME,
            cli=CodexCli(binary=binary),
            pause_after_failure=pause_after_failures,
        )
