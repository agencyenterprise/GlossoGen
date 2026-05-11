"""Helpers for reading round-end trigger information from a simulation event log.

Scenario-agnostic. Used by generic evaluators that flag rounds by how their
main phase terminated (see ``round_ended_idle_evaluator`` and
``round_ended_timeout_evaluator``).
"""

from schmidt.models.event import RoundAdvanced, RoundEnded, SimulationEvent


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
