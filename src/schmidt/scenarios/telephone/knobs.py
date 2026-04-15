"""Configuration knobs for the telephone scenario.

Controls the number of rounds, and the per-round token budget that
shrinks across epochs to create natural compression pressure.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class TelephoneKnobs(BaseKnobs):
    """Configuration knobs for the telephone scenario.

    ``round_count`` controls how many rounds the telephone game runs.
    ``base_tokens_per_item`` is the base token allowance per word-list
    item before epoch multipliers are applied. The per-round budget is
    ``len(items) * base_tokens_per_item * epoch_multiplier``.
    """

    round_count: int
    base_tokens_per_item: int
