"""The tools the runtime offers an agent, independent of the agent framework.

A runner binds these specs to its framework's tool type; the supervisor records
the definitions a runner derives from them on ``AgentRegistered``. Each executor
takes ``agent_id`` first and refuses a call by raising ``ValueError``.
"""

from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, Protocol

from glossogen.models.communication_tool_names import (
    GET_CHANNEL_MEMBERS_TOOL_NAME,
    LIST_CHANNELS_TOOL_NAME,
    READ_CHANNEL_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
)
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
