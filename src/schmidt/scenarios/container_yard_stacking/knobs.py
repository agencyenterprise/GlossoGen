"""Configuration knobs for the container_yard_stacking scenario.

Controls the per-round communication budget, case shuffling seed, round
count, postmortem discussion, hard-case fraction, channel noise level, and
the LLM judge used by both the truck-destination judge and the crane move
judge.
"""

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs


class ContainerYardStackingKnobs(BaseKnobs):
    """Configuration knobs for the container_yard_stacking scenario.

    ``time_budget_seconds`` is the per-round character budget on the
    coordination channel: every character sent costs one simulated second,
    and the round fails when the running total exceeds the budget.
    ``hard_case_fraction`` is the probability that a given round's target
    slot is buried under one blocker container (requiring a two-step crane
    plan). ``judge_model`` / ``judge_provider`` select the LLM used by both
    yard judges. ``channel_noise_level`` is the per-character drop
    probability on the coordination channel.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    time_budget_seconds: int
    seed: int
    hard_case_fraction: float
    channel_noise_level: float

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> "ContainerYardStackingKnobs":
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_hard_case_fraction(self) -> "ContainerYardStackingKnobs":
        if not 0.0 <= self.hard_case_fraction <= 1.0:
            raise ValueError(
                f"hard_case_fraction must be in [0.0, 1.0] (got {self.hard_case_fraction})"
            )
        return self
