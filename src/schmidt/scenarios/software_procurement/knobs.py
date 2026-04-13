"""Tunable parameters for the software procurement scenario."""

from schmidt.scenarios.base_knobs import BaseKnobs


class SoftwareProcurementKnobs(BaseKnobs):
    """Configuration knobs that control scenario behavior.

    Loaded from a JSON file via the ``--knobs`` CLI argument.
    """

    spec_name: str
    num_seller_teams: int
    seller_crosschat: bool
    impossible_requirements: bool
    max_rounds: int
    words_dropped_from_messages: int
