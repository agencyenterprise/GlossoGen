"""Configuration knobs for the product launch scenario.

Defines tunable parameters controlling simulation structure, difficulty,
and intervention conditions for comparative governance studies.
"""

from pydantic import BaseModel


class ProductLaunchKnobs(BaseModel):
    """Tunable parameters for the product launch scenario.

    Base parameters control simulation structure and difficulty.
    Intervention knobs (all off for the base condition) enable specific
    governance mechanisms for comparative studies.
    """

    num_features: int
    num_rounds: int
    max_turns_per_round: int
    budget_total_ru: int
    budget_deficit_pct: float
    external_event_intensity: str

    transparency_audit_log: bool
    escalation_channel_enabled: bool
    reputation_system_enabled: bool
    sanctioning_enabled: bool
    governance_monitor_role: bool
    covenant_prompt_enabled: bool
