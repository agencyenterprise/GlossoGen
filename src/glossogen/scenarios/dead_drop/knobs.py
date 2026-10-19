"""Configuration knobs for the dead_drop scenario.

Rounds are scored deterministically from the submitted answers, so there is no
``judge_model`` / ``judge_provider`` pair.
"""

from typing import Annotated, Self

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.dead_drop.ids import ChannelMode, Disclosure

MAX_SLEEP_SECONDS_CEILING = 60.0
"""Upper bound on ``max_sleep_seconds``, the waiting one command line may do, below the
runner's scenario-tool timeout."""

MAX_KEYS_PER_RUN = 10_000
"""Upper bound on the keys a run draws, well inside the key space so drawing stays quick."""


class DeadDropKnobs(BaseKnobs):
    """Factors of the dead_drop scenario.

    ``disclosure`` sets what the prompts say about the partner and the filesystem.
    ``channel_mode=chat`` adds a channel both agents share. ``fs_isolated`` gives
    each agent its own ``/tmp``, ``fs_persists_across_rounds`` keeps what agents
    wrote across rounds, ``home_dirs_readable`` lets each agent read the other's
    home, and ``inotifywait_enabled`` offers a command that waits for the other
    user's changes. The remaining fields size the codebooks and bound the cost of
    a round.
    """

    disclosure: Disclosure
    channel_mode: ChannelMode
    fs_isolated: bool
    fs_persists_across_rounds: bool
    home_dirs_readable: bool
    inotifywait_enabled: bool
    codebook_entries: Annotated[int, Field(ge=1)]
    queries_per_agent: Annotated[int, Field(ge=1)]
    commands_per_round: Annotated[int, Field(ge=1)]
    max_sleep_seconds: Annotated[float, Field(gt=0, le=MAX_SLEEP_SECONDS_CEILING)]
    command_output_char_limit: Annotated[int, Field(ge=100)]
    seed: int

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        if self.channel_mode is ChannelMode.CHAT and self.disclosure is Disclosure.NONE:
            raise ValueError("channel_mode=chat reveals the partner, so disclosure cannot be none")
        if self.queries_per_agent > self.codebook_entries:
            raise ValueError(
                f"queries_per_agent ({self.queries_per_agent}) cannot exceed "
                f"codebook_entries ({self.codebook_entries})"
            )
        keys_drawn = self.codebook_entries * 2 * self.round_count
        if keys_drawn > MAX_KEYS_PER_RUN:
            raise ValueError(
                f"codebook_entries x 2 agents x round_count draws {keys_drawn} keys; "
                f"the limit is {MAX_KEYS_PER_RUN}"
            )
        if self.max_sleep_seconds >= self.max_round_duration_seconds:
            raise ValueError(
                f"max_sleep_seconds ({self.max_sleep_seconds}) must be below "
                f"max_round_duration_seconds ({self.max_round_duration_seconds})"
            )
        if self.postmortem_enabled:
            raise ValueError("postmortem_enabled must be false: a debrief is a channel")
        if self.compaction.enabled:
            raise ValueError(
                "compaction.enabled must be false: the platform's compaction prompt "
                "talks about channels and a scenario cannot replace it"
            )
        return self
