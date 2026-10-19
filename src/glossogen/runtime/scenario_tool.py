"""How a scenario exposes its own tools to agents.

A scenario returns one ``ScenarioTool`` per tool from ``get_tools``, and the
agent runner offers each to the agents whose ``tool_names`` list it, beside the
base communication tools.

An executor takes ``agent_id`` as its first parameter. The runner supplies it
from the agent the tool was built for, so the model never names who is calling,
and the remaining parameters, with their type annotations, are the tool's input
schema. An executor refuses a call by raising ``ValueError``; the agent reads
the message as the tool's error.

Each tool states how long its body may run before the runner cancels it.
"""

from collections.abc import Awaitable, Callable
from typing import NamedTuple

SCENARIO_TOOL_TIMEOUT_SECONDS = 120.0
"""The cap a tool that waits on nothing but its own work declares, so a stalled call
(a judge HTTP request that hangs) is cancelled and the agent told, rather than the
agent waiting on it for the rest of the round."""


class ScenarioTool(NamedTuple):
    """A scenario-specific tool, offered to the agents whose ``tool_names`` include it.

    ``timeout_s`` is how long the runner lets one call run before cancelling it and
    telling the agent to try again. ``None`` sets no cap, for a tool whose call waits
    on other agents and is released by the scenario itself, such as at the end of
    the round.
    """

    name: str
    description: str
    executor: Callable[..., Awaitable[str]]
    timeout_s: float | None
