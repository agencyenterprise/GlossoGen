"""Configuration knobs for the leaderboard_leak scenario.

Rounds are scored deterministically from the submitted answers, so there is no
``judge_model`` / ``judge_provider`` pair.
"""

from typing import Annotated, Self

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.leaderboard_leak.ids import TASKS_PER_ROUND, ChannelMode, Disclosure

MAX_IDS_PER_RUN = 10_000
"""Upper bound on the IDs a run draws, well inside the ID space so drawing stays quick."""


class LeaderboardLeakKnobs(BaseKnobs):
    """Factors of the leaderboard_leak scenario.

    ``disclosure`` adds a sentence about the other team to the system prompt.
    ``comments_visible=false`` leaves the other team's comments out of the
    submission log, and ``channel_mode=chat`` adds a channel all four agents share;
    those are the two control conditions. ``sheet_entries`` sizes each team's sheet
    and ``comment_char_limit`` the longest comment accepted.
    """

    disclosure: Disclosure
    comments_visible: bool
    channel_mode: ChannelMode
    sheet_entries: Annotated[int, Field(ge=TASKS_PER_ROUND)]
    comment_char_limit: Annotated[int, Field(ge=1)]
    seed: int

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        """Refuse settings whose agent-facing text would be false or unaudited."""
        ids_drawn = self.sheet_entries * 2 * self.round_count
        if ids_drawn > MAX_IDS_PER_RUN:
            raise ValueError(
                f"sheet_entries x 2 teams x round_count draws {ids_drawn} IDs; "
                f"the limit is {MAX_IDS_PER_RUN}"
            )
        if self.disclosure is Disclosure.COMMENTS_READ and not self.comments_visible:
            raise ValueError(
                "disclosure=comments_read says the other team reads your comments, which "
                "comments_visible=false makes false"
            )
        if self.postmortem_enabled:
            raise ValueError(
                "postmortem_enabled must be false: the hint audit does not cover postmortem "
                "prompts"
            )
        if self.compaction.enabled:
            raise ValueError(
                "compaction.enabled must be false: the platform's compaction prompt speaks of "
                "the team's communication protocol, and a scenario cannot replace it"
            )
        if self.channel_noise_level != 0.0:
            raise ValueError("channel_noise_level must be 0: no channel here is corrupted")
        return self
