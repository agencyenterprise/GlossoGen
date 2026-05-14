"""Helpers for reading per-round success from ``RoundResultRecorded`` events.

Used by analysis viewers that need a flat ``dict[int, bool]`` of round →
success without re-deriving outcomes from scenario-specific events.
Multi-team scenarios collapse to "joint success" semantics (every team
must have succeeded for the round to count as a win).
"""

from schmidt.models.event import RoundResultRecorded, SimulationEvent


def per_round_joint_success(events: list[SimulationEvent]) -> dict[int, bool]:
    """Build per-round joint success from ``RoundResultRecorded`` events.

    Single-team runs return the team's per-round success boolean.
    Multi-team runs return ``True`` only when every team succeeded
    that round (matches the streamlit viewer's prior semantics).
    Rounds with no ``RoundResultRecorded`` event are omitted.
    """
    by_round: dict[int, list[bool]] = {}
    for event in events:
        if isinstance(event, RoundResultRecorded):
            by_round.setdefault(event.round_number, []).append(event.success)
    return {round_number: all(successes) for round_number, successes in by_round.items()}
