"""Configuration knobs for the product launch scenario.

Defines the tunable parameters that control scenario behavior, including
base simulation parameters and intervention condition flags.
"""

from pydantic import BaseModel


class ProductLaunchKnobs(BaseModel):
    """Configuration knobs for the product launch scenario.

    Base parameters control simulation structure and difficulty.
    Intervention knobs (all off for base condition) enable specific
    governance mechanisms for comparative studies.
    """

    num_agents: int
    num_features: int
    num_rounds: int
    max_turns_per_round: int
    budget_total_ru: int
    budget_deficit_pct: float
    external_event_intensity: str
    model: str

    transparency_audit_log: bool
    escalation_channel_enabled: bool
    reputation_system_enabled: bool
    sanctioning_enabled: bool
    governance_monitor_role: bool
    covenant_prompt_enabled: bool
