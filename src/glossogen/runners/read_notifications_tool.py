"""The ``read_notifications`` tool.

The call parks the agent in the runtime's wait registry and returns once a
condition of its ``wait_for`` holds. While parked, the agent makes no model
request, and a scenario that simulates time sees the agent as parked rather than
as a tool call in flight. pydantic-ai reports the call and its result as for any
tool, so the event log, history reconstruction and history cleanup handle it
like any other tool.

A call issued alongside other tool calls does not park. The siblings run, and
this call answers ``no_activity`` asking the agent to call it on its own.
"""

import logging
from typing import Any

from pydantic import ValidationError
from pydantic_ai import RunContext, Tool
from pydantic_ai.messages import ModelResponse, ToolCallPart

from glossogen.models.event import AgentResumed, WaitRegistered
from glossogen.runtime.notification_payload import (
    NotificationInbox,
    Wake,
    render_parallel_rejection,
)
from glossogen.runtime.read_notifications_schema import (
    READ_NOTIFICATIONS_TOOL_NAME,
    ReadNotificationsArguments,
)
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.runtime.wait_registry import WakeReason, wait_deadline

logger = logging.getLogger(__name__)


class RunTermination:
    """Set when a resumed wait ended the run for this agent; the runner stops after that cycle."""

    def __init__(self) -> None:
        self._set = False

    def set(self) -> None:
        """Record that the run is over for this agent."""
        self._set = True

    @property
    def is_set(self) -> bool:
        """True once a wait resumed with the run over."""
        return self._set


def _called_with_siblings(messages: list[Any]) -> bool:
    """True when the response that issued this call also issued other tool calls."""
    for message in reversed(messages):
        if isinstance(message, ModelResponse):
            calls = [part for part in message.parts if isinstance(part, ToolCallPart)]
            return len(calls) > 1
    return False


def build_read_notifications_tool(
    runtime: SimulationRuntime, agent_id: str, termination: RunTermination
) -> Tool[None]:
    """Return the pydantic-ai tool that parks ``agent_id`` until its wait is satisfied."""

    async def read_notifications(ctx: RunContext[None], **arguments: Any) -> str:
        try:
            parsed = ReadNotificationsArguments.model_validate(arguments)
        except ValidationError as error:
            logger.exception("Agent %s passed invalid read_notifications arguments", agent_id)
            return f"Invalid arguments for read_notifications: {error}"
        session = runtime.resolve_session(agent_id=agent_id)
        if _called_with_siblings(messages=ctx.messages):
            logger.info("Agent %s read_notifications rejected: parallel call", agent_id)
            inbox = NotificationInbox(session=session, channel_router=runtime.channel_router)
            return render_parallel_rejection(
                current_round=runtime.current_round,
                pending_count=inbox.remaining(),
            )
        return await _park_and_render(
            runtime=runtime, agent_id=agent_id, arguments=parsed, termination=termination
        )

    return Tool.from_schema(
        function=read_notifications,
        name=READ_NOTIFICATIONS_TOOL_NAME,
        description=runtime.scenario.read_notifications_description(),
        json_schema=ReadNotificationsArguments.model_json_schema(),
        takes_ctx=True,
    )


async def _park_and_render(
    runtime: SimulationRuntime,
    agent_id: str,
    arguments: ReadNotificationsArguments,
    termination: RunTermination,
) -> str:
    """Park the agent, wait for its wake, and return the scenario's rendering of it."""
    registry = runtime.wait_registry
    deadline_s = wait_deadline(
        wait_for=arguments.wait_kind,
        timeout_s=arguments.timeout_s,
        default_any_timeout_s=runtime.scenario.default_any_wait_timeout_s(),
    )
    wait = registry.register(agent_id=agent_id, wait_for=arguments.wait_kind, deadline_s=deadline_s)
    try:
        await runtime.event_logger.log(
            event=WaitRegistered(
                agent_id=agent_id,
                round_number=runtime.current_round,
                wait_id=wait.wait_id,
                wait_for=arguments.wait_kind,
                deadline_s=deadline_s,
            )
        )
        signal = await wait.future
    finally:
        # A cancelled runner cancels the future it awaits, so a cancelled future
        # is the case to clean up, alongside one that never resolved.
        if not wait.future.done() or wait.future.cancelled():
            registry.cancel(wait=wait)
    session = runtime.resolve_session(agent_id=agent_id)
    terminated = WakeReason.DONE in signal.reasons
    wake = Wake(
        wait_for=arguments.wait_kind,
        reasons=signal.reasons,
        waited_seconds=signal.waited_seconds,
        inbox=NotificationInbox(session=session, channel_router=runtime.channel_router),
        terminated=terminated,
        done_reason=session.done_reason,
        release_detail=signal.release_detail,
    )
    rendered = await runtime.scenario.read_notifications(agent_id=agent_id, wake=wake)
    await runtime.event_logger.log(
        event=AgentResumed(
            agent_id=agent_id,
            round_number=runtime.current_round,
            wait_id=wait.wait_id,
            wake_reasons=[reason.value for reason in signal.reasons],
            waited_seconds=signal.waited_seconds,
            terminated=terminated,
        )
    )
    if terminated:
        termination.set()
    return rendered
