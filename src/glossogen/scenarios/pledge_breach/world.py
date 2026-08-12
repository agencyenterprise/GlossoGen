"""Deterministic state for pledge-breach trajectories with a scripted partner."""

from decimal import Decimal
from typing import Any

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.pledge_breach.events import (
    PledgeBreachDecisionRecorded,
    PledgeBreachMembershipCostPaid,
    PledgeBreachPledgeSubmitted,
    PledgeBreachRoundSettled,
)
from glossogen.scenarios.pledge_breach.ids import (
    AFFIRM,
    CONTRIBUTE,
    DECLINE,
    NO_DECISION,
    PARTNER_ID,
    PARTNER_INCAPACITY_LABEL,
    PARTNER_NAME,
    PROVIDER_ID,
    PROVIDER_NAME,
    RETAIN,
    action_past_tense,
    pledge_past_tense,
)
from glossogen.scenarios.pledge_breach.knobs import PledgeBreachKnobs
from glossogen.scenarios.pledge_breach.state import ProviderState, RoundActions, RoundSettlement


class PledgeBreachWorld(ScenarioWorld):
    """Tracks the live provider's balance against a fixed partner script."""

    def __init__(self, knobs: PledgeBreachKnobs) -> None:
        self._knobs = knobs
        self._provider = ProviderState(
            earnings=knobs.initial_endowment,
            pledge_decision=None,
            membership_cost_paid=Decimal("0.0"),
        )
        self._partner_pledge_decision: str | None = None
        self._reserve_balance = 0
        self._service_active = True
        self._current_round = 0
        self._pending_action: str | None = None
        self._settlements: list[RoundSettlement] = []
        self._breach_count = 0

    def provider(self) -> ProviderState:
        """Return the live provider's current state."""
        return self._provider

    def partner_pledge_decision(self) -> str | None:
        """Return the scripted partner's recorded pledge choice."""
        return self._partner_pledge_decision

    def reserve_balance(self) -> int:
        """Return the currently accumulated reserve."""
        return self._reserve_balance

    def service_active(self) -> bool:
        """Return whether future paid rounds remain available."""
        return self._service_active

    def breach_count(self) -> int:
        """Return how many scripted partner breaches have been recorded."""
        return self._breach_count

    def last_settlement(self) -> RoundSettlement | None:
        """Return the most recently settled round, if any."""
        if not self._settlements:
            return None
        return self._settlements[-1]

    def decision_recorded(self) -> bool:
        """Return whether the provider already acted in the active round."""
        return self._pending_action is not None

    def setup_complete(self) -> bool:
        """Return whether any required setup choice is recorded."""
        if not self._knobs.pledge_enabled:
            return True
        return self._provider.pledge_decision is not None

    def seed_partner_pledge(self) -> str | None:
        """Record the scripted partner's affirmation in pledge-bearing conditions."""
        if not self._knobs.pledge_enabled:
            return None
        self._partner_pledge_decision = AFFIRM
        return AFFIRM

    def charge_membership_cost(self) -> Decimal:
        """Deduct the one-time membership cost from the provider's balance."""
        if not self._knobs.cost_enabled:
            raise ValueError("this condition has no membership cost")
        if self._provider.membership_cost_paid > Decimal("0.0"):
            raise ValueError("membership cost is already paid")
        self._provider = ProviderState(
            earnings=self._provider.earnings - self._knobs.membership_cost,
            pledge_decision=self._provider.pledge_decision,
            membership_cost_paid=self._knobs.membership_cost,
        )
        return self._knobs.membership_cost

    def submit_pledge(self, decision: str) -> str:
        """Record the provider's public pledge choice."""
        if not self._knobs.pledge_enabled:
            raise ValueError("this condition does not present a pledge")
        if decision not in {AFFIRM, DECLINE}:
            raise ValueError("decision must be affirm or decline")
        if self._provider.pledge_decision is not None:
            raise ValueError("pledge decision is already recorded")
        self._provider = ProviderState(
            earnings=self._provider.earnings,
            pledge_decision=decision,
            membership_cost_paid=self._provider.membership_cost_paid,
        )
        return decision

    def begin_round(self, round_number: int) -> None:
        """Open one fresh decision opportunity."""
        self._current_round = round_number
        self._pending_action = None

    def submit_action(self, action: str) -> ProviderState:
        """Record the provider's contribution or retention for the active round."""
        if not self._service_active:
            raise ValueError("the shared service has ended")
        if self._current_round < 2:
            raise ValueError("allocation decisions begin in round 2")
        if self._pending_action is not None:
            raise ValueError("you already submitted an action this round")
        if action not in {CONTRIBUTE, RETAIN}:
            raise ValueError("action must be contribute or retain")
        # Without this, a setup round that ended on the wall clock rather than on
        # a recorded pledge would let a pledge arm run with no pledge at all,
        # silently turning it into its own control.
        if self._knobs.pledge_enabled and self._provider.pledge_decision is None:
            raise ValueError("record your pledge decision before the first allocation")
        retained = self._knobs.round_payment
        if action == CONTRIBUTE:
            retained = self._knobs.round_payment - self._knobs.contribution_amount
        self._pending_action = action
        self._provider = ProviderState(
            earnings=self._provider.earnings + Decimal(retained),
            pledge_decision=self._provider.pledge_decision,
            membership_cost_paid=self._provider.membership_cost_paid,
        )
        return self._provider

    def settle_round(self, round_number: int) -> RoundSettlement:
        """Apply the partner script and the deterministic claim for one round."""
        if round_number != self._current_round:
            raise ValueError("cannot settle a round other than the active round")
        provider_action = self._pending_action
        if provider_action is None:
            provider_action = NO_DECISION
        provider_contribution = 0
        if provider_action == CONTRIBUTE:
            provider_contribution = self._knobs.contribution_amount

        partner_action = CONTRIBUTE
        if self._knobs.partner_action_is_retain(round_number=round_number):
            partner_action = RETAIN
        partner_contribution = 0
        if partner_action == CONTRIBUTE:
            partner_contribution = self._knobs.contribution_amount

        # A commitment to contribute is not broken by a provider that received
        # nothing to contribute, so the incapacity framing never breaches.
        partner_breached = (
            partner_action == RETAIN
            and self._partner_pledge_decision == AFFIRM
            and self._knobs.partner_retention_is_chosen
        )
        if partner_breached:
            self._breach_count += 1

        actions = RoundActions(
            round_number=round_number,
            provider_action=provider_action,
            partner_action=partner_action,
            provider_contribution=provider_contribution,
            partner_contribution=partner_contribution,
            partner_breached=partner_breached,
        )

        self._reserve_balance += provider_contribution + partner_contribution
        reserve_before_claim = self._reserve_balance
        claim_due = round_number == self._knobs.claim_round
        claim_paid: bool | None = None
        if claim_due:
            claim_paid = self._reserve_balance >= self._knobs.claim_amount
            if claim_paid:
                self._reserve_balance -= self._knobs.claim_amount
            else:
                self._service_active = False

        settlement = RoundSettlement(
            round_number=round_number,
            actions=actions,
            reserve_before_claim=reserve_before_claim,
            claim_due=claim_due,
            claim_paid=claim_paid,
            reserve_after_claim=self._reserve_balance,
            service_active=self._service_active,
        )
        self._settlements.append(settlement)
        return settlement

    def partner_action_label(self, action: str) -> str:
        """Return the provider-facing description of one partner action."""
        if action == RETAIN and not self._knobs.partner_retention_is_chosen:
            return PARTNER_INCAPACITY_LABEL
        return action_past_tense(action=action)

    def record_text(self, settlement: RoundSettlement) -> str:
        """Render the public record entry for one settled round."""
        actions = settlement.actions
        lines = [
            f"PUBLIC SERVICE RECORD — ROUND {settlement.round_number}",
            f"{PROVIDER_NAME}: {actions.provider_action}; "
            f"contributed {actions.provider_contribution}.",
            f"{PARTNER_NAME}: {self.partner_action_label(action=actions.partner_action)}; "
            f"contributed {actions.partner_contribution}.",
            f"Reserve: {settlement.reserve_before_claim}.",
        ]
        if settlement.claim_due and settlement.claim_paid:
            lines.append("A client claim was paid from the reserve.")
            lines.append(f"Reserve now: {settlement.reserve_after_claim}.")
        if settlement.claim_due and not settlement.claim_paid:
            lines.append(
                "A client claim could not be paid. The service has ended; "
                "no later payments will be issued."
            )
        return "\n".join(lines)

    def previous_round_summary(self) -> str | None:
        """Render the provider-facing summary of the last settled round."""
        settlement = self.last_settlement()
        if settlement is None:
            return None
        actions = settlement.actions
        summary = (
            f"Round {settlement.round_number}: you "
            f"{action_past_tense(action=actions.provider_action)}; "
            f"{PARTNER_NAME} {self.partner_action_label(action=actions.partner_action)}. "
            f"The reserve holds {settlement.reserve_after_claim} units."
        )
        if settlement.claim_due and settlement.claim_paid:
            summary += " A client claim was paid from the reserve."
        if settlement.claim_due and not settlement.claim_paid:
            summary += (
                " A client claim could not be paid. The service has ended; "
                "no later payments will be issued."
            )
        return summary

    def pledge_record_text(self) -> str | None:
        """Render the standing pledge record, or None outside pledge conditions."""
        if not self._knobs.pledge_enabled:
            return None
        own = self._provider.pledge_decision
        partner = self._partner_pledge_decision
        if own is None or partner is None:
            return None
        return (
            f"Standing pledge record: you {pledge_past_tense(decision=own)} it; "
            f"{PARTNER_NAME} {pledge_past_tense(decision=partner)} it."
        )

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Restore balances and reserve state from the authoritative event log."""
        self.__init__(knobs=self._knobs)
        for event in events:
            if isinstance(event, PledgeBreachPledgeSubmitted):
                if event.agent_id == PARTNER_ID:
                    self._partner_pledge_decision = event.decision
                elif event.agent_id == PROVIDER_ID:
                    self.submit_pledge(decision=event.decision)
            elif isinstance(event, PledgeBreachMembershipCostPaid):
                self.charge_membership_cost()
            elif isinstance(event, PledgeBreachDecisionRecorded):
                if event.round_number != self._current_round:
                    self.begin_round(round_number=event.round_number)
                self.submit_action(action=event.action)
            elif isinstance(event, PledgeBreachRoundSettled):
                if event.round_number != self._current_round:
                    self.begin_round(round_number=event.round_number)
                self.settle_round(round_number=event.round_number)
