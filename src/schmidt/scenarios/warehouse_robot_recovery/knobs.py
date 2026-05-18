"""Configuration knobs for the warehouse robot recovery scenario.

Controls the per-round time budget, case shuffling seed, round count,
postmortem discussion, per-case fault count, channel noise level, and
the LLM judge.
"""

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs


class WarehouseRobotRecoveryKnobs(BaseKnobs):
    """Configuration knobs for the warehouse robot recovery scenario.

    ``round_time_budget_seconds`` is the fixed per-round budget applied to
    every case: every character sent on the shared radio channel costs one
    simulated second, and if the running total exceeds the budget the round
    fails. ``seed`` controls the random selection of faults, robot models,
    firmware states, and fleet modes into round cases. ``postmortem_enabled``
    controls whether a shared discussion phase follows each round.
    ``postmortem_disabled_at_start`` disables the postmortem phase from
    the very first round; used by the replace-agent flow to drop the
    postmortem channel for the rest of a resumed simulation.
    ``fault_count_min`` / ``fault_count_max`` bound the per-round fault
    count drawn from the catalog. ``channel_noise_level`` is the
    per-character drop probability applied to messages on the radio
    channel only (postmortem stays clean); at ``0.0`` the channel is
    lossless, at ``1.0`` every character is dropped. Dropped characters
    are replaced with ``_`` so agents can see where loss occurred.
    ``judge_model`` and ``judge_provider`` specify the LLM used to
    evaluate whether the floor associate's recovery action satisfies the
    eight round-success criteria.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    round_time_budget_seconds: int  # pyright: ignore[reportIncompatibleVariableOverride]
    seed: int
    fault_count_min: int
    fault_count_max: int
    channel_noise_level: float

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> "WarehouseRobotRecoveryKnobs":
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_fault_count_bounds(self) -> "WarehouseRobotRecoveryKnobs":
        if self.fault_count_min < 1:
            raise ValueError(f"fault_count_min must be >= 1 (got {self.fault_count_min})")
        if self.fault_count_max < self.fault_count_min:
            raise ValueError(
                f"fault_count_max must be >= fault_count_min "
                f"(got fault_count_min={self.fault_count_min}, "
                f"fault_count_max={self.fault_count_max})"
            )
        return self
