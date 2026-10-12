"""The tools a seat on ``SessionSeatRunner`` is served, as ``SeatTool``s.

Every tool runs through the same executors and error handling as a pydantic-ai
seat's, from :mod:`glossogen.runners.agent_tools`, and ``read_notifications``
parks through :func:`glossogen.runners.read_notifications_tool.park_and_render`.
Only how a parallel ``read_notifications`` call is detected differs: the
response it came from is read off the ``ResponseTracker``.
"""

import logging
from typing import Any

from pydantic import ValidationError

from glossogen.runners.agent_tools import (
    ToolOutcome,
    ToolSpec,
    execute_tool_spec,
    list_tool_definitions,
    offered_tool_specs,
)
from glossogen.runners.read_notifications_tool import (
    RunTermination,
    park_and_render,
    reject_parallel_call,
)
from glossogen.runners.session_harness.response_tracker import ResponseTracker
from glossogen.runners.session_harness.seat_session import SeatTool, SeatToolHandler
from glossogen.runtime.read_notifications_schema import (
    READ_NOTIFICATIONS_TOOL_NAME,
    ReadNotificationsArguments,
)
from glossogen.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)


def build_seat_tools(
    runtime: SimulationRuntime,
    agent_id: str,
    termination: RunTermination,
    tracker: ResponseTracker,
) -> tuple[SeatTool, ...]:
    """The tools ``agent_id`` is offered, with the schemas a pydantic-ai seat would see."""
    schemas = {
        definition.name: definition.input_schema
        for definition in list_tool_definitions(runtime=runtime)
    }
    tools = [
        SeatTool(
            name=spec.name,
            description=spec.description,
            input_schema=schemas[spec.name],
            handler=_spec_handler(spec=spec, runtime=runtime, agent_id=agent_id),
        )
        for spec in offered_tool_specs(runtime=runtime, agent_id=agent_id)
    ]
    tools.append(
        SeatTool(
            name=READ_NOTIFICATIONS_TOOL_NAME,
            description=runtime.scenario.read_notifications_description(),
            input_schema=schemas[READ_NOTIFICATIONS_TOOL_NAME],
            handler=_read_notifications_handler(
                runtime=runtime, agent_id=agent_id, termination=termination, tracker=tracker
            ),
        )
    )
    return tuple(tools)


def _spec_handler(spec: ToolSpec, runtime: SimulationRuntime, agent_id: str) -> SeatToolHandler:
    """A handler running ``spec`` as ``agent_id``."""

    async def handle(arguments: dict[str, Any]) -> ToolOutcome:
        return await execute_tool_spec(
            spec=spec, runtime=runtime, agent_id=agent_id, arguments=arguments
        )

    return handle


def _read_notifications_handler(
    runtime: SimulationRuntime,
    agent_id: str,
    termination: RunTermination,
    tracker: ResponseTracker,
) -> SeatToolHandler:
    """A handler that parks the seat, unless the call shared its response with others.

    The tracker is consulted before the arguments are validated, so a call this
    handler sees consumes its own entry even when its arguments are refused.
    """

    async def handle(arguments: dict[str, Any]) -> ToolOutcome:
        shares_response = await tracker.next_wait_call_shares_its_response()
        try:
            parsed = ReadNotificationsArguments.model_validate(arguments)
        except ValidationError as error:
            logger.exception("Agent %s sent read_notifications invalid arguments", agent_id)
            return ToolOutcome(
                content=f"Invalid arguments for read_notifications: {error}", is_error=True
            )
        if shares_response:
            return ToolOutcome(
                content=reject_parallel_call(runtime=runtime, agent_id=agent_id), is_error=False
            )
        rendered = await park_and_render(
            runtime=runtime, agent_id=agent_id, arguments=parsed, termination=termination
        )
        return ToolOutcome(content=rendered, is_error=False)

    return handle
