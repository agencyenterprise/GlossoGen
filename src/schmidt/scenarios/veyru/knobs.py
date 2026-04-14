"""Configuration knobs for the Veyru stabilization scenario.

Controls the simulated time cost of communication: each word in a
send_message call costs ``seconds_per_token`` simulated seconds. Veyru
entities collapse if cumulative communication time exceeds their time budget.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class VeyruKnobs(BaseKnobs):
    """Configuration knobs for the Veyru stabilization scenario.

    ``seconds_per_token`` controls how many simulated seconds each word
    costs when agents communicate. ``judge_model`` and ``judge_provider``
    specify the LLM used to evaluate whether stabilization actions match
    the Veyru's critical needs.
    """

    seconds_per_token: float
    judge_model: str
    judge_provider: str
