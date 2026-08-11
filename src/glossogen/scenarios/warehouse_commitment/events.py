"""Event schemas for repeated warehouse commitment decisions."""

from typing import Literal

from glossogen.models.event_base import EventBase


class WarehouseCommitmentRoundStarted(EventBase):
    """Records the active institutional condition for one repeated decision."""

    event_type: Literal["warehouse_commitment_round_started"] = "warehouse_commitment_round_started"
    condition: str
    group_enabled: bool
    pledge_enabled: bool
    forfeiture_fraction: float
    provider_ids: list[str]


class WarehouseCommitmentPledgeSubmitted(EventBase):
    """Records a provider's structured response to the covenant pledge."""

    event_type: Literal["warehouse_commitment_pledge_submitted"] = (
        "warehouse_commitment_pledge_submitted"
    )
    agent_id: str
    decision: str
    pledge_text: str


class WarehouseCommitmentActionChosen(EventBase):
    """Records one provider's private inspection or shortcut choice."""

    event_type: Literal["warehouse_commitment_action_chosen"] = "warehouse_commitment_action_chosen"
    agent_id: str
    action: str
    inspected: bool
    gross_payment: float
    forfeiture_paid: float
    net_payment: float
    balance_before: float
    balance_after: float


class WarehouseCommitmentRoundSettled(EventBase):
    """Records the aggregate adherence outcome after a round ends."""

    event_type: Literal["warehouse_commitment_round_settled"] = "warehouse_commitment_round_settled"
    condition: str
    completed: bool
    inspected_provider_count: int
    shortcut_provider_count: int
    missing_provider_ids: list[str]
    joint_inspection: bool
    actions_by_provider: dict[str, str]
