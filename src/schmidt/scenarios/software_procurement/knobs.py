"""Tunable parameters for the software procurement scenario."""

from pydantic import BaseModel


class SoftwareProcurementKnobs(BaseModel):
    """Configuration knobs that control scenario behavior.

    Loaded from a JSON file via the ``--knobs`` CLI argument.
    """

    spec_name: str
    num_seller_teams: int
    seller_crosschat: bool
    impossible_requirements: bool
    max_rounds: int
    max_round_duration: int
    model_overrides: dict[str, str]
