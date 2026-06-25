"""Configuration knobs for the container_yard_stacking scenario.

Controls the per-round inspection-window budget, case shuffling seed,
round count, postmortem discussion phase, channel noise, the set of
warmup rounds forced to a single delivery, and the optional two-team
mode with mid-run crane-operator swap. Per-step blocker placement
(whether a given delivery's target tier is already occupied) is not a
user knob — it is determined by a fixed internal proportion shuffled
per seed in ``yard_cases.py``.
"""

from typing import Self

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs
from schmidt.scenarios.channel_noise import NoiseReplacementMode


class ContainerYardStackingKnobs(BaseKnobs):
    """Configuration knobs for the container_yard_stacking scenario.

    ``round_time_budget_seconds`` is the per-round character budget on the
    link channel: every character sent costs one simulated second, and the
    round fails when the running total reaches the budget.
    ``channel_noise_level`` is the per-character drop probability on the
    link channel. ``noise_replacement_mode`` selects what each dropped
    character becomes: ``mask`` replaces it with ``_`` (erasure channel),
    ``random_letter`` replaces it with a different random letter leaving no
    marker (substitution channel).

    Two-team mode runs two isolated teams (yard / planner / crane on
    ``link_a`` / ``link_b``) on identical cases each round.
    ``swap_round`` swaps the two teams' crane operators after that
    round's main phase ends and clears link history so the new pairings
    must re-establish their protocol. ``announce_swap`` toggles an
    in-channel system message announcing the swap.
    ``postmortem_after_swap`` controls whether postmortem stays enabled
    after the swap fires.
    ``easy_round_numbers`` is the set of round numbers forced to a single
    delivery (single-step warmup cases) so agents learn the basic
    deliver / lift protocol before facing multi-container coordination.
    Every other round draws its step count from the configurable weighted
    distribution (``step_count_values`` paired with ``step_count_weights``).
    Each round is built from an independent per-round RNG, so toggling a
    round in or out of this set never shifts the case stream for any other
    round under a fixed ``seed``. Set to an empty list to disable the
    warmup constraint entirely.
    ``step_count_values`` and ``step_count_weights`` define the per-round
    delivery-count distribution: a non-easy round draws one value from
    ``step_count_values`` with the corresponding weight in
    ``step_count_weights`` (the two lists must be the same non-empty
    length). For example values ``[1, 2, 3, 4, 5]`` with weights
    ``[20, 25, 20, 15, 15]`` yields a mean of about 2.65 deliveries.
    """

    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    round_time_budget_seconds: int  # pyright: ignore[reportIncompatibleVariableOverride]
    seed: int
    channel_noise_level: float
    noise_replacement_mode: NoiseReplacementMode = NoiseReplacementMode.MASK
    easy_round_numbers: frozenset[int]
    step_count_values: list[int]
    step_count_weights: list[int]
    two_teams: bool = False
    swap_round: int | None = None
    announce_swap: bool = False
    postmortem_after_swap: bool = True
    intern_enabled: bool = False
    intern_join_round: int | None = None
    intern_takeover_round: int | None = None

    @model_validator(mode="after")
    def _validate_channel_noise_level(self) -> Self:
        if not 0.0 <= self.channel_noise_level <= 1.0:
            raise ValueError(
                f"channel_noise_level must be in [0.0, 1.0] (got {self.channel_noise_level})"
            )
        return self

    @model_validator(mode="after")
    def _validate_step_count_distribution(self) -> Self:
        if len(self.step_count_values) == 0:
            raise ValueError("step_count_values must be non-empty")
        if len(self.step_count_values) != len(self.step_count_weights):
            raise ValueError(
                f"step_count_values and step_count_weights must have the same length "
                f"(got {len(self.step_count_values)} values and "
                f"{len(self.step_count_weights)} weights)"
            )
        if any(value < 1 for value in self.step_count_values):
            raise ValueError(f"step_count_values must all be >= 1 (got {self.step_count_values})")
        if any(weight <= 0 for weight in self.step_count_weights):
            raise ValueError(f"step_count_weights must all be > 0 (got {self.step_count_weights})")
        return self

    @model_validator(mode="after")
    def _validate_swap_round(self) -> Self:
        if self.swap_round is None:
            return self
        if not self.two_teams:
            raise ValueError("swap_round requires two_teams=true")
        if self.swap_round < 1 or self.swap_round >= self.round_count:
            raise ValueError(
                f"swap_round must satisfy 1 <= swap_round < round_count "
                f"(got swap_round={self.swap_round}, round_count={self.round_count})"
            )
        return self

    @model_validator(mode="after")
    def _validate_intern_mode(self) -> Self:
        if self.intern_enabled and self.two_teams:
            raise ValueError("intern_enabled is incompatible with two_teams")
        if self.intern_enabled:
            if self.intern_join_round is None or self.intern_takeover_round is None:
                raise ValueError(
                    "intern_enabled requires intern_join_round and intern_takeover_round"
                )
            if self.intern_join_round < 1 or self.intern_join_round > self.round_count:
                raise ValueError(
                    f"intern_join_round must be in [1, round_count] "
                    f"(got {self.intern_join_round})"
                )
            if self.intern_takeover_round <= self.intern_join_round:
                raise ValueError("intern_takeover_round must be > intern_join_round")
            if self.intern_takeover_round > self.round_count:
                raise ValueError("intern_takeover_round must be <= round_count")
        return self
