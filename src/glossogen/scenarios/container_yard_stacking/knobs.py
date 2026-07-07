"""Configuration knobs for the container_yard_stacking scenario.

Controls the per-round inspection-window budget, case seed, round count,
postmortem discussion phase, channel noise, the warmup rounds forced to a
single container, the per-round batch-size distribution, and the yard size.
Also the optional two-team mode with mid-run crane-operator swap and the
intern mode.
"""

from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.channel_noise import NoiseReplacementMode
from glossogen.scenarios.container_yard_stacking.ids import DEFAULT_YARD_SLOT_COUNT


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

    Each round a batch of containers arrives in the yard's intake slots and
    must be relocated to assigned target bays. ``batch_size_values`` paired
    with ``batch_size_weights`` defines the per-round batch-size distribution
    (the two lists must be the same non-empty length). ``yard_slot_count`` is
    the number of slots in the yard; it must hold the batch plus its target
    bays (``>= 2 * max(batch_size_values) + 2``). ``easy_round_numbers``
    forces those rounds to a single container (warmup).

    Two-team mode runs two isolated teams (spotter / planner / crane on
    ``link_a`` / ``link_b``) on identical cases each round. ``swap_round``
    swaps the two teams' crane operators after that round's main phase ends
    and clears link history.
    """

    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
    round_time_budget_seconds: int  # pyright: ignore[reportIncompatibleVariableOverride]
    seed: int
    channel_noise_level: float
    noise_replacement_mode: NoiseReplacementMode = NoiseReplacementMode.MASK
    easy_round_numbers: frozenset[int]
    batch_size_values: list[int]
    batch_size_weights: list[int]
    yard_slot_count: int = DEFAULT_YARD_SLOT_COUNT
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
    def _validate_batch_size_distribution(self) -> Self:
        if len(self.batch_size_values) == 0:
            raise ValueError("batch_size_values must be non-empty")
        if len(self.batch_size_values) != len(self.batch_size_weights):
            raise ValueError(
                f"batch_size_values and batch_size_weights must have the same length "
                f"(got {len(self.batch_size_values)} values and "
                f"{len(self.batch_size_weights)} weights)"
            )
        if any(value < 1 for value in self.batch_size_values):
            raise ValueError(f"batch_size_values must all be >= 1 (got {self.batch_size_values})")
        if any(weight <= 0 for weight in self.batch_size_weights):
            raise ValueError(f"batch_size_weights must all be > 0 (got {self.batch_size_weights})")
        return self

    @model_validator(mode="after")
    def _validate_yard_capacity(self) -> Self:
        max_batch = max(self.batch_size_values)
        if self.yard_slot_count < 2 * max_batch + 2:
            raise ValueError(
                f"yard_slot_count must be >= 2 * max(batch_size_values) + 2 "
                f"(got yard_slot_count={self.yard_slot_count}, max batch={max_batch})"
            )
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
