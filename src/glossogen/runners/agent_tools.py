"""The tools one agent is offered, built as pydantic-ai function tools.

Every tool runs in the runner's process, in the calling agent's own task. The
agent id is bound when the tool is built: an executor receives it as its
``agent_id`` argument and the model never supplies it, so the remaining
parameters are the schema the model sees. A tool refuses a call by raising
``ValueError``, which reaches the model as the tool's error in the executor's
words; any other exception is logged here and reaches the model as
``Error executing tool <name>``.

``list_tool_definitions`` describes the same tools without binding an agent,
for the ``agent_registered`` event and the ATIF export.
"""

import asyncio
import inspect
import logging
import typing
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

from pydantic import BaseModel
from pydantic_ai import ModelRetry, Tool

from glossogen.models.tool_definition import RecordedToolDefinition
from glossogen.runners.read_notifications_tool import (
    RunTermination,
    build_read_notifications_tool,
)
from glossogen.runtime.communication_tools import (
    BASE_TOOL_NAMES,
    GET_CHANNEL_MEMBERS_DESCRIPTION,
    LIST_CHANNELS_DESCRIPTION,
    READ_CHANNEL_DESCRIPTION,
    build_get_channel_members,
    build_list_channels,
    build_read_channel,
)
from glossogen.runtime.read_notifications_schema import read_notifications_tool_definition
from glossogen.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)

SCENARIO_TOOL_TIMEOUT_SECONDS = 120.0
"""Cap on a scenario tool body, so a stalled call (a judge HTTP request that hangs)
is cancelled and the agent told, rather than the agent waiting on it for the rest
of the round. The base communication tools are not capped."""

TOOL_ERROR_RETRY_LIMIT = 1_000_000
"""How many tool errors one agent cycle may carry before pydantic-ai aborts it.

A refusal is the scenario telling the agent what it did wrong, not a fault of
the run, so a cycle is not aborted however many an agent collects.
"""

AGENT_ID_PARAMETER = "agent_id"

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
            name="read_channel",
            description=READ_CHANNEL_DESCRIPTION,
            executor=build_read_channel(runtime=runtime),
            timeout_s=None,
        ),
        ToolSpec(
            name="send_message",
            description=scenario.send_message_description(),
            executor=scenario.send_message_executor(),
            timeout_s=None,
        ),
        ToolSpec(
            name="list_channels",
            description=LIST_CHANNELS_DESCRIPTION,
            executor=build_list_channels(runtime=runtime),
            timeout_s=None,
        ),
        ToolSpec(
            name="get_channel_members",
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
                timeout_s=SCENARIO_TOOL_TIMEOUT_SECONDS,
            )
        )
    return specs


def build_agent_tools(
    runtime: SimulationRuntime, agent_id: str, termination: RunTermination
) -> list[Tool[None]]:
    """The tools ``agent_id`` is offered: its base tools, its scenario tools, and the wait.

    A base tool the scenario withholds through ``hidden_base_tools`` is left out,
    and a scenario tool is included only when the agent's ``tool_names`` list it.
    """
    tools: list[Tool[None]] = []
    for spec in tool_specs(runtime=runtime):
        if spec.name in BASE_TOOL_NAMES:
            if runtime.is_base_tool_hidden(agent_id=agent_id, tool_name=spec.name):
                continue
        elif not runtime.is_tool_allowed(agent_id=agent_id, tool_name=spec.name):
            continue
        tools.append(_bind(spec=spec, runtime=runtime, agent_id=agent_id))
    tools.append(
        build_read_notifications_tool(runtime=runtime, agent_id=agent_id, termination=termination)
    )
    return tools


def list_tool_definitions(runtime: SimulationRuntime) -> list[RecordedToolDefinition]:
    """Every tool an agent can be offered, with the schema the model would see."""
    definitions: list[RecordedToolDefinition] = []
    for spec in tool_specs(runtime=runtime):

        async def describe(**arguments: Any) -> Any:
            raise NotImplementedError("a tool definition is never called")

        tool = Tool(
            _with_schema_of(function=describe, spec=spec),
            takes_ctx=False,
            name=spec.name,
            description=spec.description,
        )
        definitions.append(
            RecordedToolDefinition(
                name=spec.name,
                description=spec.description,
                input_schema=tool.tool_def.parameters_json_schema,
            )
        )
    definitions.append(
        read_notifications_tool_definition(
            description=runtime.scenario.read_notifications_description()
        )
    )
    return definitions


def select_tool_definitions(
    definitions: list[RecordedToolDefinition],
    tool_names: list[str],
) -> list[RecordedToolDefinition]:
    """The definitions of ``tool_names``, in that order, once each.

    A name with no definition is skipped, and a repeated name is listed once.
    """
    by_name = {definition.name: definition for definition in definitions}
    return [by_name[name] for name in dict.fromkeys(tool_names) if name in by_name]


def _bind(spec: ToolSpec, runtime: SimulationRuntime, agent_id: str) -> Tool[None]:
    """A pydantic-ai tool that runs ``spec.executor`` as ``agent_id``."""

    async def call(**arguments: Any) -> Any:
        session = runtime.resolve_session(agent_id=agent_id)
        if session.terminated:
            # The agent is being torn down for its swapped-in successor; a
            # state-mutating call now would land under the new occupant.
            raise ModelRetry(
                f"Agent '{agent_id}' is being swapped out; tool '{spec.name}' rejected. "
                "Read your notifications to exit cleanly."
            )
        try:
            if spec.timeout_s is None:
                result = await spec.executor(agent_id=agent_id, **arguments)
            else:
                result = await asyncio.wait_for(
                    spec.executor(agent_id=agent_id, **arguments), timeout=spec.timeout_s
                )
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc
        except asyncio.TimeoutError:
            logger.exception(
                "Tool %s for agent %s exceeded %.0fs and was cancelled to free the agent",
                spec.name,
                agent_id,
                spec.timeout_s,
            )
            return (
                f"The '{spec.name}' action timed out after {spec.timeout_s:.0f} seconds "
                "and was cancelled. Try again."
            )
        except ModelRetry:
            raise
        except Exception as exc:
            logger.exception("Tool %s raised for agent %s", spec.name, agent_id)
            raise ModelRetry(f"Error executing tool {spec.name}") from exc
        if isinstance(result, BaseModel):
            return result.model_dump()
        return result

    return Tool(
        _with_schema_of(function=call, spec=spec),
        takes_ctx=False,
        name=spec.name,
        description=spec.description,
        max_retries=TOOL_ERROR_RETRY_LIMIT,
    )


def _with_schema_of(function: Callable[..., Awaitable[Any]], spec: ToolSpec) -> Executor:
    """Give ``function`` the executor's signature and annotations, less ``agent_id``.

    pydantic-ai builds a tool's schema from these, so the model sees the
    executor's own parameters and types, and not the agent id the runner binds.
    """
    signature = inspect.signature(spec.executor)
    if AGENT_ID_PARAMETER not in signature.parameters:
        raise ValueError(f"tool {spec.name!r}: its executor must take {AGENT_ID_PARAMETER}")
    hints = typing.get_type_hints(spec.executor)
    parameters = [
        parameter for name, parameter in signature.parameters.items() if name != AGENT_ID_PARAMETER
    ]
    annotations = {
        name: hints[name]
        for name in signature.parameters
        if name != AGENT_ID_PARAMETER and name in hints
    }
    if "return" in hints:
        annotations["return"] = hints["return"]
    function.__signature__ = signature.replace(parameters=parameters)  # type: ignore[attr-defined]  # pyright: ignore[reportFunctionMemberAccess]
    function.__annotations__ = annotations
    function.__name__ = spec.name
    function.__doc__ = None
    return function
