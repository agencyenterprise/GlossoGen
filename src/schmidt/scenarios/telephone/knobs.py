"""Configuration knobs for the telephone scenario.

Controls the number of rounds in the telephone game. Each round presents
a word list of increasing length that the Relayer must compress.
"""

from schmidt.scenarios.base_knobs import BaseKnobs


class TelephoneKnobs(BaseKnobs):
    """Configuration knobs for the telephone scenario.

    ``round_count`` controls how many rounds the telephone game runs.
    """

    round_count: int
