"""Models representing the mutable state of a running simulation and per-turn routing decisions."""

from pydantic import BaseModel

from schmidt.models.message import SimulationMessage


class TurnDecision(BaseModel):
    """Specifies which agent should act next, on which channel, and in which scenario round."""

    agent_id: str
    channel_id: str
    round_number: int


class SimulationState(BaseModel):
    """Snapshot of the simulation at a given point in time, tracking the current turn,
    all messages exchanged on each channel, and the set of agents still participating.

    Attributes:
        turn_number: Number of turns completed so far (0 before the first turn).
        messages_by_channel: All messages exchanged on each channel up to this point.
        active_agent_ids: Agents still participating in the simulation.
    """

    turn_number: int
    messages_by_channel: dict[str, list[SimulationMessage]]
    active_agent_ids: list[str]
