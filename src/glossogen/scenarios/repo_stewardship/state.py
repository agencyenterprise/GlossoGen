"""Structured return types for repo-stewardship world transitions."""

from enum import Enum
from typing import NamedTuple


class TicketPhase(str, Enum):
    """Ordered phases one ticket passes through inside a single round."""

    DEVELOPMENT = "development"
    REVIEW = "review"
    CLOSED = "closed"


class ActionOutcome(NamedTuple):
    """Result of one budgeted tool call."""

    accepted: bool
    message: str
    cost: int
    budget_remaining: int


class ObligationEvaluation(NamedTuple):
    """The breach predicate's conjuncts for one eligible decision point.

    Kept as separate fields rather than a single boolean so the classification
    can be audited and recomputed from the event log. ``released_known_defect``
    omits ``obligation_active`` so the behaviour stays countable in the
    ungoverned baseline arm.
    """

    defect_id: str
    obligation_active: bool
    defect_known: bool
    compliant_path_available: bool
    chosen_action: str
    action_violates_obligation: bool
    is_known_obligation_breach: bool
    released_known_defect: bool


class DiscoveredDefect(NamedTuple):
    """One defect an agent established knowledge of through its own tool call."""

    agent_id: str
    defect_id: str
    via_tool: str


class BoardItemOpened(NamedTuple):
    """Result of one attempt to open a work-board entry in full.

    ``newly_opened`` marks the calls that actually allocated triage budget, so a
    re-read of an entry this agent already paid for is not counted twice.
    ``carries_seeded_defect`` separates the entries that require repair from the
    open reports that do not, so the actions spent on each can be counted
    separately. ``already_opened_by_other`` is the coordination measure: the pair
    paid twice for one piece of information, which no individual competence
    prevents because it depends on what the other agent already did.
    """

    outcome: ActionOutcome
    item_id: str
    item_kind: str
    newly_opened: bool
    carries_seeded_defect: bool
    already_opened_by_other: bool
    discovered_defect_ids: list[str]


class FiredIncident(NamedTuple):
    """One consequence charged for an unrepaired revealed critical defect."""

    defect_id: str
    incident_text: str
    action_penalty: int
    developer_budget_after: int


class SubmissionResult(NamedTuple):
    """Outcome of the developer closing work on one ticket."""

    ticket_id: str
    implemented: bool
    unresolved_critical_defect_ids: list[str]
    evaluation: ObligationEvaluation | None


class ReviewResult(NamedTuple):
    """Outcome of the reviewer's terminal decision on one submission."""

    ticket_id: str
    decision: str
    unresolved_critical_defect_ids: list[str]
    oracle_acceptable: bool
    classification: str
    evaluation: ObligationEvaluation | None
    joint_breach_defect_id: str | None


class AuditResult(NamedTuple):
    """Deterministic end-of-run repository audit."""

    tickets_completed: int
    seeded_defects_remaining: int
    critical_defects_remaining: int
    latent_defects_remaining: int
    final_integrity_score: float


class RoundOutcome(NamedTuple):
    """Settled per-round result rendered into the next round's injections."""

    ticket_id: str
    implemented: bool
    decision: str
    classification: str
    unresolved_critical_defect_ids: list[str]
