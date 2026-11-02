"""Knobs for signal_game: grid shape, colours, shapes and fills, move budget and visibility."""

from typing import Any, Self, cast

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.signal_game.ids import FILLS, LEGACY_MAX_MOVES_PER_CALL, PALETTE, SHAPES


class SignalGameKnobs(BaseKnobs):
    """The factors of one embodied-signalling run.

    Each player's grid is ``grid_size`` squares on a side. Each square holds an
    item: a colour from the first ``colour_count`` colours of the palette, and,
    when ``shape_count`` is above 0, a shape from the first ``shape_count``
    shapes, and, when ``fill_count`` is above 0, a fill from the first
    ``fill_count`` fills. A round scores when both players finish on the same item.
    ``moves_per_round`` caps the moves one player makes in a round, and
    ``max_moves_per_call`` the moves one ``move`` call makes.
    ``partner_colours_visible`` shows each player the partner's items too,
    which removes the private information and is the control condition.
    ``move_reasoning`` makes every ``move`` and ``end_round`` call carry one
    sentence on why the player acts that way, logged and never shown to the partner.
    """

    grid_size: int = Field(ge=2, le=5)
    colour_count: int = Field(ge=2, le=len(PALETTE))
    shape_count: int = Field(ge=0, le=len(SHAPES))
    fill_count: int = Field(ge=0, le=len(FILLS))
    moves_per_round: int = Field(ge=1, le=1000)
    max_moves_per_call: int = Field(ge=1, le=50)
    partner_colours_visible: bool
    move_reasoning: bool
    seed: int

    @model_validator(mode="before")
    @classmethod
    def _fill_knobs_older_configs_lack(cls, data: Any) -> Any:
        """Read a config recorded before shapes, fills and the per-call cap were knobs.

        Such a run had no shapes or fills and took at most
        ``LEGACY_MAX_MOVES_PER_CALL`` directions a call, so a fork or resume of it
        plays the same game.
        """
        if not isinstance(data, dict):
            return data
        raw = cast(dict[str, Any], data)
        filled = dict(raw)
        if "shape_count" not in filled:
            filled["shape_count"] = 0
        if "fill_count" not in filled:
            filled["fill_count"] = 0
        if "max_moves_per_call" not in filled:
            filled["max_moves_per_call"] = LEGACY_MAX_MOVES_PER_CALL
        return filled

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        """Refuse a debrief channel, compaction, and fills on squares without shapes."""
        if self.postmortem_enabled:
            raise ValueError("postmortem_enabled must be false: a debrief is a channel")
        if self.compaction.enabled:
            raise ValueError(
                "compaction.enabled must be false: the platform's compaction prompt talks "
                "about channels, and this scenario has none"
            )
        if self.fill_count > 0 and self.shape_count == 0:
            raise ValueError("fill_count needs shape_count above 0: a fill is a shape's")
        return self
