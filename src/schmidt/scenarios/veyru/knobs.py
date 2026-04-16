"""Configuration knobs for the Veyru stabilization scenario.

Controls epoch selection, the simulated time cost of communication, and
the LLM judge. Each epoch applies a fixed budget multiplier so pressure
is constant across all rounds.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class VeyruKnobs(BaseKnobs):
    """Configuration knobs for the Veyru stabilization scenario.

    ``epoch`` selects which epoch to run (1-indexed). Each epoch uses a
    fixed budget multiplier so pressure is constant across all rounds.
    ``seconds_per_token`` controls how many simulated seconds each word
    costs when agents communicate. ``judge_model`` and ``judge_provider``
    specify the LLM used to evaluate whether stabilization actions match
    the Veyru's critical needs.
    """

    epoch: int
    round_count: int
    seconds_per_token: float
    judge_model: str
    judge_provider: str
