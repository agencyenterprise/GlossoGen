"""Refuse to rebuild a seat whose harness cannot take a reconstructed history.

Every fork, replacement and resume rebuilds each kept seat's history from the
event log as pydantic-ai messages and hands it to the seat's runner. Only the
pydantic-ai harness accepts one; a seat that ran under another harness keeps
its conversation in that harness's own state. So a derivation that keeps such a
seat is refused before anything is cloned, and replacing the seat is the way to
continue the run without it.
"""

from collections.abc import Iterable, Mapping

from glossogen.config_overrides import ResolvedAgentModel
from glossogen.models.event import AgentRegistered, AgentSwappedMidRun, SimulationEvent
from glossogen.runners.harness_names import PYDANTIC_AI_HARNESS_NAME


def seat_harnesses(events: Iterable[SimulationEvent]) -> dict[str, str]:
    """The harness each agent ran under last: its latest registration's or swap's."""
    harnesses: dict[str, str] = {}
    for event in events:
        if isinstance(event, AgentRegistered):
            harnesses[event.agent_id] = event.harness
        elif isinstance(event, AgentSwappedMidRun):
            harnesses[event.agent_id] = event.new_harness
    return harnesses


def refuse_kept_seats_under_other_harnesses(
    harnesses: Mapping[str, str],
    replaced_agent_id: str | None,
) -> None:
    """Raise ValueError when a seat keeping its history ran under a non-pydantic-ai harness.

    ``harnesses`` maps each agent to the harness in force at the boundary;
    ``replaced_agent_id`` is the seat the derivation restarts, which is exempt.
    """
    kept_elsewhere = sorted(
        f"{agent_id} ({harness})"
        for agent_id, harness in harnesses.items()
        if agent_id != replaced_agent_id and harness != PYDANTIC_AI_HARNESS_NAME
    )
    if kept_elsewhere:
        raise ValueError(
            "this run cannot be continued with these seats keeping their history: "
            f"{', '.join(kept_elsewhere)}. Their conversation lives in their harness, not "
            f"in a history {PYDANTIC_AI_HARNESS_NAME} can rebuild; replace the seat instead."
        )


def require_fresh_seat_harness(harness: str, seat_description: str) -> None:
    """Raise ValueError unless ``harness`` accepts a seat seeded with a reconstructed history.

    A scheduled swap, a replacement and a cross-run import all hand the new
    runner a history rebuilt from the event log as pydantic-ai messages. Only
    the pydantic-ai harness takes one; any other harness starts a seat fresh.
    """
    if harness == PYDANTIC_AI_HARNESS_NAME:
        return
    raise ValueError(
        f"{seat_description} would start under harness {harness!r} with a reconstructed "
        f"history, which only {PYDANTIC_AI_HARNESS_NAME} accepts; use that harness for it."
    )


def require_rebuilt_seats_on_pydantic_ai(seats: Mapping[str, ResolvedAgentModel]) -> None:
    """Raise ValueError unless every seat a resumed run rebuilds resolves to pydantic-ai.

    ``seats`` maps each agent to what it will run under. A resumed run, and every
    fork, hands every seat a history rebuilt from the log, so a seat named onto
    another harness by a knob override would be refused only once its runner
    started, after the run directory was claimed.
    """
    for agent_id, resolved in sorted(seats.items()):
        require_fresh_seat_harness(harness=resolved.harness, seat_description=agent_id)
