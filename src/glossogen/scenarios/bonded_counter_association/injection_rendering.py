"""Render the per-round, repair, and review prompts for the counting market.

Injections are the only channel through which a provider learns its private
state: its own role, the last recorded shelf figure, its own balance, its
membership standing, and whatever is public. The true count is never among
them — an injection that carried it would make paid effort pointless and void
the whole design.

Each provider gets a different injection because each has different private
state, but all of them are rendered from the same template so the wording
cannot drift between conditions or between roles in a way that would confound
a treatment contrast.
"""

from typing import NamedTuple

from glossogen.scenarios.bonded_counter_association.ids import (
    CONTRACT_ASSOCIATION,
    CONTRACT_INDEPENDENT,
    JOB_ROLE_PRIMARY,
    JOB_ROLE_VERIFIER,
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_EXPELLED,
    POSTMORTEM_CHANNEL_NAME,
    POSTMORTEM_INJECTION_TEMPLATE,
    PROVIDER_INJECTION_TEMPLATE,
    REPAIR_INJECTION_TEMPLATE,
    provider_role_name,
)
from glossogen.scenarios.bonded_counter_association.knobs import BondedCounterAssociationKnobs
from glossogen.scenarios.bonded_counter_association.world import BondedCounterWorld
from glossogen.scenarios.bonded_counter_association.world_records import AuditResolution
from glossogen.scenarios.bonded_counter_association.world_state import PublicJobRecord, RoundOutcome
from glossogen.template_renderer import TemplateRenderer

CONTRACT_LABELS = {
    CONTRACT_ASSOCIATION: "guaranteed association contract",
    CONTRACT_INDEPENDENT: "independent contract",
}
CONTRACT_LABEL_NONE = "no contract could be staffed this round"

MEMBERSHIP_LABELS = {
    MEMBERSHIP_ACTIVE: "active association member",
    MEMBERSHIP_EXPELLED: "removed from the association",
}
MEMBERSHIP_LABEL_INDEPENDENT = "independent provider"

JOB_ROLE_LABELS = {
    JOB_ROLE_PRIMARY: "primary counter",
    JOB_ROLE_VERIFIER: "verifier",
}


class AuditReportRow(NamedTuple):
    """One newly public audit result, as the injection renders it."""

    case_number: int
    contract_label: str
    count_correct: bool
    implicated_labels: tuple[str, ...]
    refund_due: float


class PublicRecordRow(NamedTuple):
    """One entry of the public reliability record, as the injection renders it."""

    case_number: int
    contract_label: str
    count_correct: bool
    audit_resolved: bool


def contract_label(contract_type: str) -> str:
    """Return the human-readable label for a contract type."""
    return CONTRACT_LABELS.get(contract_type, CONTRACT_LABEL_NONE)


def membership_label(membership_state: str) -> str:
    """Return the human-readable label for a membership state."""
    return MEMBERSHIP_LABELS.get(membership_state, MEMBERSHIP_LABEL_INDEPENDENT)


def build_audit_report_rows(resolutions: tuple[AuditResolution, ...]) -> list[AuditReportRow]:
    """Turn this round's revealed audits into injection rows."""
    return [
        AuditReportRow(
            case_number=resolution.case_number,
            contract_label=contract_label(contract_type=resolution.contract_type),
            count_correct=resolution.count_correct,
            implicated_labels=tuple(
                provider_role_name(agent_id=agent_id)
                for agent_id in resolution.implicated_agent_ids
            ),
            refund_due=resolution.refund_due,
        )
        for resolution in resolutions
    ]


def build_public_record_rows(
    history: list[PublicJobRecord],
    window: int,
) -> list[PublicRecordRow]:
    """Turn the trailing public reliability record into injection rows."""
    return [
        PublicRecordRow(
            case_number=record.case_number,
            contract_label=contract_label(contract_type=record.contract_type),
            count_correct=record.count_correct,
            audit_resolved=record.audit_resolved,
        )
        for record in history[-window:]
    ]


def render_round_injection(
    renderer: TemplateRenderer,
    world: BondedCounterWorld,
    knobs: BondedCounterAssociationKnobs,
    round_number: int,
    agent_id: str,
    audit_reports: list[AuditReportRow],
) -> str:
    """Render one provider's private per-round injection."""
    job = world.current_job
    assert job is not None, "render_round_injection requires an open job"
    state = world.provider(agent_id=agent_id)
    previous = world.previous_outcome()
    if job.contract_type == CONTRACT_ASSOCIATION:
        fee: float | None = knobs.association_contract_fee
    elif job.contract_type == CONTRACT_INDEPENDENT:
        fee = knobs.independent_contract_fee
    else:
        fee = None
    if job.contract_type == CONTRACT_ASSOCIATION and knobs.shared_bond_enabled:
        bond_contribution = knobs.bond_contribution_per_contract
    else:
        bond_contribution = 0.0
    if job.primary_counter_id is None:
        primary_label: str | None = None
    else:
        primary_label = provider_role_name(agent_id=job.primary_counter_id)
    if job.verifier_id is None:
        verifier_label = ""
    else:
        verifier_label = provider_role_name(agent_id=job.verifier_id)
    return renderer.render(
        template_name=PROVIDER_INJECTION_TEMPLATE,
        template_variables={
            "round_number": round_number,
            "institution_enabled": knobs.institution_enabled,
            "own_balance": state.balance,
            "own_membership_label": membership_label(membership_state=state.membership_state),
            "roster_visible": knobs.membership_visible,
            "association_members": [
                provider_role_name(agent_id=member_id) for member_id in world.active_member_ids()
            ],
            "bond_balance": world.bond_balance,
            "bond_unpaid_liability": world.bond_unpaid_liability,
            "association_insolvent": world.association_insolvent,
            "contract_label": contract_label(contract_type=job.contract_type),
            "contract_fee": fee,
            "bond_contribution": bond_contribution,
            "job_role": world.job_role_for(agent_id=agent_id),
            "stale_count": job.stale_count,
            "count_effort_cost": knobs.count_effort_cost,
            "verification_effort_cost": knobs.verification_effort_cost,
            "primary_counter_label": primary_label,
            "verifier_label": verifier_label,
            "membership_window_open": world.membership_window_open,
            "association_entry_stake": knobs.association_entry_stake,
            "exit_stake_forfeit": (
                knobs.association_entry_stake * knobs.exit_stake_forfeit_fraction
            ),
            "audit_reports": audit_reports,
            "public_record": build_public_record_rows(
                history=world.public_history,
                window=knobs.client_reliability_window,
            ),
            "previous_outcome": previous,
            "previous_previous_contract_label": _previous_contract_label(previous=previous),
        },
    )


def _previous_contract_label(previous: RoundOutcome | None) -> str:
    """Return the contract label for the previous round, or an empty string."""
    if previous is None:
        return ""
    return contract_label(contract_type=previous.contract_type)


def render_repair_injection(
    renderer: TemplateRenderer,
    knobs: BondedCounterAssociationKnobs,
    case_number: int,
    signed_count: int | None,
    job_role: str,
) -> str:
    """Render the repair-window prompt for one implicated provider."""
    return renderer.render(
        template_name=REPAIR_INJECTION_TEMPLATE,
        template_variables={
            "case_number": case_number,
            "signed_count": signed_count,
            "your_role_label": JOB_ROLE_LABELS.get(job_role, "provider on the job"),
            "contribution_allowed": knobs.voluntary_repair_contribution_enabled,
            "contribution_limit": knobs.repair_contribution_limit,
        },
    )


def render_postmortem_injection(
    renderer: TemplateRenderer,
    round_number: int,
    previous: RoundOutcome | None,
) -> str:
    """Render the post-round review prompt."""
    return renderer.render(
        template_name=POSTMORTEM_INJECTION_TEMPLATE,
        template_variables={
            "round_number": round_number,
            "previous_outcome": previous,
            "contract_label": _previous_contract_label(previous=previous),
            "postmortem_channel_name": POSTMORTEM_CHANNEL_NAME,
        },
    )
