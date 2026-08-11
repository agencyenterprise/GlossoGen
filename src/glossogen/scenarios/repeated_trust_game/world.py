"""Deterministic state machine for repeated human-parallel trust games."""

from typing import Any

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.repeated_trust_game.events import (
    RepeatedTrustDecisionRecorded,
    RepeatedTrustPledgeSubmitted,
    RepeatedTrustRoundSettled,
)
from glossogen.scenarios.repeated_trust_game.ids import (
    PARTICIPANT_A_ID,
    PARTICIPANT_IDS,
    TRUSTEE_ROLE,
    TRUSTOR_ROLE,
)
from glossogen.scenarios.repeated_trust_game.knobs import RepeatedTrustGameKnobs
from glossogen.scenarios.repeated_trust_game.state import (
    DecisionRecord,
    ParticipantState,
    RoundOutcome,
)

_AFFIRM = "affirm"
_DECLINE = "decline"


class RepeatedTrustGameWorld(ScenarioWorld):
    """Tracks pledge, role-specific choices, and realized decision earnings."""

    def __init__(self, knobs: RepeatedTrustGameKnobs) -> None:
        self._knobs = knobs
        self._participants: dict[str, ParticipantState] = {
            agent_id: ParticipantState(balance=0.0, forfeiture_paid=0.0, pledge_decision=None)
            for agent_id in PARTICIPANT_IDS
        }
        self._current_round = 0
        self._decisions: dict[str, DecisionRecord] = {}
        self._outcomes: list[RoundOutcome] = []
        self._current_round_settled = False

    def participant(self, agent_id: str) -> ParticipantState:
        """Return the cumulative state for one known participant."""
        return self._participants[agent_id]

    def previous_outcome(self) -> RoundOutcome | None:
        """Return the latest settled round outcome when one exists."""
        if len(self._outcomes) == 0:
            return None
        return self._outcomes[-1]

    def role_for(self, round_number: int, agent_id: str) -> str:
        """Return the counterbalanced role for one participant and round."""
        if agent_id not in PARTICIPANT_IDS:
            raise ValueError("unknown participant")
        participant_a_is_trustor = round_number % 2 == 1
        if agent_id == PARTICIPANT_A_ID:
            if participant_a_is_trustor:
                return TRUSTOR_ROLE
            return TRUSTEE_ROLE
        if participant_a_is_trustor:
            return TRUSTEE_ROLE
        return TRUSTOR_ROLE

    def participant_for_role(self, round_number: int, role: str) -> str:
        """Return the participant assigned to one role for the current round."""
        if role not in {TRUSTOR_ROLE, TRUSTEE_ROLE}:
            raise ValueError("unknown trust-game role")
        for agent_id in PARTICIPANT_IDS:
            if self.role_for(round_number=round_number, agent_id=agent_id) == role:
                return agent_id
        raise ValueError("round has no participant for requested role")

    def begin_round(self, round_number: int) -> None:
        """Open the counterbalanced trust and reciprocity decisions."""
        self._current_round = round_number
        self._decisions = {}
        self._current_round_settled = False

    def submit_pledge(self, agent_id: str, decision: str) -> str:
        """Store one covenant participant's affirmative or declining decision."""
        if not self._knobs.pledge_enabled:
            raise ValueError("this condition does not present a covenant pledge")
        if agent_id not in self._participants:
            raise ValueError("unknown participant")
        if decision not in {_AFFIRM, _DECLINE}:
            raise ValueError("decision must be affirm or decline")
        participant = self._participants[agent_id]
        if participant.pledge_decision is not None:
            raise ValueError("pledge decision is already recorded")
        self._participants[agent_id] = ParticipantState(
            balance=participant.balance,
            forfeiture_paid=participant.forfeiture_paid,
            pledge_decision=decision,
        )
        return decision

    def record_decision(self, agent_id: str, role: str, amount: int) -> DecisionRecord:
        """Apply one role-specific amount and record retained decision earnings."""
        if self._current_round < 1:
            raise ValueError("no round is open")
        if agent_id in self._decisions:
            raise ValueError("you already made this round's decision")
        if role != self.role_for(round_number=self._current_round, agent_id=agent_id):
            raise ValueError("this tool is not available for your role this round")
        participant = self._participants[agent_id]
        if self._knobs.pledge_enabled and participant.pledge_decision is None:
            raise ValueError("record a pledge decision before making a game decision")
        maximum_amount = self._maximum_amount(role=role)
        if amount < 0 or amount > maximum_amount:
            raise ValueError(f"amount must be an integer from 0 to {maximum_amount}")
        gross_earnings = float(maximum_amount - amount)
        forfeiture_paid = 0.0
        if self._knobs.forfeiture_enabled:
            forfeiture_paid = round(
                gross_earnings * self._knobs.forfeiture_fraction,
                ndigits=2,
            )
        net_earnings = round(gross_earnings - forfeiture_paid, ndigits=2)
        record = DecisionRecord(
            agent_id=agent_id,
            role=role,
            amount=amount,
            maximum_amount=maximum_amount,
            gross_earnings=gross_earnings,
            forfeiture_paid=forfeiture_paid,
            net_earnings=net_earnings,
            balance_before=participant.balance,
            balance_after=round(participant.balance + net_earnings, ndigits=2),
        )
        self._decisions[agent_id] = record
        self._participants[agent_id] = ParticipantState(
            balance=record.balance_after,
            forfeiture_paid=participant.forfeiture_paid + forfeiture_paid,
            pledge_decision=participant.pledge_decision,
        )
        return record

    def decisions_complete(self) -> bool:
        """Return whether both role-specific decisions are recorded."""
        return len(self._decisions) == len(PARTICIPANT_IDS)

    def settle_round(self, round_number: int) -> RoundOutcome:
        """Freeze one round's trust and reciprocity amounts."""
        if self._current_round_settled:
            return self._outcomes[-1]
        trustor_id = self.participant_for_role(round_number=round_number, role=TRUSTOR_ROLE)
        trustee_id = self.participant_for_role(round_number=round_number, role=TRUSTEE_ROLE)
        trust_record = self._decisions.get(trustor_id)
        return_record = self._decisions.get(trustee_id)
        missing = tuple(agent_id for agent_id in PARTICIPANT_IDS if agent_id not in self._decisions)
        outcome = RoundOutcome(
            round_number=round_number,
            completed=len(missing) == 0,
            missing_participant_ids=missing,
            trustor_id=trustor_id,
            trustee_id=trustee_id,
            trust_sent=None if trust_record is None else trust_record.amount,
            reciprocity_returned=None if return_record is None else return_record.amount,
        )
        self._outcomes.append(outcome)
        self._current_round_settled = True
        return outcome

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Rebuild participant state and settled outcomes after a resumed run."""
        self.__init__(knobs=self._knobs)
        outcomes: list[RoundOutcome] = []
        for event in events:
            if isinstance(event, RepeatedTrustPledgeSubmitted):
                participant = self._participants[event.agent_id]
                self._participants[event.agent_id] = ParticipantState(
                    balance=participant.balance,
                    forfeiture_paid=participant.forfeiture_paid,
                    pledge_decision=event.decision,
                )
            elif isinstance(event, RepeatedTrustDecisionRecorded):
                participant = self._participants[event.agent_id]
                self._participants[event.agent_id] = ParticipantState(
                    balance=event.balance_after,
                    forfeiture_paid=participant.forfeiture_paid + event.forfeiture_paid,
                    pledge_decision=participant.pledge_decision,
                )
            elif isinstance(event, RepeatedTrustRoundSettled):
                outcomes.append(
                    RoundOutcome(
                        round_number=event.round_number,
                        completed=event.completed,
                        missing_participant_ids=tuple(event.missing_participant_ids),
                        trustor_id=event.trustor_id,
                        trustee_id=event.trustee_id,
                        trust_sent=event.trust_sent,
                        reciprocity_returned=event.reciprocity_returned,
                    )
                )
        self._outcomes = outcomes
        self._current_round = max((outcome.round_number for outcome in outcomes), default=0)
        self._decisions = {}
        self._current_round_settled = False

    def _maximum_amount(self, role: str) -> int:
        """Return the available amount in the specified decision role."""
        if role == TRUSTOR_ROLE:
            return self._knobs.trustor_endowment
        if role == TRUSTEE_ROLE:
            return self._knobs.fixed_trustee_endowment
        raise ValueError("unknown trust-game role")
