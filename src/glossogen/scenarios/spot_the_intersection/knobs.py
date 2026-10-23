"""Configuration knobs for the spot_the_intersection scenario.

Controls how many viewers a team has, the grid and how many objects each board
holds, whether near-misses make every board necessary, the competing second
team and whether it is simulated, the postmortem discussion phase, channel
noise, and the optional per-round character budget.
"""

from typing import Annotated, Self

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.spot_the_intersection.board_generation import (
    BoardSettings,
    planted_per_board,
)
from glossogen.scenarios.spot_the_intersection.board_model import MAX_GRID_SIZE

MAX_TEAM_SIZE = 12

PositiveShare = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class SpotTheIntersectionKnobs(BaseKnobs):
    """Configuration knobs for the spot_the_intersection scenario.

    Each team has ``team_size`` viewers, each holding a private board of
    objects (a shape and a color in a cell of a ``grid_size`` x ``grid_size``
    grid). Exactly one object is on every board of a team. With ``near_misses``
    on and three or more viewers, certification requires that leaving out any
    one board leaves at least two candidates. Each round draws a decoy count and
    a filler count. Decoys are objects held by more than one board and fewer
    than all. Every board holds the planted objects plus both counts, padded
    with fillers (objects held by one board), so a board holds the filler count
    plus one filler for each decoy it lacks, and its size grows with
    ``team_size``.

    ``two_teams`` runs a second team on the same boards seat for seat. Among
    teams whose every member submits the correct object, the one that sent the
    fewest link characters wins the round. ``simulated_opponent_ratio``, with
    two teams, plays Team A alone and scores it against a simulated Team B that
    gets every round right in a share of Team A's own characters, rounded down.
    A number fixes the share; a ``[low, high]`` pair draws it each round within
    that range from the seed and the round number, so a resumed run scores a
    round as it was played. ``None`` plays both teams. Team A is told exactly what it would be
    told against a real Team B. ``round_time_budget_seconds`` is an optional
    hard cap on link characters (``-1`` for none).
    """

    round_time_budget_seconds: int
    seed: int
    team_size: int = Field(ge=2, le=MAX_TEAM_SIZE)
    grid_size: int = Field(ge=3, le=MAX_GRID_SIZE)
    near_misses: bool
    decoy_count_values: list[int]
    decoy_count_weights: list[int]
    filler_count_values: list[int]
    filler_count_weights: list[int]
    two_teams: bool
    simulated_opponent_ratio: PositiveShare | tuple[PositiveShare, PositiveShare] | None

    @model_validator(mode="after")
    def _validate_count_distributions(self) -> Self:
        for name, values, weights in (
            ("decoy_count", self.decoy_count_values, self.decoy_count_weights),
            ("filler_count", self.filler_count_values, self.filler_count_weights),
        ):
            if len(values) == 0:
                raise ValueError(f"{name}_values must be non-empty")
            if len(values) != len(weights):
                raise ValueError(
                    f"{name}_values and {name}_weights must have the same length "
                    f"(got {len(values)} values and {len(weights)} weights)"
                )
            if any(value < 0 for value in values):
                raise ValueError(f"{name}_values must all be >= 0 (got {values})")
            if any(weight <= 0 for weight in weights):
                raise ValueError(f"{name}_weights must all be > 0 (got {weights})")
        return self

    @model_validator(mode="after")
    def _validate_decoys_need_three_viewers(self) -> Self:
        if self.team_size < 3 and max(self.decoy_count_values) > 0:
            raise ValueError(
                "a decoy is on more than one board and fewer than all, which needs "
                f"team_size >= 3 (got team_size={self.team_size}, "
                f"decoy_count_values={self.decoy_count_values}); set decoy_count_values to [0] "
                "and decoy_count_weights to [1]"
            )
        return self

    @model_validator(mode="after")
    def _validate_simulated_opponent(self) -> Self:
        share = self.simulated_opponent_ratio
        if share is None:
            return self
        if not self.two_teams:
            raise ValueError(
                "simulated_opponent_ratio stands in for Team B, so it needs two_teams=True "
                f"(got simulated_opponent_ratio={share})"
            )
        if isinstance(share, tuple) and share[0] > share[1]:
            raise ValueError(
                "simulated_opponent_ratio as a range must be [low, high] with low <= high "
                f"(got {list(share)})"
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
    def _validate_grid_capacity(self) -> Self:
        largest = largest_board_size(knobs=self)
        if self.grid_size * self.grid_size < 2 * largest:
            raise ValueError(
                f"a {self.grid_size}x{self.grid_size} grid is too small for boards of up to "
                f"{largest} objects; the grid needs at least twice as many cells as the "
                "largest board"
            )
        return self

    def board_settings(self) -> BoardSettings:
        """The subset of knobs board generation reads."""
        return BoardSettings(
            team_size=self.team_size,
            grid_size=self.grid_size,
            near_misses=self.near_misses,
            decoy_count_values=self.decoy_count_values,
            decoy_count_weights=self.decoy_count_weights,
            filler_count_values=self.filler_count_values,
            filler_count_weights=self.filler_count_weights,
        )


def largest_board_size(knobs: SpotTheIntersectionKnobs) -> int:
    """The most objects any round's boards can hold under these knobs."""
    planted = planted_per_board(team_size=knobs.team_size, near_misses=knobs.near_misses)
    return planted + max(knobs.decoy_count_values) + max(knobs.filler_count_values)
