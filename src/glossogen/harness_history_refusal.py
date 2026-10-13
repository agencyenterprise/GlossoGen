"""Refuse to seed a seat whose harness cannot take a reconstructed history.

Every fork, replacement and resume rebuilds each kept seat's history from the
event log as pydantic-ai messages and hands it to the seat's runner. Only the
pydantic-ai harness accepts one; every other harness starts its seat fresh. A
seat that ran under a CLI harness has a rebuildable log (one tool-call turn
per call), so continuing it is allowed once it is named onto pydantic-ai,
with ``agents.<id>.harness=`` or a ``model_overrides`` entry.
"""

from collections.abc import Mapping

from glossogen.runners.harness_names import PYDANTIC_AI_HARNESS_NAME


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
    seat pinned to or named onto another harness would be refused only once
    its runner started, after the run directory was claimed. A fork keeps each
    seat on the harness it ran under, so a seat that ran in a CLI is named
    onto pydantic-ai through a ``model_overrides`` entry to continue it.
    """
    for agent_id, harness in sorted(harnesses.items()):
        require_history_accepting_harness(harness=harness, seat_description=agent_id)
