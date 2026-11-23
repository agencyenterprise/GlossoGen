"""The tools the runtime offers an agent, independent of the agent framework.

A runner binds these specs to its framework's tool type; the supervisor records
the definitions a runner derives from them on ``AgentRegistered``, in the order
that the runner sends them. Each executor takes ``agent_id`` first and refuses a call
by raising ``ValueError``.
"""

from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, Protocol

from glossogen.models.communication_tool_names import (
    BASE_TOOL_NAMES,
    GET_CHANNEL_MEMBERS_TOOL_NAME,
    LIST_CHANNELS_TOOL_NAME,
    READ_CHANNEL_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
)
from glossogen.models.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME
from glossogen.models.tool_definition import RecordedToolDefinition
from glossogen.runtime.communication_tools import (
    GET_CHANNEL_MEMBERS_DESCRIPTION,
    LIST_CHANNELS_DESCRIPTION,
    READ_CHANNEL_DESCRIPTION,
    build_get_channel_members,
    build_list_channels,
    build_read_channel,
)
from glossogen.runtime.simulation_state import SimulationRuntime

Executor = Callable[..., Awaitable[Any]]


class ToolSpec(NamedTuple):
    """One tool as the runtime offers it: its executor takes ``agent_id`` first."""

    name: str
    description: str
    executor: Executor
    timeout_s: float | None


def tool_specs(runtime: SimulationRuntime) -> list[ToolSpec]:
    """Every tool the runtime offers other than ``read_notifications``, in listing order."""
    scenario = runtime.scenario
    specs = [
        ToolSpec(
            name=READ_CHANNEL_TOOL_NAME,
            description=READ_CHANNEL_DESCRIPTION,
            executor=build_read_channel(runtime=runtime),
            timeout_s=None,
        ),
        ToolSpec(
            name=SEND_MESSAGE_TOOL_NAME,
            description=scenario.send_message_description(),
            executor=scenario.send_message_executor(),
            timeout_s=None,
        ),
        ToolSpec(
            name=LIST_CHANNELS_TOOL_NAME,
            description=LIST_CHANNELS_DESCRIPTION,
            executor=build_list_channels(runtime=runtime),
            timeout_s=None,
        ),
        ToolSpec(
            name=GET_CHANNEL_MEMBERS_TOOL_NAME,
            description=GET_CHANNEL_MEMBERS_DESCRIPTION,
            executor=build_get_channel_members(runtime=runtime),
            timeout_s=None,
        ),
    ]
    for scenario_tool in scenario.get_tools():
        specs.append(
            ToolSpec(
                name=scenario_tool.name,
                description=scenario_tool.description,
                executor=scenario_tool.executor,
                timeout_s=scenario.scenario_tool_timeout_s(),
            )
        )
    return specs


def offered_tool_specs(runtime: SimulationRuntime, agent_id: str) -> list[ToolSpec]:
    """The specs ``agent_id`` is offered, in listing order, without ``read_notifications``.

    A base tool the scenario hides from the agent is left out, and a scenario
    tool is kept only when the agent's ``tool_names`` list it.
    """
    offered: list[ToolSpec] = []
    for spec in tool_specs(runtime=runtime):
        if spec.name in BASE_TOOL_NAMES:
            if runtime.is_base_tool_hidden(agent_id=agent_id, tool_name=spec.name):
                continue
        elif not runtime.is_tool_allowed(agent_id=agent_id, tool_name=spec.name):
            continue
        offered.append(spec)
    return offered


def offered_tool_names(runtime: SimulationRuntime, agent_id: str) -> list[str]:
    """The names of the tools ``agent_id`` is offered, in the order that the model receives them.

    The runner sends the offered specs in listing order and ``read_notifications`` last.
    """
    names = [spec.name for spec in offered_tool_specs(runtime=runtime, agent_id=agent_id)]
    return [*names, READ_NOTIFICATIONS_TOOL_NAME]


class ToolDefinitionLister(Protocol):
    """Lists the tools an agent can be offered, with the schema its framework sends the model.

    The entry point supplies one, so the supervisor records on ``AgentRegistered``
    what the runner it built will send.
    """

    def __call__(self, runtime: SimulationRuntime) -> list[RecordedToolDefinition]: ...


def select_tool_definitions(
    definitions: list[RecordedToolDefinition],
    tool_names: list[str],
) -> list[RecordedToolDefinition]:
    """The definitions of ``tool_names``, in that order, once each.

    A name with no definition is skipped, and a repeated name is listed once.
    """
    by_name = {definition.name: definition for definition in definitions}
    return [by_name[name] for name in dict.fromkeys(tool_names) if name in by_name]
