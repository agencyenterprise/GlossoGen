"""Configuration knobs for the orbital_anomaly scenario.

Controls the per-anomaly communication budget, case-generation seed, round
count, postmortem debrief phase, channel noise, the set of warmup rounds
forced to a single fault, and the per-round fault-count distribution.
"""

from typing import Self

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs


class OrbitalAnomalyKnobs(BaseKnobs):
    """Configuration knobs for the orbital_anomaly scenario.

    ``round_time_budget_seconds`` is the per-anomaly character budget on the
    comm loop: every character sent costs one simulated second, and the
    anomaly is lost when the running total exceeds the budget.
    ``channel_noise_level`` is the per-character drop probability on the
    comm loop. ``cipher_enabled`` toggles the per-round secret rotation that
    maps each fault to a different fault's procedure template; when false the
    offset is forced to zero so every fault maps to its own (coherent)
    procedure. ``easy_round_numbers`` lists round numbers forced to a single
    fault (warmup). ``fault_count_values`` paired with
    ``fault_count_weights`` defines the per-round weighted distribution of
    how many faults cascade in an anomaly; the two lists must be the same
    non-empty length.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    round_time_budget_seconds: int  # pyright: ignore[reportIncompatibleVariableOverride]
    seed: int
    channel_noise_level: float
    cipher_enabled: bool
    easy_round_numbers: frozenset[int]
    fault_count_values: list[int]
    fault_count_weights: list[int]

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> Self:
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_fault_count_distribution(self) -> Self:
        if len(self.fault_count_values) == 0:
            raise ValueError("fault_count_values must be non-empty")
        if len(self.fault_count_values) != len(self.fault_count_weights):
            raise ValueError(
                f"fault_count_values and fault_count_weights must have the same length "
                f"(got {len(self.fault_count_values)} values and "
                f"{len(self.fault_count_weights)} weights)"
            )
        if any(value < 1 for value in self.fault_count_values):
            raise ValueError(f"fault_count_values must all be >= 1 (got {self.fault_count_values})")
        if any(weight <= 0 for weight in self.fault_count_weights):
            raise ValueError(
                f"fault_count_weights must all be > 0 (got {self.fault_count_weights})"
            )
        return self
