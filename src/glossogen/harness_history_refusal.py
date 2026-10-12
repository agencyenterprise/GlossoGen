"""Refuse to rebuild a seat whose harness cannot take a reconstructed history.

Every fork, replacement and resume rebuilds each kept seat's history from the
event log as pydantic-ai messages and hands it to the seat's runner. Only the
pydantic-ai harness accepts one; a seat that ran under another harness keeps
its conversation in that harness's own state, and its log holds no model
responses to rebuild from. So a derivation that keeps such a seat is refused
before anything is cloned, and so is importing one; replacing the seat is the
way to continue the run without it.
"""

from collections.abc import Iterable, Mapping

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


def require_history_accepting_harness(harness: str, seat_description: str) -> None:
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


def require_rebuilt_seats_on_pydantic_ai(harnesses: Mapping[str, str]) -> None:
    """Raise ValueError unless every seat a resumed run rebuilds resolves to pydantic-ai.

    ``harnesses`` maps each agent to the harness it will run under. A resumed
    run, and every fork, hands every seat a history rebuilt from the log, so a
    seat named onto another harness by a knob override would be refused only
    once its runner started, after the run directory was claimed.
    """
    for agent_id, harness in sorted(harnesses.items()):
        require_history_accepting_harness(harness=harness, seat_description=agent_id)


def refuse_import_of_seat_without_responses(harness: str, agent_id: str) -> None:
    """Raise ValueError when the seat to import from source B ran under a non-pydantic-ai harness.

    A seat run by an agent CLI connected over MCP logs its tool calls but no
    model responses, so its log rebuilds into no history to import.
    """
    if harness == PYDANTIC_AI_HARNESS_NAME:
        return
    raise ValueError(
        f"{agent_id} ran under harness {harness!r} in source B, which logs no model "
        "responses; its history cannot be rebuilt for import. Import a seat that ran "
        f"under {PYDANTIC_AI_HARNESS_NAME}."
    )
