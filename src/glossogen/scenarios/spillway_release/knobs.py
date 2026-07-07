"""Configuration knobs for the spillway_release scenario.

Controls the per-round communication budget, case-generation seed, round
count, postmortem discussion phase, channel noise, the set of warmup
rounds, the dam physics constants (gate count, per-gate release rate,
reservoir band), the operating-day horizon, and the per-round archetype
mix. Round scoring is fully deterministic, so there is no LLM judge knob.
"""

from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.channel_noise import NoiseReplacementMode

# Archetype weights are positional; this is the fixed order they map to.
ARCHETYPE_ORDER = ("hold", "time_it", "keep_closed", "evacuate")


class SpillwayReleaseKnobs(BaseKnobs):
    """Configuration knobs for the spillway_release scenario.

    ``round_time_budget_seconds`` is the per-round character budget on the
    ops channel: every character sent costs one simulated second and the
    round fails when the running total reaches the budget.
    ``channel_noise_level`` is the per-character drop probability on the
    ops channel; ``noise_replacement_mode`` selects what each dropped
    character becomes (``mask`` = visible erasure, ``random_letter`` =
    silent substitution).

    ``gate_count`` is the number of identical spillway gates; each open
    gate sheds ``release_per_gate_per_hour`` percentage points of reservoir
    capacity per hour. ``max_level`` is the collapse threshold (the dam
    fails above it) and ``min_level`` is the shortage threshold (the round
    fails below it); the operator must land the end-of-round level inside
    ``[min_level, max_level]``. ``day_end_hours`` is the end of the
    operating horizon used for park-occupancy and release windows.

    ``easy_round_numbers`` is the set of rounds forced to the ``hold``
    archetype (calm warmups). Every other round draws its archetype from
    ``archetype_weights`` (positional, paired with
    :data:`ARCHETYPE_ORDER`: hold, time_it, keep_closed, evacuate). Each
    round is built from an independent per-round RNG so toggling one round
    never shifts another round's case under a fixed ``seed``.
    """

    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    round_time_budget_seconds: int  # pyright: ignore[reportIncompatibleVariableOverride]
    seed: int
    channel_noise_level: float
    noise_replacement_mode: NoiseReplacementMode = NoiseReplacementMode.MASK
    easy_round_numbers: frozenset[int]
    gate_count: int
    release_per_gate_per_hour: int
    max_level: int
    min_level: int
    day_end_hours: float
    archetype_weights: list[int]

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> Self:
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_reservoir_band(self) -> Self:
        if self.min_level >= self.max_level:
            raise ValueError(
                f"min_level must be < max_level (got min_level={self.min_level}, "
                f"max_level={self.max_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_gate_physics(self) -> Self:
        if self.gate_count < 1:
            raise ValueError(f"gate_count must be >= 1 (got {self.gate_count})")
        if self.release_per_gate_per_hour < 1:
            raise ValueError(
                f"release_per_gate_per_hour must be >= 1 (got {self.release_per_gate_per_hour})"
            )
        return self

    @model_validator(mode="after")
    def _validate_day_end_hours(self) -> Self:
        if not 0.0 < self.day_end_hours <= 24.0:
            raise ValueError(f"day_end_hours must be in (0.0, 24.0] (got {self.day_end_hours})")
        return self

    @model_validator(mode="after")
    def _validate_archetype_weights(self) -> Self:
        if len(self.archetype_weights) != len(ARCHETYPE_ORDER):
            raise ValueError(
                f"archetype_weights must have exactly {len(ARCHETYPE_ORDER)} entries "
                f"(order: {', '.join(ARCHETYPE_ORDER)}); got {len(self.archetype_weights)}"
            )
        if any(weight < 0 for weight in self.archetype_weights):
            raise ValueError(f"archetype_weights must all be >= 0 (got {self.archetype_weights})")
        if sum(self.archetype_weights) <= 0:
            raise ValueError("archetype_weights must sum to a positive value")
        return self
