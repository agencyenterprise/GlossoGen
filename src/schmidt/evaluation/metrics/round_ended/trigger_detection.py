"""Helpers for reading round-end trigger information from a simulation event log.

Scenario-agnostic. Used by generic evaluators that flag rounds by how their
main phase terminated (see ``round_ended_idle_evaluator`` and
``round_ended_timeout_evaluator``).
"""

from schmidt.models.event import (
    PostmortemEnded,
    PostmortemStarted,
    RoundAdvanced,
    RoundEnded,
    SimulationEvent,
)

_POSTMORTEM_TIMEOUT_TRIGGER = "postmortem_timeout"


def count_rounds(events: list[SimulationEvent]) -> int:
    """Return the highest round number seen in ``RoundAdvanced`` events."""
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced):
            if event.round_number > max_round:
                max_round = event.round_number
    return max_round


def find_round_end_triggers(events: list[SimulationEvent]) -> dict[int, str]:
    """Map ``round_number -> trigger`` from ``RoundEnded`` events."""
    triggers: dict[int, str] = {}
    for event in events:
        if isinstance(event, RoundEnded):
            triggers[event.round_number] = event.trigger
    return triggers


def count_postmortem_phases(events: list[SimulationEvent]) -> int:
    """Return the number of postmortem phases that ran, from ``PostmortemStarted`` events."""
    return sum(1 for event in events if isinstance(event, PostmortemStarted))


def find_postmortem_timeout_rounds(events: list[SimulationEvent]) -> set[int]:
    """Return the set of round numbers whose postmortem phase ended via wall-clock timeout.

    Reads ``PostmortemEnded`` events (authoritative; covers the final round) and
    falls back to ``RoundAdvanced(trigger='postmortem_timeout')`` for runs that
    predate the ``PostmortemEnded`` event — attributing each such advance to the
    round before it (the postmortem's round, since ``RoundAdvanced`` carries the
    incremented round number). The union is safe: both sources derive the trigger
    from the same phase-end decision, so they never disagree for a given round.
    """
    rounds: set[int] = set()
    for event in events:
        if isinstance(event, PostmortemEnded):
            if event.trigger == _POSTMORTEM_TIMEOUT_TRIGGER:
                rounds.add(event.round_number)
        elif isinstance(event, RoundAdvanced):
            if event.trigger == _POSTMORTEM_TIMEOUT_TRIGGER:
                rounds.add(event.round_number - 1)
    return rounds
