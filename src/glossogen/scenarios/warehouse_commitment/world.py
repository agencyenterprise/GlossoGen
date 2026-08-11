"""Deterministic state machine for the warehouse commitment scenario."""

from typing import Any

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.warehouse_commitment.events import (
    WarehouseCommitmentActionChosen,
    WarehouseCommitmentPledgeSubmitted,
    WarehouseCommitmentRoundSettled,
)
from glossogen.scenarios.warehouse_commitment.ids import PROVIDER_IDS
from glossogen.scenarios.warehouse_commitment.knobs import WarehouseCommitmentKnobs
from glossogen.scenarios.warehouse_commitment.state import ActionRecord, ProviderState, RoundOutcome

_AFFIRM = "affirm"
_DECLINE = "decline"
_INSPECT = "inspect"
_SHORTCUT = "shortcut"


class WarehouseCommitmentWorld(ScenarioWorld):
    """Tracks payments, pledge decisions, and one action per provider each round."""

    def __init__(self, knobs: WarehouseCommitmentKnobs) -> None:
        self._knobs = knobs
        self._providers: dict[str, ProviderState] = {
            agent_id: ProviderState(
                balance=knobs.starting_provider_balance,
                forfeiture_paid=0.0,
                pledge_decision=None,
            )
            for agent_id in PROVIDER_IDS
        }
        self._current_round = 0
        self._actions: dict[str, ActionRecord] = {}
        self._outcomes: list[RoundOutcome] = []
        self._current_round_settled = False

    @property
    def outcomes(self) -> list[RoundOutcome]:
        """Return every settled round outcome."""
        return list(self._outcomes)

    @property
    def current_actions(self) -> dict[str, ActionRecord]:
        """Return a copy of current-round actions."""
        return dict(self._actions)

    def provider(self, agent_id: str) -> ProviderState:
        """Return the cumulative state for one known provider."""
        return self._providers[agent_id]

    def previous_outcome(self) -> RoundOutcome | None:
        """Return the latest aggregate result, when a prior round exists."""
        if len(self._outcomes) == 0:
            return None
        return self._outcomes[-1]

    def begin_round(self, round_number: int) -> None:
        """Open a new decision window and clear the preceding actions."""
        self._current_round = round_number
        self._actions = {}
        self._current_round_settled = False

    def submit_pledge(self, agent_id: str, decision: str) -> str:
        """Store a one-time pledge response from one provider."""
        if not self._knobs.pledge_enabled:
            raise ValueError("this condition does not present a covenant pledge")
        if agent_id not in self._providers:
            raise ValueError("unknown provider")
        if decision not in {_AFFIRM, _DECLINE}:
            raise ValueError("decision must be affirm or decline")
        provider = self._providers[agent_id]
        if provider.pledge_decision is not None:
            raise ValueError("pledge decision is already recorded")
        self._providers[agent_id] = ProviderState(
            balance=provider.balance,
            forfeiture_paid=provider.forfeiture_paid,
            pledge_decision=decision,
        )
        return decision

    def choose_action(self, agent_id: str, action: str) -> ActionRecord:
        """Apply one inspection or shortcut action and its fixed payoff."""
        if agent_id not in self._providers:
            raise ValueError("unknown provider")
        if self._current_round < 1:
            raise ValueError("no round is open")
        if agent_id in self._actions:
            raise ValueError("you already chose an action this round")
        provider = self._providers[agent_id]
        if self._knobs.pledge_enabled and provider.pledge_decision is None:
            raise ValueError("record a pledge decision before choosing this round's action")
        if action not in {_INSPECT, _SHORTCUT}:
            raise ValueError("action must be inspect or shortcut")
        inspected = action == _INSPECT
        gross_payment = self._knobs.base_round_payment
        if action == _SHORTCUT:
            gross_payment += self._knobs.shortcut_bonus
        forfeiture_paid = 0.0
        if self._knobs.forfeiture_enabled:
            forfeiture_paid = round(
                gross_payment * self._knobs.forfeiture_fraction,
                ndigits=2,
            )
        net_payment = round(gross_payment - forfeiture_paid, ndigits=2)
        record = ActionRecord(
            agent_id=agent_id,
            action=action,
            inspected=inspected,
            gross_payment=gross_payment,
            forfeiture_paid=forfeiture_paid,
            net_payment=net_payment,
            balance_before=provider.balance,
            balance_after=round(provider.balance + net_payment, ndigits=2),
        )
        self._actions[agent_id] = record
        self._providers[agent_id] = ProviderState(
            balance=record.balance_after,
            forfeiture_paid=provider.forfeiture_paid + forfeiture_paid,
            pledge_decision=provider.pledge_decision,
        )
        return record

    def actions_complete(self) -> bool:
        """Return whether both providers have selected their action."""
        return len(self._actions) == len(PROVIDER_IDS)

    def settle_round(self, round_number: int) -> RoundOutcome:
        """Freeze and return the current round's adherence outcome."""
        if self._current_round_settled:
            return self._outcomes[-1]
        missing = tuple(agent_id for agent_id in PROVIDER_IDS if agent_id not in self._actions)
        inspected = sum(1 for record in self._actions.values() if record.inspected)
        shortcuts = sum(1 for record in self._actions.values() if not record.inspected)
        outcome = RoundOutcome(
            round_number=round_number,
            completed=len(missing) == 0,
            inspected_provider_count=inspected,
            shortcut_provider_count=shortcuts,
            missing_provider_ids=missing,
            joint_inspection=inspected == len(PROVIDER_IDS),
            actions_by_provider={
                agent_id: record.action for agent_id, record in self._actions.items()
            },
        )
        self._outcomes.append(outcome)
        self._current_round_settled = True
        return outcome

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Rebuild balances, pledge choices, and closed outcomes for resume."""
        self.__init__(knobs=self._knobs)
        outcomes: list[RoundOutcome] = []
        for event in events:
            if isinstance(event, WarehouseCommitmentPledgeSubmitted):
                provider = self._providers[event.agent_id]
                self._providers[event.agent_id] = ProviderState(
                    balance=provider.balance,
                    forfeiture_paid=provider.forfeiture_paid,
                    pledge_decision=event.decision,
                )
            elif isinstance(event, WarehouseCommitmentActionChosen):
                provider = self._providers[event.agent_id]
                self._providers[event.agent_id] = ProviderState(
                    balance=event.balance_after,
                    forfeiture_paid=provider.forfeiture_paid + event.forfeiture_paid,
                    pledge_decision=provider.pledge_decision,
                )
            elif isinstance(event, WarehouseCommitmentRoundSettled):
                outcomes.append(
                    RoundOutcome(
                        round_number=event.round_number,
                        completed=event.completed,
                        inspected_provider_count=event.inspected_provider_count,
                        shortcut_provider_count=event.shortcut_provider_count,
                        missing_provider_ids=tuple(event.missing_provider_ids),
                        joint_inspection=event.joint_inspection,
                        actions_by_provider=dict(event.actions_by_provider),
                    )
                )
        self._outcomes = outcomes
        self._current_round = max((outcome.round_number for outcome in outcomes), default=0)
        self._actions = {}
        self._current_round_settled = False
