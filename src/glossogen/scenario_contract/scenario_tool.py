"""How a scenario exposes its own tools to agents.

A scenario returns one ``ScenarioTool`` per tool from ``get_tools``, and the
agent runner offers each to the agents whose ``tool_names`` list it, beside the
base communication tools.

An executor takes ``agent_id`` as its first parameter. The runner supplies it
from the agent the tool was built for, so the model never names who is calling,
and the remaining parameters, with their type annotations, are the tool's input
schema. An executor refuses a call by raising ``ValueError``; the agent reads
the message as the tool's error. It returns text, or a Pydantic model the agent
reads as JSON; a model that carries images (``CarriesImages``) reaches the agent
with its images attached.
"""

from collections.abc import Awaitable, Callable
from typing import NamedTuple

from pydantic import BaseModel

SCENARIO_TOOL_TIMEOUT_SECONDS = 120.0
"""Default cap on a scenario tool body, so a stalled call (a judge HTTP request that
hangs) is cancelled and the agent told, rather than the agent waiting on it for the
rest of the round. A scenario sets its own through ``scenario_tool_timeout_s``. The
base communication tools are not capped."""


class ScenarioTool(NamedTuple):
    """A scenario-specific tool, offered to the agents whose ``tool_names`` include it."""

    name: str
    description: str
    executor: Callable[..., Awaitable[str | BaseModel]]
