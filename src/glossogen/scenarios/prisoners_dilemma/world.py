"""Living world for the Prisoner's Dilemma scenario.

Tracks each player's decision for the in-progress round and resolves the
round's payoff as soon as both players have submitted via
``submit_decision``. All resolution logic is deterministic arithmetic over
the configured payoff matrix. There is no LLM judge involved anywhere in
this scenario.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld, WorldContext
from glossogen.scenarios.prisoners_dilemma.ids import PLAYER_A_ID, PLAYER_B_ID, Decision


class RoundOutcome(NamedTuple):
    """The resolved outcome of one completed round."""

    round_number: int
    player_a_decision: Decision
    player_b_decision: Decision
    player_a_payoff: float
    player_b_payoff: float
    resolved_early: bool


class PrisonersDilemmaWorld(ScenarioWorld):
    """Tracks in-round decisions, cumulative scores, and resolved round history."""

    _context: WorldContext

    def __init__(
        self,
        payoff_temptation: float,
        payoff_reward: float,
        payoff_punishment: float,
        payoff_sucker: float,
    ) -> None:
        super().__init__(
            postmortem_channel_ids=frozenset(),
            postmortem_globally_disabled=False,
        )
        self._payoff_temptation = payoff_temptation
        self._payoff_reward = payoff_reward
        self._payoff_punishment = payoff_punishment
        self._payoff_sucker = payoff_sucker
        self._pending_decisions: dict[str, Decision] = {}
        self._cumulative_scores: dict[str, float] = {PLAYER_A_ID: 0.0, PLAYER_B_ID: 0.0}
        self._round_history: list[RoundOutcome] = []

    @property
    def context(self) -> WorldContext:
        """Return the attached ``WorldContext``. Valid after ``run`` is started."""
        return self._context

    @property
    def cumulative_scores(self) -> dict[str, float]:
        """Return each player's running total payoff across all resolved rounds."""
        return dict(self._cumulative_scores)

    def start_new_round(self) -> None:
        """Clear pending decisions so both players can submit for the new round."""
        self._pending_decisions = {}

    def is_round_resolved(self, round_number: int) -> bool:
        """Return True once the given round's outcome has been recorded."""
        return any(outcome.round_number == round_number for outcome in self._round_history)

    def get_outcome(self, round_number: int) -> RoundOutcome | None:
        """Return the resolved outcome for ``round_number``, or None if unresolved."""
        for outcome in self._round_history:
            if outcome.round_number == round_number:
                return outcome
        return None

    def record_decision(self, agent_id: str, decision: Decision) -> bool:
        """Record one player's decision. Returns True once both players have decided.

        Raises ``ValueError`` if the agent already submitted a decision this
        round. Callers use this to reject a duplicate ``submit_decision`` call.
        """
        if agent_id in self._pending_decisions:
            raise ValueError(f"{agent_id} already submitted a decision this round")
        self._pending_decisions[agent_id] = decision
        return len(self._pending_decisions) == 2

    def resolve_round(self, round_number: int) -> RoundOutcome:
        """Compute payoffs now that both decisions are in, and record history."""
        a_decision = self._pending_decisions[PLAYER_A_ID]
        b_decision = self._pending_decisions[PLAYER_B_ID]
        return self._settle(
            round_number=round_number,
            a_decision=a_decision,
            b_decision=b_decision,
            resolved_early=False,
        )

    def resolve_incomplete_round(self, round_number: int) -> RoundOutcome:
        """Force-resolve a round that ended before both players decided.

        Any player who never called ``submit_decision`` this round is
        treated as having defected. Silence is the safe default a real
        opponent would assume. Called from the game-clock's
        ``on_round_ended`` hook so every round always has a recorded
        outcome, even one ended by timeout or all-agents-idle.
        """
        a_decision = self._pending_decisions.get(PLAYER_A_ID, "defect")
        b_decision = self._pending_decisions.get(PLAYER_B_ID, "defect")
        return self._settle(
            round_number=round_number,
            a_decision=a_decision,
            b_decision=b_decision,
            resolved_early=True,
        )

    def _settle(
        self,
        round_number: int,
        a_decision: Decision,
        b_decision: Decision,
        resolved_early: bool,
    ) -> RoundOutcome:
        a_payoff, b_payoff = self._compute_payoffs(a_decision=a_decision, b_decision=b_decision)
        self._cumulative_scores[PLAYER_A_ID] += a_payoff
        self._cumulative_scores[PLAYER_B_ID] += b_payoff
        outcome = RoundOutcome(
            round_number=round_number,
            player_a_decision=a_decision,
            player_b_decision=b_decision,
            player_a_payoff=a_payoff,
            player_b_payoff=b_payoff,
            resolved_early=resolved_early,
        )
        self._round_history.append(outcome)
        return outcome

    def _compute_payoffs(self, a_decision: Decision, b_decision: Decision) -> tuple[float, float]:
        if a_decision == "cooperate" and b_decision == "cooperate":
            return self._payoff_reward, self._payoff_reward
        if a_decision == "defect" and b_decision == "defect":
            return self._payoff_punishment, self._payoff_punishment
        if a_decision == "defect" and b_decision == "cooperate":
            return self._payoff_temptation, self._payoff_sucker
        return self._payoff_sucker, self._payoff_temptation
