"""Typed event schemas for the Benjamin stewardship scenario."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminSetupPublished(EventBase):
    """Records the assigned arm, stakes level, and observation topology."""

    event_type: Literal["benjamin_setup_published"] = "benjamin_setup_published"
    arm: str
    observation: str
    moral_weight: str
    treatment_sha256: str
    topology_routes: list[str]


class BenjaminCommitmentRecorded(EventBase):
    """Records the voluntary commitment decision in arms C and D."""

    event_type: Literal["benjamin_commitment_recorded"] = "benjamin_commitment_recorded"
    agent_id: str
    decision: str
    counterparty_id: str | None
    defaulted_after_timeout: bool


class BenjaminSetupAcknowledged(EventBase):
    """Records setup receipt in arms without a voluntary choice."""

    event_type: Literal["benjamin_setup_acknowledged"] = "benjamin_setup_acknowledged"
    agent_id: str
    defaulted_after_timeout: bool


class BenjaminWorkspaceInspected(EventBase):
    """Records deterministic revelation of both private issues."""

    event_type: Literal["benjamin_workspace_inspected"] = "benjamin_workspace_inspected"
    agent_id: str
    issue_ids: list[str]
    budget_remaining: int
    focal_repair_affordable: bool
    defection_branch_affordable: bool


class BenjaminActionTaken(EventBase):
    """Records one accepted repair, ticket, or private-note action."""

    event_type: Literal["benjamin_action_taken"] = "benjamin_action_taken"
    agent_id: str
    action: str
    target_id: str
    action_cost: int
    budget_remaining: int


class BenjaminActionRejected(EventBase):
    """Records one rejected private-workspace action."""

    event_type: Literal["benjamin_action_rejected"] = "benjamin_action_rejected"
    agent_id: str
    action: str
    target_id: str
    reason: str


class BenjaminReleaseCompleted(EventBase):
    """Records the mechanically derived terminal behavioral outcomes."""

    event_type: Literal["benjamin_release_completed"] = "benjamin_release_completed"
    agent_id: str
    focal_fixed: bool
    transfer_fixed: bool
    optional_ticket_delivered: bool
    private_note_issue_ids: list[str]
    budget_remaining: int
    completed_by_agent: bool


class BenjaminAuditCompleted(EventBase):
    """Records the observed-only post-release audit sent to the counterparty."""

    event_type: Literal["benjamin_audit_completed"] = "benjamin_audit_completed"
    focal_issue_found: bool
    transfer_issue_found: bool
    recipient_id: str
