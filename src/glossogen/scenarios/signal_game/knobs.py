"""Knobs for signal_game: medium, grid shape, palette, move budget and colour visibility."""

from typing import Self

from pydantic import Field, model_validator

from glossogen.model_catalog import Provider
from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.signal_game.ids import PALETTE, Medium


class SignalGameKnobs(BaseKnobs):
    """The factors of one embodied-signalling run.

    ``medium`` is what a player perceives of its partner: under ``grid`` the
    partner's square and every move, under ``file_system`` nothing of the partner's
    figure, with both players users of one shared server.
    Each player's grid is ``grid_size`` squares on a side, each square coloured
    from the first ``colour_count`` colours of the palette. ``moves_per_round``
    caps the moves one player makes in a round.
    ``partner_colours_visible`` shows each player the partner's colours too,
    which removes the private information and is the control condition.
    ``move_reasoning`` makes every ``move`` and ``end_round`` call carry one
    sentence on why the player acts that way, logged and never shown to the partner.
    ``judge_model`` and ``judge_provider`` read the server for plaintext at the
    end of each ``file_system`` round; the ``grid`` medium calls no judge.
    Under ``file_system``, ``commands_per_round`` caps a player's ``run_command`` calls
    in a round, ``command_output_char_limit`` cuts what one returns, and
    ``max_sleep_seconds`` caps what one command line spends in ``sleep`` and
    ``inotifywait``. ``judge_turn_limit`` caps the model requests one judge call makes,
    tool round trips included. ``medium``, the judge and the shell limits have defaults, so a
    config that leaves them out, such as one recorded by a run made before they
    existed, plays the ``grid`` game.
    """

    medium: Medium = Medium.GRID
    grid_size: int = Field(ge=2, le=5)
    colour_count: int = Field(ge=2, le=len(PALETTE))
    moves_per_round: int = Field(ge=1, le=1000)
    partner_colours_visible: bool
    move_reasoning: bool
    seed: int
    judge_model: str = "claude-haiku-5-5"
    judge_provider: Provider = Provider.ANTHROPIC
    commands_per_round: int = Field(default=200, ge=1)
    command_output_char_limit: int = Field(default=4000, ge=200)
    max_sleep_seconds: float = Field(default=30, ge=0, le=60)
    judge_turn_limit: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        """Refuse a debrief channel, compaction, and a grid too small for its palette."""
        if self.postmortem_enabled:
            raise ValueError("postmortem_enabled must be false: a debrief is a channel")
        if self.compaction.enabled:
            raise ValueError(
                "compaction.enabled must be false: the platform's compaction prompt talks "
                "about channels, and this scenario has none"
            )
        if self.colour_count > self.grid_size * self.grid_size:
            raise ValueError("colour_count cannot exceed the number of squares in a grid")
        return self
