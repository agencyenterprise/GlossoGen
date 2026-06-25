"""Configuration knobs for the satellite contact window scenario.

Controls the per-round contact-window budget, case generation seed, round
count, postmortem discussion, per-case pattern count, channel noise level,
and the LLM judge.
"""

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs
from schmidt.scenarios.channel_noise import NoiseReplacementMode


class SatelliteContactWindowKnobs(BaseKnobs):
    """Configuration knobs for the satellite contact window scenario.

    ``round_time_budget_seconds`` is the fixed per-round budget applied to every
    case: every character sent on the shared ``link`` channel costs one
    simulated second, and if the running total exceeds the budget the
    contact window closes and the round fails. ``seed`` controls the random
    selection of telemetry patterns, wait-time parameters, and authorization
    envelopes into round cases. ``postmortem_enabled`` controls whether a
    shared discussion phase follows each round.
    ``postmortem_disabled_at_start`` disables the postmortem phase from the
    very first round; used by the replace-agent flow to drop the postmortem
    channel for the rest of a resumed simulation. ``pattern_count_min`` /
    ``pattern_count_max`` bound the per-round telemetry-pattern count drawn
    from the catalog. ``channel_noise_level`` is the per-character drop
    probability applied to messages on the ``link`` channel only (postmortem
    stays clean); at ``0.0`` the channel is lossless, at ``1.0`` every
    character is dropped. ``noise_replacement_mode`` selects what each dropped
    character becomes: ``mask`` replaces it with ``_`` (erasure channel),
    ``random_letter`` replaces it with a different random letter leaving no
    marker (substitution channel). ``judge_model`` and ``judge_provider``
    specify the LLM used to evaluate whether the operator's submitted command
    sequence satisfies the round-success criteria.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    round_time_budget_seconds: int  # pyright: ignore[reportIncompatibleVariableOverride]
    seed: int
    pattern_count_min: int
    pattern_count_max: int
    channel_noise_level: float
    noise_replacement_mode: NoiseReplacementMode = NoiseReplacementMode.MASK

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> "SatelliteContactWindowKnobs":
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_round_time_budget_seconds(self) -> "SatelliteContactWindowKnobs":
        if self.round_time_budget_seconds <= 0:
            raise ValueError(
                f"round_time_budget_seconds must be > 0 (got {self.round_time_budget_seconds})"
            )
        return self

    @model_validator(mode="after")
    def _validate_round_count(self) -> "SatelliteContactWindowKnobs":
        if self.round_count < 1:
            raise ValueError(f"round_count must be >= 1 (got {self.round_count})")
        return self

    @model_validator(mode="after")
    def _validate_pattern_count_bounds(self) -> "SatelliteContactWindowKnobs":
        if self.pattern_count_min < 1:
            raise ValueError(f"pattern_count_min must be >= 1 (got {self.pattern_count_min})")
        if self.pattern_count_max < self.pattern_count_min:
            raise ValueError(
                f"pattern_count_max must be >= pattern_count_min "
                f"(got pattern_count_min={self.pattern_count_min}, "
                f"pattern_count_max={self.pattern_count_max})"
            )
        return self
