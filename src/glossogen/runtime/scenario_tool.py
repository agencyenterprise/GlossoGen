"""How a scenario exposes its own tools to agents.

A scenario returns one ``ScenarioTool`` per tool from ``get_tools``, and the
agent runner offers each to the agents whose ``tool_names`` list it, beside the
base communication tools.

An executor takes ``agent_id`` as its first parameter. The runner supplies it
from the agent the tool was built for, so the model never names who is calling,
and the remaining parameters, with their type annotations, are the tool's input
schema. An executor refuses a call by raising ``ValueError``; the agent reads
the message as the tool's error.
"""

from collections.abc import Awaitable, Callable
from typing import NamedTuple


class ScenarioTool(NamedTuple):
    """A scenario-specific tool, offered to the agents whose ``tool_names`` include it."""

    name: str
    description: str
    executor: Callable[..., Awaitable[str]]
