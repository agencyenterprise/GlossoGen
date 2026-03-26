"""Protocol for scenarios with mutable world state that evolves between rounds.

Defines the ``SimulationStateProtocol`` that stateful scenarios implement alongside
``SimulationScenario``. The hub checks for this protocol at runtime and calls its
methods during round transitions to advance state, capture ground truth, and deliver
filtered observations to agents.
"""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class AgentAction(BaseModel):
    """A structured action submitted by an agent to modify world state.

    Attributes:
        action_type: Identifier for the kind of action (e.g. ``allocate_effort``).
        parameters: Action-specific key-value pairs.
    """

    action_type: str
    parameters: dict[str, Any]


class ActionOutcome(BaseModel):
    """Result of applying an agent action to the world state.

    Attributes:
        success: Whether the action was applied successfully.
        agent_visible_result: Description returned to the acting agent.
    """

    success: bool
    agent_visible_result: str


class RoundTransitionReport(BaseModel):
    """Summary of world state changes that occurred between rounds.

    Attributes:
        round_number: The round that just completed its transition.
        changes: Human-readable list of changes applied.
        external_events_applied: External events injected during this transition.
        summary: One-line summary of the transition for logging.
    """

    round_number: int
    changes: list[str]
    external_events_applied: list[str]
    summary: str


@runtime_checkable
class SimulationStateProtocol(Protocol):
    """Protocol for scenarios that maintain mutable world state.

    The ``SimulationHub`` checks ``isinstance(scenario, SimulationStateProtocol)``
    at runtime. When satisfied, the hub calls ``advance_round`` between rounds,
    logs ground truth snapshots, and delivers filtered observations to each agent.
    """

    def get_agent_observation(self, agent_id: str) -> dict[str, Any]:
        """Return the state visible to a specific agent.

        Each agent may see a different slice of the world state
        depending on their role and information access.
        """
        ...

    def apply_agent_action(self, agent_id: str, action: AgentAction) -> ActionOutcome:
        """Apply a structured action from an agent to the world state.

        Returns an ``ActionOutcome`` describing what happened, which gets
        logged and optionally fed back to the agent.
        """
        ...

    def advance_round(self, round_number: int) -> RoundTransitionReport:
        """Update world state between rounds.

        Resolves pending actions, applies stochastic dynamics,
        injects external events, and returns a summary of what changed.
        """
        ...

    def get_ground_truth(self) -> dict[str, Any]:
        """Return the complete unfiltered state for logging and evaluation.

        Never shown to agents. Used by the experimenter and evaluators
        for computing accuracy metrics post-hoc.
        """
        ...
