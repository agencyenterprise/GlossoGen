"""Models representing the mutable state of a running simulation and per-turn routing decisions."""

from pydantic import BaseModel

from schmidt.models.message import SimulationMessage


class TurnDecision(BaseModel):
    """Specifies which agent should act next and in which scenario round.

    Attributes:
        agent_id: Which agent takes the next turn.
        round_number: Scenario round this turn belongs to.
        excluded_tool_names: Tool names to hide from the agent for this turn.
            Include "pass_turn" to force the agent to speak.
        max_tokens: Maximum tokens the LLM may generate for this turn.
    """

    agent_id: str
    round_number: int
    excluded_tool_names: list[str]
    max_tokens: int


class SimulationState(BaseModel):
    """Snapshot of the simulation at a given point in time, tracking the current turn,
    all messages exchanged on each channel, and the set of agents still participating.

    Attributes:
        turn_number: Number of turns completed so far (0 before the first turn).
        messages_by_channel: All messages exchanged on each channel up to this point.
        active_agent_ids: Agents still participating in the simulation.
        last_turn_passed: True if the previous agent sent no messages, False otherwise.
    """

    turn_number: int
    messages_by_channel: dict[str, list[SimulationMessage]]
    active_agent_ids: list[str]
    last_turn_passed: bool
