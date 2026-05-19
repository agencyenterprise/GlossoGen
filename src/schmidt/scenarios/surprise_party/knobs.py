"""Configuration knobs for the surprise_party scenario.

Controls round count, the wall-clock per-round timeout, the LLM judge used
to score freetext guesses, the model pinned to the rotating Friend slot,
and the seed used for both the (where, when) draw and the per-round friend
name shuffle.
"""

from typing import Self

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs
from schmidt.scenarios.surprise_party.friend_names import FRIEND_NAME_POOL


class SurprisePartyKnobs(BaseKnobs):
    """Configuration knobs for the surprise_party scenario.

    ``judge_model`` / ``judge_provider`` configure the LLM that scores
    ``submit_guess`` calls against the ground-truth party where / when.
    ``round_count`` controls how many rotating-friend rounds run.
    ``seed`` drives the deterministic ``(where, when)`` draw and the
    deterministic shuffle of friend names. ``friend_model`` and
    ``friend_provider`` pin the Friend slot's model — independent of the
    ``--model`` CLI flag — so the same agent model is used for the initial
    spawn and every per-round swap.
    """

    judge_model: str
    judge_provider: str
    round_count: int
    seed: int
    friend_model: str
    friend_provider: str

    @model_validator(mode="after")
    def _validate_surprise_party_knobs(self) -> Self:
        if self.round_count < 1:
            raise ValueError(f"round_count must be >= 1 (got {self.round_count})")
        if self.round_count > len(FRIEND_NAME_POOL):
            raise ValueError(
                f"round_count={self.round_count} exceeds the friend name pool "
                f"(size {len(FRIEND_NAME_POOL)}). Add more names to "
                f"surprise_party.friend_names.FRIEND_NAME_POOL or lower round_count."
            )
        return self
