"""Configuration knobs for the container_yard_stacking scenario.

Controls the per-round inspection-window budget, case shuffling seed,
round count, postmortem discussion phase, and per-character drop noise on
the link channel. Round difficulty (whether a given round has a blocker
on the target tier) is not a user knob — it is determined by a fixed
internal proportion shuffled per seed in ``yard_cases.py``.
"""

from typing import Self

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs


class ContainerYardStackingKnobs(BaseKnobs):
    """Configuration knobs for the container_yard_stacking scenario.

    ``time_budget_seconds`` is the per-round character budget on the link
    channel: every character sent costs one simulated second, and the
    round fails when the running total reaches the budget.
    ``channel_noise_level`` is the per-character drop probability on the
    link channel.
    """

    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    time_budget_seconds: int
    seed: int
    channel_noise_level: float

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> Self:
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self
