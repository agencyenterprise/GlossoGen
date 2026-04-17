"""Configuration knobs for the Veyru stabilization scenario.

Controls the constant budget multiplier, character-based communication cost,
case shuffling seed, round count, postmortem discussion, and the LLM judge.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class VeyruKnobs(BaseKnobs):
    """Configuration knobs for the Veyru stabilization scenario.

    ``budget_multiplier`` scales all base case time budgets by a constant
    factor across every round. ``seconds_per_character`` controls how many
    simulated seconds each character costs when agents communicate.
    ``seed`` controls the random shuffle of failure motifs into round cases.
    ``postmortem_enabled`` controls whether a shared discussion phase follows
    each round. ``postmortem_duration_seconds`` sets the time limit for the
    discussion phase. ``judge_model`` and ``judge_provider`` specify the LLM
    used to evaluate whether stabilization actions match the Veyru's needs.
    """

    budget_multiplier: float
    judge_model: str
    judge_provider: str
    postmortem_duration_seconds: float
    postmortem_enabled: bool
    round_count: int
    seconds_per_character: float
    seed: int
