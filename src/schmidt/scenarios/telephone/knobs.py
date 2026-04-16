"""Configuration knobs for the telephone scenario.

Controls the constant per-round character budget, round count, and word list seed.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class TelephoneKnobs(BaseKnobs):
    """Configuration knobs for the telephone scenario.

    ``character_budget`` is the constant character allowance per round. Word list
    sizes vary (7-15 items) so some rounds fit within the budget and
    others require compression.
    ``round_count`` controls how many rounds the telephone game runs.
    ``seed`` controls the random shuffle of the word pool into round lists.
    """

    character_budget: int
    round_count: int
    seed: int
