"""Validated configuration for service-reliability governance arms."""

from enum import Enum
from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.service_reliability.ids import (
    CLOSURE_COVENANT_DECISION_LINE,
    CLOSURE_RULE_DECISION_LINE,
    COVENANT_TEXT,
    DISCLOSURE_COVENANT_DECISION_LINE,
    DISCLOSURE_RULE_DECISION_LINE,
    RULE_TEXT,
)
from glossogen.scenarios.service_reliability.incident_fixture import (
    ALERTS,
    FAULT_BY_ID,
    FAULTS,
    subsystem_of_service,
)


class GovernanceCondition(str, Enum):
    """Institutional exposure applied to an otherwise identical world.

    The material world is byte-identical across all three arms: same services,
    same faults, same alerts, same arrival schedule, same budgets, same tool
    costs, same ledger. Only the normative structure differs, which is what
    allows a difference between ``RULE`` and ``COVENANT`` to be attributed to
    the provenance and mutuality of the obligation rather than to enforcement.
    """

    BASELINE = "baseline"
    PRIVATE_NOTEBOOK = "private_notebook"
    RULE = "rule"
    COVENANT = "covenant"


class ServiceReliabilityKnobs(BaseKnobs):
    """Parameters for two operators sustaining a service under action scarcity.

    Both operators are live. Scarcity is enforced by the world rather than
    asserted in a prompt: each budgeted tool call decrements a counter and is
    refused once the balance cannot cover it. ``mark_resolved`` is free, so a
    run can always make progress and the whole of the budget pressure falls on
    diagnosis, repair, verification, and disclosure.

    The good the operators hold in common is the diagnosis of a hidden fault.
    It is non-rivalrous — posting it to the ledger does not take it away from
    the poster — but acquiring it costs actions and disclosing it costs one
    more, and four of the six faults can only be repaired by the operator who
    did not pay to find them.
    """

    seed: int
    condition: GovernanceCondition
    judge_model: str
    judge_provider: str
    setup_rounds: int
    """Rounds before the first alert wave, used to publish the arm and take commitments.

    The alert schedule in the fixture is stated in world rounds; the scenario
    offsets it by this many simulation rounds. A setup round exists so that in
    the covenant arm each operator learns the other affirmed before either has
    acted, which is the mutuality the arm is defined by, and so that the rule
    arm reads its standards at the same position in the transcript.
    """

    platform_allowance_per_round: int
    data_allowance_per_round: int
    """Actions granted to each operator at the start of every non-setup round.

    Granted per round and accumulating rather than issued once at the start.
    A single up-front balance was spent in the first round by every operator
    observed, which left the second and third fault waves unactionable and made
    the outcome a function of the arrival schedule rather than of how the
    operators allocated. Recurring grants also mean resources keep arriving, so
    no round is the one after which nothing can be done.
    """
    inspect_action_cost: int
    read_logs_action_cost: int
    trace_action_cost: int
    repair_action_cost: int
    verify_action_cost: int
    post_finding_action_cost: int
    resolution_scoreboard_enabled: bool
    """Whether each operator sees its own running count of alerts marked resolved.

    Constitutive of this scenario's dilemma rather than an add-on to it. The
    locally rewarded act — closing an alert — is free and immediate, while the
    two collectively valuable acts — verifying before closing, and disclosing a
    diagnosis the other operator needs — both cost budget. Switching the
    scoreboard off removes the private pull against which the obligation is
    measured. It is held identical across arms, so it sets the pressure the
    arms are compared under; it does not confound the comparison.
    """

    ledger_is_shared: bool
    """Whether a posted finding is readable by the other operator.

    Setting this false is the ``private_notebook`` control that
    [STUDY-014](../../../../docs/research/covenant-game/studies/STUDY-014-knowledge-commons.md)
    makes a standing requirement: the write carries the identical cost with no
    beneficiary. Until it is run, nothing observed here may be described as a
    public good or as free-riding — the omission that cost that study's
    predecessors four studies.

    Scope its reading carefully. In this world the two forced-coordination
    faults are visible only to the operator that cannot repair them, so a
    private ledger makes them unrepairable and the arm's outage endpoint is not
    comparable to the others'. The control identifies the **write rate** under
    an identical cost with no reader, and nothing else.
    """

    horizon_disclosed: bool
    """Whether the operators are told how many rounds remain.

    Withholding it is the scenario's implementation of an open horizon: outage
    weight accrues every round a fault stays active and new faults arrive
    mid-run, so there is no round after which nothing is at stake and no round
    an operator can identify as the last one. Disclosing it is available as the
    ablation that restores a terminal point.
    """

    obligation_active: bool
    commitment_required: bool

    @model_validator(mode="after")
    def check_condition_wiring(self) -> Self:
        """Reject a configuration whose flags contradict its named arm."""
        if self.condition is GovernanceCondition.BASELINE:
            if self.obligation_active or self.commitment_required:
                raise ValueError("baseline carries no obligation text and no affirmation step")
            if not self.ledger_is_shared:
                raise ValueError("baseline shares the ledger; use private_notebook instead")
        if self.condition is GovernanceCondition.PRIVATE_NOTEBOOK:
            if self.obligation_active or self.commitment_required:
                raise ValueError(
                    "private_notebook carries no obligation text and no affirmation step"
                )
            if self.ledger_is_shared:
                raise ValueError("private_notebook requires ledger_is_shared=false")
        if self.condition is GovernanceCondition.RULE:
            if not self.ledger_is_shared:
                raise ValueError(f"rule shares the ledger")
            if not self.obligation_active:
                raise ValueError("rule requires obligation_active=true")
            if self.commitment_required:
                raise ValueError("rule is imposed, not affirmed; commitment_required must be false")
        if self.condition is GovernanceCondition.COVENANT:
            if not self.ledger_is_shared:
                raise ValueError(f"covenant shares the ledger")
            if not self.obligation_active:
                raise ValueError("covenant requires obligation_active=true")
            if not self.commitment_required:
                raise ValueError("covenant requires commitment_required=true")
        return self

    @model_validator(mode="after")
    def check_scarcity_binds(self) -> Self:
        """Refuse a budget that lets perfect play clear every fault.

        This is the anti-ceiling condition stated as a precondition rather than
        as a hope. If the combined budget covers the cheapest complete run, the
        instrument cannot separate arms by how scarce actions were allocated,
        because a sufficiently capable operator pair can simply do everything.
        """
        combined = self.combined_action_budget()
        required = self.minimum_full_resolution_cost()
        if combined >= required:
            raise ValueError(
                f"combined action budget {combined} covers the cheapest complete "
                f"resolution ({required}); scarcity would not bind"
            )
        return self

    def minimum_full_resolution_cost(self) -> int:
        """Return the cheapest action total that clears every fault and closes every alert.

        Assumes ideal play: each fault is traced once, from an alert inside the
        subsystem that owns it where one exists; a fault surfacing in the other
        operator's subsystem is disclosed once; every alert is verified before
        it is closed; and the benign alert is traced once to establish that it
        is benign. This is a lower bound on cost, not a prediction of behaviour.
        """
        total = 0
        for fault in FAULTS:
            total += self.trace_action_cost + self.repair_action_cost
        for alert in ALERTS:
            total += self.verify_action_cost
            if alert.fault_id is None:
                total += self.trace_action_cost
                continue
            fault = FAULT_BY_ID[alert.fault_id]
            surfaces_elsewhere = subsystem_of_service(alert.service_id) != subsystem_of_service(
                fault.service_id
            )
            if surfaces_elsewhere:
                total += self.post_finding_action_cost
        return total

    def world_round_count(self) -> int:
        """Return how many rounds carry alerts, after the setup rounds."""
        return self.round_count - self.setup_rounds

    def total_budget_for(self, subsystem_value: str) -> int:
        """Return every action one subsystem will be granted across the run."""
        return self.allowance_for(subsystem_value=subsystem_value) * self.world_round_count()

    def combined_action_budget(self) -> int:
        """Return both operators' total grants across the run."""
        return self.total_budget_for(subsystem_value="platform") + self.total_budget_for(
            subsystem_value="data"
        )

    def allowance_for(self, subsystem_value: str) -> int:
        """Return the per-round grant for one subsystem."""
        if subsystem_value == "platform":
            return self.platform_allowance_per_round
        if subsystem_value == "data":
            return self.data_allowance_per_round
        raise ValueError(f"unknown subsystem: {subsystem_value}")

    def obligation_text(self) -> str | None:
        """Return the arm's obligation text, or ``None`` in baseline."""
        if not self.obligation_active:
            return None
        if self.commitment_required:
            return COVENANT_TEXT
        return RULE_TEXT

    def disclosure_decision_line(self) -> str | None:
        """Return the retrieval line shown before a disclosure decision."""
        if not self.obligation_active:
            return None
        if self.commitment_required:
            return DISCLOSURE_COVENANT_DECISION_LINE
        return DISCLOSURE_RULE_DECISION_LINE

    def closure_decision_line(self) -> str | None:
        """Return the retrieval line shown before a closure decision."""
        if not self.obligation_active:
            return None
        if self.commitment_required:
            return CLOSURE_COVENANT_DECISION_LINE
        return CLOSURE_RULE_DECISION_LINE

    def action_cost(self, action: str) -> int:
        """Return the budget cost of one action name."""
        costs = {
            "inspect_service": self.inspect_action_cost,
            "read_logs": self.read_logs_action_cost,
            "trace_dependency": self.trace_action_cost,
            "apply_repair": self.repair_action_cost,
            "verify_alert": self.verify_action_cost,
            "post_finding": self.post_finding_action_cost,
            "mark_resolved": 0,
        }
        if action not in costs:
            raise ValueError(f"unknown service-reliability action: {action}")
        return costs[action]
