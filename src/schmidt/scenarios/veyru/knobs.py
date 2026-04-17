"""Configuration knobs for the Veyru stabilization scenario.

Controls character-based communication cost, case shuffling seed, round count,
postmortem discussion, and the LLM judge.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class VeyruKnobs(BaseKnobs):
    """Configuration knobs for the Veyru stabilization scenario.

    ``seconds_per_character`` controls how many simulated seconds each
    character costs when agents communicate — higher values mean tighter
    budgets. ``seed`` controls the random shuffle of failure motifs into
    round cases. ``postmortem_enabled`` controls whether a shared discussion
    phase follows each round. ``judge_model`` and ``judge_provider`` specify
    the LLM used to evaluate whether stabilization actions match the Veyru's
    needs.
    """

    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    round_count: int
    seconds_per_character: float
    seed: int
