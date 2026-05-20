"""Configuration knobs for the codebreakers scenario.

Covers round count, the wall-clock per-round timeout, the seed driving
the deterministic per-round target draw, and the (currently unused but
preserved for consistency) judge model fields.
"""

from typing import Self

from pydantic import model_validator

from schmidt.scenarios.base_knobs import BaseKnobs


class CodebreakersKnobs(BaseKnobs):
    """Configuration knobs for the codebreakers scenario.

    ``round_count`` controls how many target-signaling rounds run.
    ``seed`` drives the per-round target sampler. ``judge_model`` /
    ``judge_provider`` are kept on the knobs schema for consistency with
    other scenarios; v1 uses exact pool matching and does not call an LLM
    judge.
    """

    judge_model: str
    judge_provider: str
    round_count: int
    seed: int
    postmortem_enabled: bool

    @model_validator(mode="after")
    def _validate_codebreakers_knobs(self) -> Self:
        if self.round_count < 1:
            raise ValueError(f"round_count must be >= 1 (got {self.round_count})")
        return self
