"""Deterministic common-good state for shared-reserve commitment runs."""

from decimal import Decimal
from typing import Any

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.shared_reserve_commitment.events import (
    SharedReserveDecisionRecorded,
    SharedReserveEntryCostPaid,
    SharedReservePledgeSubmitted,
    SharedReserveRoundSettled,
)
from glossogen.scenarios.shared_reserve_commitment.ids import PROVIDER_IDS
from glossogen.scenarios.shared_reserve_commitment.knobs import (
    LedgerVisibility,
    SharedReserveCommitmentKnobs,
)
from glossogen.scenarios.shared_reserve_commitment.state import (
    ProviderState,
    ReserveDecision,
    RoundSettlement,
)

_AFFIRM = "affirm"
_DECLINE = "decline"
_CONTRIBUTE = "contribute"
_RETAIN = "retain"


class SharedReserveCommitmentWorld(ScenarioWorld):
    """Tracks balances, contributions, shared reserve claims, and service status."""

    def __init__(self, knobs: SharedReserveCommitmentKnobs) -> None:
        self._knobs = knobs
        self._providers: dict[str, ProviderState] = {
            agent_id: ProviderState(
                earnings=knobs.initial_endowment,
                pledge_decision=None,
                entry_cost_paid=Decimal("0.0"),
            )
            for agent_id in PROVIDER_IDS
        }
        self._reserve_balance = 0
        self._service_active = True
        self._current_round = 0
        self._decisions: dict[str, ReserveDecision] = {}
        self._decisions_by_round: dict[int, dict[str, ReserveDecision]] = {}
        self._settlements: list[RoundSettlement] = []

    def provider(self, agent_id: str) -> ProviderState:
        """Return state for one registered provider."""
        return self._providers[agent_id]

    def reserve_balance(self) -> int:
        """Return the currently available common reserve."""
        return self._reserve_balance

    def service_active(self) -> bool:
        """Return whether future paid service rounds remain available."""
        return self._service_active

    def current_round_decisions(self) -> tuple[ReserveDecision, ...]:
        """Return decisions in stable provider order for public settlement."""
        return tuple(self._decisions[agent_id] for agent_id in PROVIDER_IDS)

    def setup_complete(self) -> bool:
        """Return whether any required public pledge choices are recorded."""
        if not self._knobs.pledge_enabled:
            return True
        return all(
            self._providers[agent_id].pledge_decision is not None for agent_id in PROVIDER_IDS
        )

    def decisions_complete(self) -> bool:
        """Return whether both providers acted in the current active service round."""
        return len(self._decisions) == len(PROVIDER_IDS)

    def begin_round(self, round_number: int) -> None:
        """Open one fresh opportunity unless a prior claim ended the service."""
        self._current_round = round_number
        self._decisions = {}

    def submit_pledge(self, agent_id: str, decision: str) -> str:
        """Record one public voluntary pledge choice."""
        if not self._knobs.pledge_enabled:
            raise ValueError("this condition does not present a public pledge")
        if agent_id not in self._providers:
            raise ValueError("unknown provider")
        if decision not in {_AFFIRM, _DECLINE}:
            raise ValueError("decision must be affirm or decline")
        provider = self._providers[agent_id]
        if provider.pledge_decision is not None:
            raise ValueError("pledge decision is already recorded")
        self._providers[agent_id] = ProviderState(
            earnings=provider.earnings,
            pledge_decision=decision,
            entry_cost_paid=provider.entry_cost_paid,
        )
        return decision

    def pay_pledge_entry_cost(self, agent_id: str) -> Decimal:
        """Deduct the one-time cost from an affirming provider's real balance."""
        if not self._knobs.entry_cost_enabled:
            raise ValueError("this condition has no pledge entry cost")
        provider = self._providers[agent_id]
        if provider.pledge_decision != _AFFIRM:
            raise ValueError("only an affirming provider pays the entry cost")
        if provider.entry_cost_paid > Decimal("0.0"):
            raise ValueError("entry cost is already paid")
        self._providers[agent_id] = ProviderState(
            earnings=provider.earnings - self._knobs.pledge_entry_cost,
            pledge_decision=provider.pledge_decision,
            entry_cost_paid=self._knobs.pledge_entry_cost,
        )
        return self._knobs.pledge_entry_cost

    def submit_decision(self, agent_id: str, action: str) -> ReserveDecision:
        """Record one provider's current-round contribution or retention."""
        if not self._service_active:
            raise ValueError("the shared service has ended")
        if self._current_round < 2:
            raise ValueError("allocation decisions begin in round 2")
        if agent_id not in self._providers:
            raise ValueError("unknown provider")
        if agent_id in self._decisions:
            raise ValueError("you already submitted a decision this round")
        if action not in {_CONTRIBUTE, _RETAIN}:
            raise ValueError("action must be contribute or retain")
        provider = self._providers[agent_id]
        if self._knobs.pledge_enabled and provider.pledge_decision is None:
            raise ValueError("record your pledge decision before the first allocation")
        if (
            self._knobs.entry_cost_enabled
            and provider.pledge_decision == _AFFIRM
            and provider.entry_cost_paid == Decimal("0.0")
        ):
            raise ValueError("affirming providers must pay the entry cost before allocation")
        contribution = 0
        retained = self._knobs.client_payment
        if action == _CONTRIBUTE:
            contribution = self._knobs.contribution_amount
            retained = self._knobs.client_payment - contribution
        record = ReserveDecision(
            agent_id=agent_id,
            action=action,
            contribution=contribution,
            retained=retained,
            earnings_before=provider.earnings,
            earnings_after=provider.earnings + Decimal(retained),
        )
        self._providers[agent_id] = ProviderState(
            earnings=record.earnings_after,
            pledge_decision=provider.pledge_decision,
            entry_cost_paid=provider.entry_cost_paid,
        )
        self._decisions[agent_id] = record
        return record

    def settle_round(self, round_number: int) -> RoundSettlement:
        """Apply the deterministic shared claim after submitted or missed actions."""
        if round_number != self._current_round:
            raise ValueError("cannot settle a round other than the active round")
        missing_provider_ids = tuple(
            agent_id for agent_id in PROVIDER_IDS if agent_id not in self._decisions
        )
        for agent_id in missing_provider_ids:
            provider = self._providers[agent_id]
            self._decisions[agent_id] = ReserveDecision(
                agent_id=agent_id,
                action="no_decision",
                contribution=0,
                retained=0,
                earnings_before=provider.earnings,
                earnings_after=provider.earnings,
            )
        contributions = sum(record.contribution for record in self._decisions.values())
        self._reserve_balance += contributions
        reserve_before_claim = self._reserve_balance
        client_claim_due = round_number in self._knobs.client_claim_rounds
        client_claim_paid: bool | None = None
        if client_claim_due:
            client_claim_paid = self._reserve_balance >= self._knobs.client_claim_amount
            if client_claim_paid:
                self._reserve_balance -= self._knobs.client_claim_amount
            else:
                self._service_active = False
        settlement = RoundSettlement(
            round_number=round_number,
            missing_provider_ids=missing_provider_ids,
            reserve_before_claim=reserve_before_claim,
            client_claim_due=client_claim_due,
            client_claim_paid=client_claim_paid,
            reserve_after_claim=self._reserve_balance,
            service_active=self._service_active,
        )
        self._settlements.append(settlement)
        self._decisions_by_round[round_number] = dict(self._decisions)
        return settlement

    def ledger_text(self, settlement: RoundSettlement) -> str:
        """Render the agent-visible public record for one settled round."""
        decision_lines: list[str] = []
        if self._knobs.ledger_visibility == LedgerVisibility.FULL:
            for decision in self.current_round_decisions():
                decision_lines.append(
                    f"{decision.agent_id}: {decision.action}; "
                    f"contributed {decision.contribution}; retained {decision.retained}."
                )
        if self._knobs.claim_amount_disclosed:
            claim_size = f"A {self._knobs.client_claim_amount}-unit client claim"
        else:
            claim_size = "A client claim"
        claim_text = "No client claim was due this round."
        if settlement.client_claim_due and settlement.client_claim_paid:
            claim_text = f"{claim_size} was paid from the reserve."
        if settlement.client_claim_due and not settlement.client_claim_paid:
            claim_text = (
                f"{claim_size} could not be paid. "
                "The shared service has ended; no later payments will be issued."
            )
        lines: list[str] = [
            f"PUBLIC CONTINUITY LEDGER — ROUND {settlement.round_number}",
            *decision_lines,
        ]
        if self._knobs.reserve_balance_disclosed:
            lines.append(f"Reserve before any claim: {settlement.reserve_before_claim}.")
        lines.append(claim_text)
        if self._knobs.reserve_balance_disclosed:
            lines.append(
                f"Reserve now: {settlement.reserve_after_claim}. "
                f"Service active: {settlement.service_active}."
            )
        else:
            lines.append(f"Service active: {settlement.service_active}.")
        return "\n".join(lines)

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Restore balances and reserve state from the authoritative event log."""
        self.__init__(knobs=self._knobs)
        for event in events:
            if isinstance(event, SharedReservePledgeSubmitted):
                self.submit_pledge(agent_id=event.agent_id, decision=event.decision)
            elif isinstance(event, SharedReserveEntryCostPaid):
                self.pay_pledge_entry_cost(agent_id=event.agent_id)
            elif isinstance(event, SharedReserveDecisionRecorded):
                if event.round_number != self._current_round:
                    self.begin_round(round_number=event.round_number)
                self.submit_decision(agent_id=event.agent_id, action=event.action)
            elif isinstance(event, SharedReserveRoundSettled):
                self._reserve_balance = event.reserve_after_claim
                self._service_active = event.service_active
                self._settlements.append(
                    RoundSettlement(
                        round_number=event.round_number,
                        missing_provider_ids=tuple(event.missing_provider_ids),
                        reserve_before_claim=event.reserve_before_claim,
                        client_claim_due=event.client_claim_due,
                        client_claim_paid=event.client_claim_paid,
                        reserve_after_claim=event.reserve_after_claim,
                        service_active=event.service_active,
                    )
                )
                self._decisions_by_round[event.round_number] = dict(self._decisions)
                self._decisions = {}
