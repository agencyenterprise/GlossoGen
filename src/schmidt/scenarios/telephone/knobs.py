"""Configuration knobs for the telephone scenario.

Controls epoch selection, round count, and the per-round token budget.
Each epoch applies a fixed budget multiplier to create uniform compression
pressure across all rounds.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class TelephoneKnobs(BaseKnobs):
    """Configuration knobs for the telephone scenario.

    ``epoch`` selects which epoch to run (1-indexed). Each epoch uses a
    fixed budget multiplier so pressure is constant across all rounds.
    ``round_count`` controls how many rounds the telephone game runs.
    ``base_tokens_per_item`` is the base token allowance per word-list
    item before the epoch multiplier is applied. The per-round budget is
    ``len(items) * base_tokens_per_item * epoch_multiplier``.
    """

    epoch: int
    round_count: int
    base_tokens_per_item: int
