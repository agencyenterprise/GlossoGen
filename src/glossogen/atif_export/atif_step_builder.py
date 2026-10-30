"""Convert single simulation events into ATIF steps.

One function per event kind. Each takes the ``step_id`` the trajectory assigns, so
numbering stays with the trajectory builder.
"""

from datetime import datetime
from enum import Enum

from glossogen.atif_export.atif_models import (
    AtifMetrics,
    AtifObservation,
    AtifObservationResult,
    AtifStep,
    AtifStepSource,
    AtifToolCall,
)
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    ContextCompacted,
    LLMResponseReceived,
    ToolResultReceived,
)
from glossogen.models.event_base import TokenUsage


class RunnerPromptKind(str, Enum):
    """Which runner prompt opened a cycle."""

    INITIAL = "initial_prompt"
    CONTINUE = "continue_prompt"


def copied_flag(copied: bool) -> bool | None:
    """``True`` for copied context; ``None`` otherwise, so the key is omitted from the document."""
    if copied:
        return True
    return None


def build_system_prompt_step(
    step_id: int,
    registration: AgentRegistered,
    copied: bool,
) -> AtifStep:
    """The system prompt the agent was registered with."""
    return AtifStep(
        step_id=step_id,
        timestamp=registration.timestamp.isoformat(),
        source=AtifStepSource.SYSTEM,
        message=registration.system_prompt,
        model_name=None,
        reasoning_content=None,
        tool_calls=None,
        observation=None,
        metrics=None,
        is_copied_context=copied_flag(copied=copied),
        llm_call_count=None,
        extra={"kind": "system_prompt", "round_number": registration.round_number},
    )


def build_runner_prompt_step(
    step_id: int,
    prompt: str,
    kind: RunnerPromptKind,
    copied: bool,
) -> AtifStep:
    """The user prompt the runner opens an agent cycle with.

    Not timestamped: the log records when a cycle's turns happened, not when its
    prompt was sent.
    """
    return AtifStep(
        step_id=step_id,
        timestamp=None,
        source=AtifStepSource.USER,
        message=prompt,
        model_name=None,
        reasoning_content=None,
        tool_calls=None,
        observation=None,
        metrics=None,
        is_copied_context=copied_flag(copied=copied),
        llm_call_count=None,
        extra={"kind": kind.value},
    )


def build_compaction_step(step_id: int, event: ContextCompacted, copied: bool) -> AtifStep:
    """The summary that replaced the agent's earlier history when the provider compacted it."""
    return AtifStep(
        step_id=step_id,
        timestamp=event.timestamp.isoformat(),
        source=AtifStepSource.SYSTEM,
        message=event.summary_text,
        model_name=None,
        reasoning_content=None,
        tool_calls=None,
        observation=None,
        metrics=None,
        is_copied_context=copied_flag(copied=copied),
        llm_call_count=None,
        extra={
            "kind": "compaction",
            "round_number": event.round_number,
            "provider_name": event.provider_name,
            "summary_char_count": event.summary_char_count,
        },
    )


def build_agent_step(
    step_id: int,
    event: LLMResponseReceived,
    model_name: str,
    cost_usd: float | None,
    results_by_call_id: dict[str, ToolResultReceived],
    failed_cycles: list[AgentRunCycleFailed],
    copied: bool,
    started_at: datetime,
    llm_call_count: int | None,
) -> AtifStep:
    """One LLM response, its tool calls, and the results those calls returned.

    ``started_at`` is when the turn's first tool call was invoked. The response
    event itself is logged only after those calls return, which for a slow tool
    is after events the agent had not yet seen.

    ``failed_cycles`` are the cycles that raised since the previous response; they
    are recorded on this step because a failed cycle produced no turn of its own.

    ``llm_call_count`` is the number of responses in the cycle this step closes,
    and ``None`` on a step that does not close one.
    """
    extra: dict[str, object] = {
        "round_number": event.round_number,
        "stop_reason": event.stop_reason,
    }
    if failed_cycles:
        extra["failed_cycles"] = failed_cycle_records(failures=failed_cycles)
    message = ""
    if event.text is not None:
        message = event.text
    return AtifStep(
        step_id=step_id,
        timestamp=started_at.isoformat(),
        source=AtifStepSource.AGENT,
        message=message,
        model_name=model_name,
        reasoning_content=event.thinking,
        tool_calls=_build_tool_calls(event=event),
        observation=_build_observation(event=event, results_by_call_id=results_by_call_id),
        metrics=build_step_metrics(usage=event.usage, cost_usd=cost_usd),
        is_copied_context=copied_flag(copied=copied),
        llm_call_count=llm_call_count,
        extra=extra,
    )


def failed_cycle_records(failures: list[AgentRunCycleFailed]) -> list[dict[str, object]]:
    """Each failed cycle as the ``extra`` entry that records it."""
    return [
        {"cycle": failure.cycle, "error_type": failure.error_type, "message": failure.message}
        for failure in failures
    ]


def build_step_metrics(usage: TokenUsage, cost_usd: float | None) -> AtifMetrics | None:
    """ATIF metrics from the token usage logged on one response, or ``None`` when it logged none.

    The runner records usage once per agent cycle, on the cycle's last response, and
    zeros on the others. A step's metrics therefore cover every LLM call of the cycle
    it closes; the step's ``llm_call_count`` says how many. ``cost_usd`` is that
    usage's cost, ``None`` for an unpriced model.
    """
    if (
        usage.input_tokens
        + usage.output_tokens
        + usage.cache_read_input_tokens
        + usage.cache_creation_input_tokens
        == 0
    ):
        return None
    return AtifMetrics(
        prompt_tokens=usage.input_tokens,
        completion_tokens=usage.output_tokens,
        cached_tokens=usage.cache_read_input_tokens,
        cost_usd=cost_usd,
        extra={
            "cache_creation_input_tokens": usage.cache_creation_input_tokens,
            # Part of completion_tokens, not an addition to it.
            "reasoning_tokens": usage.reasoning_tokens,
        },
    )


def _build_tool_calls(event: LLMResponseReceived) -> list[AtifToolCall] | None:
    if not event.tool_calls:
        return None
    return [
        AtifToolCall(
            tool_call_id=call.call_id,
            function_name=call.tool_name,
            arguments=call.arguments,
        )
        for call in event.tool_calls
    ]


def _build_observation(
    event: LLMResponseReceived,
    results_by_call_id: dict[str, ToolResultReceived],
) -> AtifObservation | None:
    results = [
        AtifObservationResult(
            source_call_id=call.call_id,
            content=results_by_call_id[call.call_id].result,
        )
        for call in event.tool_calls
        if call.call_id in results_by_call_id
    ]
    if not results:
        return None
    return AtifObservation(results=results)
