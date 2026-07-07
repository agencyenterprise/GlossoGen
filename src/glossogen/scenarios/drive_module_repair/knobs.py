"""Configuration knobs for the drive_module_repair scenario.

Controls the per-round communication budget, case-generation seed, round
count, postmortem discussion, channel noise, the warmup rounds, the
per-round replacement-count distribution, and the LLM judge that scores
each free-text replacement against the expected component / tool / torque /
calibration.
"""

from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.channel_noise import NoiseReplacementMode


class DriveModuleRepairKnobs(BaseKnobs):
    """Configuration knobs for the drive_module_repair scenario.

    ``round_time_budget_seconds`` is the per-round character budget on the
    bay channel: every character sent costs one simulated second and the
    round fails when the running total reaches the budget.
    ``channel_noise_level`` is the per-character drop probability on the bay
    channel; ``noise_replacement_mode`` selects what each dropped character
    becomes (``mask`` = visible erasure, ``random_letter`` = silent
    substitution). ``judge_model`` / ``judge_provider`` select the LLM that
    judges each replacement action. ``easy_round_numbers`` forces a single
    module with a single faulty component (warmup). Every other round draws a
    module count from ``module_count_values`` weighted by
    ``module_count_weights``, and for each module draws a faulty-component
    count from ``replacements_count_values`` weighted by
    ``replacements_count_weights``. Modules are serviced in a fixed canonical
    order (module-1 first); within each module, components are replaced in
    access-depth order. Each round is built from an independent per-round RNG
    so toggling one round never shifts another round's case under a fixed
    ``seed``.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    round_time_budget_seconds: int  # pyright: ignore[reportIncompatibleVariableOverride]
    seed: int
    channel_noise_level: float
    noise_replacement_mode: NoiseReplacementMode = NoiseReplacementMode.MASK
    easy_round_numbers: frozenset[int]
    module_count_values: list[int]
    module_count_weights: list[int]
    replacements_count_values: list[int]
    replacements_count_weights: list[int]

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> Self:
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_module_distribution(self) -> Self:
        _validate_count_distribution(
            values=self.module_count_values,
            weights=self.module_count_weights,
            name="module_count",
        )
        return self

    @model_validator(mode="after")
    def _validate_replacements_distribution(self) -> Self:
        _validate_count_distribution(
            values=self.replacements_count_values,
            weights=self.replacements_count_weights,
            name="replacements_count",
        )
        return self


def _validate_count_distribution(values: list[int], weights: list[int], name: str) -> None:
    """Validate a paired (values, weights) count distribution; raise on any problem."""
    if len(values) == 0:
        raise ValueError(f"{name}_values must be non-empty")
    if len(values) != len(weights):
        raise ValueError(
            f"{name}_values and {name}_weights must have the same length "
            f"(got {len(values)} values and {len(weights)} weights)"
        )
    if any(value < 1 for value in values):
        raise ValueError(f"{name}_values must all be >= 1 (got {values})")
    if any(weight <= 0 for weight in weights):
        raise ValueError(f"{name}_weights must all be > 0 (got {weights})")
