"""Configuration knobs for the spot_the_difference scenario.

Controls the grid size, the per-round object-count and difference-count
distributions, which difference kinds are enabled, the warmup rounds forced
to a single difference, the postmortem discussion phase, channel noise, the
optional per-round character budget, and the optional two-team competitive mode.

``round_time_budget_seconds`` is an optional hard cap: when positive, every
character a team sends on the link channel counts against it and a team that
reaches the cap is ineligible for that round; set it to ``-1`` (the default) to
disable the cap entirely. Either way the character count is tracked, and among
teams that find every difference the one with the fewest characters wins.
"""

from typing import Self

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.channel_noise import NoiseReplacementMode
from glossogen.scenarios.spot_the_difference.ids import DifferenceKind

_VALID_DIFFERENCE_KINDS = frozenset(kind.value for kind in DifferenceKind)


class SpotTheDifferenceKnobs(BaseKnobs):
    """Configuration knobs for the spot_the_difference scenario.

    Each round the environment generates a scene of objects on a
    ``grid_size`` x ``grid_size`` grid (each object a ``shape, color, size``
    bundle at a ``(column, row)`` cell) and a near-identical copy with exactly
    K planted differences drawn from ``difference_kinds``. ``object_count_*``
    sets the per-round object-count distribution, ``difference_count_*`` sets
    the per-round K distribution, and ``easy_round_numbers`` forces those
    rounds to K=1 (warmup). ``round_time_budget_seconds`` is the optional
    per-round link-channel character cap (``-1`` = no cap, the default).
    ``channel_noise_level`` is the
    per-character drop probability on the link channel and
    ``noise_replacement_mode`` selects what each dropped character becomes
    (``mask`` -> ``_`` erasure, ``random_letter`` -> a different random letter
    substitution).

    Two-team mode runs two isolated teams (each a left viewer on scene A and a
    right viewer on scene B, on ``link_a`` / ``link_b``) on the identical
    scene pair each round, so the per-round winner (fewest characters among
    teams that found every difference) can be announced as in-context
    reinforcement.

    ``shared_link`` (two-team only) puts both teams on a single shared link
    channel instead of the isolated ``link_a`` / ``link_b`` pair, so every
    viewer can read the other team's link messages; the postmortem channels
    stay per-team and private. Each team's character count still totals only its
    own members' messages (attributed by sender), and per-team language/char
    metrics collapse to one pooled measurement over the shared channel.

    ``all_must_submit`` (the default) makes both teammates submit their own
    answer: a team is scored only once both members call ``submit_differences``
    (the round is lost for any team where one member never submits), both
    answers are sent to the judge, and the team is eligible only if the two
    answers agree on the same full set of K differences with no false positives.
    When off, the first submission from either member locks and scores the team.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_time_budget_seconds: int  # pyright: ignore[reportIncompatibleVariableOverride]
    seed: int
    grid_size: int
    object_count_values: list[int]
    object_count_weights: list[int]
    difference_count_values: list[int]
    difference_count_weights: list[int]
    difference_kinds: list[str]
    easy_round_numbers: frozenset[int]
    channel_noise_level: float = Field(ge=0.0, le=1.0)
    noise_replacement_mode: NoiseReplacementMode = NoiseReplacementMode.MASK
    two_teams: bool = False
    shared_link: bool = False
    all_must_submit: bool = True

    @model_validator(mode="after")
    def _validate_object_count_distribution(self) -> Self:
        if len(self.object_count_values) == 0:
            raise ValueError("object_count_values must be non-empty")
        if len(self.object_count_values) != len(self.object_count_weights):
            raise ValueError(
                f"object_count_values and object_count_weights must have the same length "
                f"(got {len(self.object_count_values)} values and "
                f"{len(self.object_count_weights)} weights)"
            )
        if any(value < 1 for value in self.object_count_values):
            raise ValueError(
                f"object_count_values must all be >= 1 (got {self.object_count_values})"
            )
        if any(weight <= 0 for weight in self.object_count_weights):
            raise ValueError(
                f"object_count_weights must all be > 0 (got {self.object_count_weights})"
            )
        return self

    @model_validator(mode="after")
    def _validate_difference_count_distribution(self) -> Self:
        if len(self.difference_count_values) == 0:
            raise ValueError("difference_count_values must be non-empty")
        if len(self.difference_count_values) != len(self.difference_count_weights):
            raise ValueError(
                f"difference_count_values and difference_count_weights must have the same length "
                f"(got {len(self.difference_count_values)} values and "
                f"{len(self.difference_count_weights)} weights)"
            )
        if any(value < 1 for value in self.difference_count_values):
            raise ValueError(
                f"difference_count_values must all be >= 1 (got {self.difference_count_values})"
            )
        if any(weight <= 0 for weight in self.difference_count_weights):
            raise ValueError(
                f"difference_count_weights must all be > 0 (got {self.difference_count_weights})"
            )
        return self

    @model_validator(mode="after")
    def _validate_difference_kinds(self) -> Self:
        if len(self.difference_kinds) == 0:
            raise ValueError("difference_kinds must be non-empty")
        invalid = [kind for kind in self.difference_kinds if kind not in _VALID_DIFFERENCE_KINDS]
        if invalid:
            raise ValueError(
                f"difference_kinds entries must be one of {sorted(_VALID_DIFFERENCE_KINDS)} "
                f"(got invalid {invalid})"
            )
        return self

    @model_validator(mode="after")
    def _validate_shared_link(self) -> Self:
        if self.shared_link and not self.two_teams:
            raise ValueError(
                "shared_link requires two_teams=True (there is no other team to share with)"
            )
        return self

    @model_validator(mode="after")
    def _validate_budget(self) -> Self:
        if self.round_time_budget_seconds != -1 and self.round_time_budget_seconds <= 0:
            raise ValueError(
                f"round_time_budget_seconds must be > 0, or -1 for no budget "
                f"(got {self.round_time_budget_seconds})"
            )
        return self

    @model_validator(mode="after")
    def _validate_grid_and_capacity(self) -> Self:
        if self.grid_size < 3:
            raise ValueError(f"grid_size must be >= 3 (got {self.grid_size})")
        max_objects = max(self.object_count_values)
        max_differences = max(self.difference_count_values)
        if min(self.object_count_values) < max_differences:
            raise ValueError(
                f"min(object_count_values) must be >= max(difference_count_values) so every "
                f"difference can target a distinct object (got min objects "
                f"{min(self.object_count_values)}, max differences {max_differences})"
            )
        cell_count = self.grid_size * self.grid_size
        if cell_count < max_objects + max_differences + 1:
            raise ValueError(
                f"grid must hold the objects plus fresh cells for added/moved objects: "
                f"grid_size^2 ({cell_count}) must be >= max objects ({max_objects}) + "
                f"max differences ({max_differences}) + 1"
            )
        return self
