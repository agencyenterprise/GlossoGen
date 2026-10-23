"""Per-agent model, provider, and role, one column family per attribute.

This is the generic form of the per-role model columns a hand-written exporter
spells out (`field_observer_model`, `engineer_model`, and so on). Keying by
`agent_id` needs no table mapping ids to roles, and it covers a scenario nobody
anticipated.

The roster also lands here for a second reason: on most runs the per-agent CSV
frame is empty, because a metric reports per-agent numbers only when it has them.
Carrying model and provider per agent on the run row means the roster survives
regardless.

A run swapped mid-flight registers the same `agent_id` more than once under
different models. The first registration wins the column, and the swap itself is
recorded in the lineage columns and in the event log.
"""

from typing import NamedTuple, Protocol

from glossogen.run_export.csv_cell_text import render_cell
from glossogen.server.runs.models import AgentModelSummary

AGENT_MODEL_COLUMN_PREFIX = "agent_model."
AGENT_PROVIDER_COLUMN_PREFIX = "agent_provider."
AGENT_ROLE_COLUMN_PREFIX = "agent_role."


def agent_identity_cells(agent_models: list[AgentModelSummary]) -> dict[str, str]:
    """Return the per-agent model, provider, and role cells for one run."""
    cells: dict[str, str] = {}
    for agent in agent_models:
        model_column = f"{AGENT_MODEL_COLUMN_PREFIX}{agent.agent_id}"
        if model_column in cells:
            continue
        cells[model_column] = render_cell(text=agent.model)
        cells[f"{AGENT_PROVIDER_COLUMN_PREFIX}{agent.agent_id}"] = render_cell(text=agent.provider)
        cells[f"{AGENT_ROLE_COLUMN_PREFIX}{agent.agent_id}"] = render_cell(text=agent.role_name)
    return cells


def agent_model_by_id(agent_models: list[AgentModelSummary]) -> dict[str, AgentModelSummary]:
    """Index a run's agents by id, keeping the first registration of each."""
    indexed: dict[str, AgentModelSummary] = {}
    for agent in agent_models:
        if agent.agent_id in indexed:
            continue
        indexed[agent.agent_id] = agent
    return indexed


class RosterAgent(Protocol):
    """What a roster entry carries about an agent, whichever record holds it."""

    @property
    def role_name(self) -> str:
        """The agent's role."""
        ...

    @property
    def model(self) -> str:
        """The model the agent ran on."""
        ...

    @property
    def provider(self) -> str:
        """The provider serving that model."""
        ...


class AgentIdentity(NamedTuple):
    """An agent's role, model and provider, as a row's identity cells hold them."""

    role: str
    model: str
    provider: str


def roster_identity(agent: RosterAgent | None) -> AgentIdentity:
    """Return an agent's role, model and provider, all empty when the roster lacks it.

    Empty reads as the roster not carrying the agent, which is the case for an id
    only a metric or a message named.
    """
    if agent is None:
        return AgentIdentity(role="", model="", provider="")
    return AgentIdentity(role=agent.role_name, model=agent.model, provider=agent.provider)
