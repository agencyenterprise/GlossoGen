"""The ``claude-agent-sdk`` harness: drives seats through the Claude Code CLI.

The SDK is the optional ``harness-claude-agent-sdk`` extra. The launch check
refuses a seat under this harness when the extra is missing or the seat's
provider is not Anthropic. The adapter is imported by name only when a runner
is built, so the platform imports cleanly without the extra.
"""

import importlib
import importlib.util
from typing import cast

from glossogen.model_catalog import Provider
from glossogen.runners.harness_names import CLAUDE_AGENT_SDK_HARNESS_NAME
from glossogen.runners.harness_protocol import AgentHarness, HarnessSeat, RunnerBuildContext
from glossogen.runners.session_harness.runner import SessionSeatRunner
from glossogen.runners.session_harness.seat_session import SeatSessionFactory

SDK_MODULE = "claude_agent_sdk"
SDK_EXTRA = "harness-claude-agent-sdk"
ADAPTER_MODULE = "glossogen.runners.claude_agent_sdk.claude_sdk_seat_session"
ADAPTER_CLASS = "ClaudeSdkSeatSession"


class ClaudeAgentSdkHarness(AgentHarness):
    """Builds ``SessionSeatRunner`` instances over the Claude Agent SDK adapter."""

    @classmethod
    def name(cls) -> str:
        return CLAUDE_AGENT_SDK_HARNESS_NAME

    @classmethod
    def gates_model_responses(cls) -> bool:
        return False

    @classmethod
    def preflight(cls, seats: tuple[HarnessSeat, ...]) -> tuple[str, ...]:
        remedies: list[str] = []
        if importlib.util.find_spec(name=SDK_MODULE) is None:
            remedies.append(f"install the {SDK_EXTRA} extra (uv sync --extra {SDK_EXTRA})")
        other_providers = sorted({seat.provider.value for seat in seats} - {Provider.ANTHROPIC})
        if other_providers:
            remedies.append(
                f"run these seats under provider {Provider.ANTHROPIC.value}; Claude Code "
                f"drives Claude models only, not {', '.join(other_providers)}"
            )
        return tuple(remedies)

    @classmethod
    def build_runner(cls, context: RunnerBuildContext) -> SessionSeatRunner:
        adapter = importlib.import_module(name=ADAPTER_MODULE)
        session_factory = cast(SeatSessionFactory, getattr(adapter, ADAPTER_CLASS))
        return SessionSeatRunner(
            context=context,
            session_factory=session_factory,
            harness_name=CLAUDE_AGENT_SDK_HARNESS_NAME,
        )
