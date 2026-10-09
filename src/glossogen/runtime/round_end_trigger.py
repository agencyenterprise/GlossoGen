"""The triggers the game clock itself ends a round or a phase with.

A scenario ends a round with a trigger of its own through
``get_early_round_end_trigger``; those are free strings. The values here are the
platform's, written to ``RoundEnded``, ``PostmortemEnded`` and ``RoundAdvanced``,
and are what a scenario's ``on_round_ended`` and the round-ended metrics compare
against.
"""

from enum import StrEnum


class RoundEndTrigger(StrEnum):
    """Why the game clock ended a round, a postmortem phase, or opened a round."""

    ALL_AGENTS_IDLE = "all_agents_idle"
    """Every agent went idle and the idle floor elapsed."""
    ROUND_TIMEOUT = "round_timeout"
    """The round's wall-clock limit passed."""
    POSTMORTEM_TIMEOUT = "postmortem_timeout"
    """The postmortem phase's wall-clock limit passed."""
    ALL_AGENTS_WAITING = "all_agents_waiting"
    """Every agent was parked with no deadline, in a scenario that ends the round then."""
    ALL_AGENTS_FINISHED = "all_agents_finished"
    """Every parked agent was waiting for the next round."""
    FORK_AFTER_ROUND = "fork_after_round"
    """A ``RoundAdvanced`` recorded when a fork opens the round after its source's last."""
    SIMULATION_START = "simulation_start"
    """The ``RoundAdvanced`` that opens round 1."""


PLATFORM_TRIGGER_VALUES: frozenset[str] = frozenset(trigger.value for trigger in RoundEndTrigger)
