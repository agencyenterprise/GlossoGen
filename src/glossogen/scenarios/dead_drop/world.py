"""Round state for dead_drop: submitted answers, commands spent, and each round's verdict.

The filesystem lives in ``ServerFilesystem``. This world holds what the verdict
and the briefings read: who has submitted, whether each answer was right, and
how many commands each agent has run this round.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.dead_drop.ids import AGENT_IDS


class Submission(NamedTuple):
    """One agent's locked answer for a round."""

    answers: dict[str, str]
    correct_keys: tuple[str, ...]
    all_correct: bool


class RoundOutcome(NamedTuple):
    """A resolved round: each agent's correctness and how the round ended."""

    round_number: int
    agent_correct: dict[str, bool]
    submitted: tuple[str, ...]
    success: bool
    trigger: str


class DeadDropWorld(ScenarioWorld):
    """Submissions, command counts and verdicts, per round."""

    def __init__(self) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._submissions: dict[int, dict[str, Submission]] = {}
        self._commands_used: dict[int, dict[str, int]] = {}
        self._outcomes: dict[int, RoundOutcome] = {}

    def record_submission(
        self, round_number: int, agent_id: str, answers: dict[str, str], expected: dict[str, str]
    ) -> Submission:
        """Lock ``agent_id``'s answer for the round; raises ``ValueError`` on a second one."""
        submitted = self._submissions.setdefault(round_number, {})
        if agent_id in submitted:
            raise ValueError("You already submitted an answer for this round.")
        correct_keys = tuple(
            sorted(key for key, value in expected.items() if answers[key] == value)
        )
        submission = Submission(
            answers=dict(answers),
            correct_keys=correct_keys,
            all_correct=len(correct_keys) == len(expected),
        )
        submitted[agent_id] = submission
        return submission

    def has_submitted(self, round_number: int, agent_id: str) -> bool:
        """Whether ``agent_id`` has locked an answer for the round."""
        return agent_id in self._submissions.get(round_number, {})

    def both_submitted(self, round_number: int) -> bool:
        """Whether every agent has locked an answer for the round."""
        submitted = self._submissions.get(round_number, {})
        return all(agent_id in submitted for agent_id in AGENT_IDS)

    def use_command(self, round_number: int, agent_id: str) -> int:
        """Count one command for ``agent_id`` this round and return how many it has used."""
        used = self._commands_used.setdefault(round_number, {})
        used[agent_id] = used.get(agent_id, 0) + 1
        return used[agent_id]

    def resolve(self, round_number: int, trigger: str) -> RoundOutcome:
        """Settle the round: an agent that never submitted counts as wrong."""
        submitted = self._submissions.get(round_number, {})
        agent_correct = {
            agent_id: agent_id in submitted and submitted[agent_id].all_correct
            for agent_id in AGENT_IDS
        }
        outcome = RoundOutcome(
            round_number=round_number,
            agent_correct=agent_correct,
            submitted=tuple(sorted(submitted)),
            success=all(agent_correct.values()),
            trigger=trigger,
        )
        self._outcomes[round_number] = outcome
        return outcome

    def restore_submission(self, round_number: int, agent_id: str, submission: Submission) -> None:
        """Seed an answer locked before a fork or resume."""
        self._submissions.setdefault(round_number, {})[agent_id] = submission

    def restore_outcome(self, outcome: RoundOutcome) -> None:
        """Seed a round resolved before a fork or resume."""
        self._outcomes[outcome.round_number] = outcome

    def outcome(self, round_number: int) -> RoundOutcome | None:
        """The round's verdict, or None while it is unresolved."""
        return self._outcomes.get(round_number)
