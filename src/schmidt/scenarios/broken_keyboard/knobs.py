"""Configuration knobs for the broken keyboard scenario."""

from schmidt.scenarios.base_knobs import BaseKnobs


class BrokenKeyboardKnobs(BaseKnobs):
    """Tunable parameters for the broken keyboard scenario."""

    r_drop_rate: float
    max_rounds: int
