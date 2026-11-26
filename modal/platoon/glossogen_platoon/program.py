"""``program: glossogen-signal-game``: run the root harness, then give each seat's trajectory its
rounds as spans.

Each trajectory of a seat that platoon served gets the sum of its round scores as its reward, and
``misc["spans"]``: one span for each round of the game, in round order, holding the seat's model
calls of that round with the round's score as the span's reward. A span's place in the list is
therefore its round. A call is matched to its round by order: the seat's n-th answered call is its
n-th ``llm_response_received`` in the event log, whose round the scorer gives. An answered call
holds text or a tool call. pydantic-ai asks the model again after an empty answer, and GlossoGen
logs no response for it, so an empty call is in no span. Calls before the seat's first tool call
(round 0) are in no span either. A call in no span trains on no round's score. A seat whose
answered calls and logged responses differ in number fails the episode.

The rollout setting ``extra.glossogen_reward`` names the reward that trains, ``first_item`` or
``win``. The episode's outcome holds the mean score per player-round under that reward (``reward``),
and under each reward by its name.
"""

from collections import defaultdict
from typing import Any

import platoon as pt
from glossogen_platoon.game_scores import GameScores, PlayedGame, SeatScores

PROGRAM_NAME = "glossogen-signal-game"
REWARD_SETTING = "glossogen_reward"
PRIMARY_REWARD = "reward"


def is_answered(*, step: Any) -> bool:
    """Whether a recorded call's answer holds text or a tool call."""
    message = step.misc["message"]
    if message.get("tool_calls"):
        return True
    content = message.get("content")
    if content is None:
        return False
    return str(content).strip() != ""


def call_ids(*, trajectory: Any) -> list[str]:
    """The ids of a trajectory's answered model calls, in order."""
    return [
        step.misc["action_misc"]["completion_id"]
        for step in trajectory.steps
        if is_answered(step=step)
    ]


def round_spans(
    *, calls: list[str], seat: SeatScores, rounds: list[int], reward: str
) -> list[dict[str, Any]]:
    """One span per round of the game, in round order: the seat's calls of that round and its
    score."""
    if len(calls) != len(seat.answer_rounds):
        raise ValueError(
            f"{len(calls)} answered calls, but {len(seat.answer_rounds)} logged responses"
        )
    calls_by_round: dict[int, list[str]] = defaultdict(list)
    for call, round_number in zip(calls, seat.answer_rounds, strict=True):
        calls_by_round[round_number].append(call)
    return [
        {"calls": calls_by_round[round_number], "reward": float(seat.scores[reward][round_number])}
        for round_number in rounds
    ]


class SeatRewards:
    """A finalizer that sets each platoon seat's reward and round spans from the game's scores."""

    def __init__(self, *, game: PlayedGame, reward: str) -> None:
        self.game = game
        self.reward = reward

    def __call__(self, collection: pt.TrajectoryCollection) -> None:
        """Set the reward and spans of every trajectory that belongs to a seat's agent."""
        agent_seats = {agent_id: seat for seat, agent_id in self.game.seat_agents.items()}
        for trajectory in collection.trajectories.values():
            agent_id = trajectory.misc["agent"]["agent_id"]
            if agent_id not in agent_seats:
                continue
            seat = self.game.scores.seats[agent_seats[agent_id]]
            spans = round_spans(
                calls=call_ids(trajectory=trajectory),
                seat=seat,
                rounds=self.game.scores.rounds,
                reward=self.reward,
            )
            trajectory.misc["spans"] = spans
            trajectory.misc["calls_outside_rounds"] = sum(
                1 for round_number in seat.answer_rounds if round_number == 0
            )
            trajectory.misc["empty_calls"] = sum(
                1 for step in trajectory.steps if not is_answered(step=step)
            )
            trajectory.reward = sum(span["reward"] for span in spans)


def mean_score(*, scores: GameScores, reward: str) -> float:
    """The mean score per player-round under ``reward``, over every seat and round of the game."""
    values = [
        seat.scores[reward][round_number]
        for seat in scores.seats.values()
        for round_number in scores.rounds
    ]
    return sum(values) / len(values)


def outcome_rewards(*, scores: GameScores, reward: str) -> dict[str, float]:
    """The episode's rewards: the trained reward's mean score, and each reward's under its name."""
    names = next(iter(scores.seats.values())).scores.keys()
    rewards = {name: mean_score(scores=scores, reward=name) for name in names}
    rewards[PRIMARY_REWARD] = rewards[reward]
    return rewards


@pt.program(PROGRAM_NAME)
async def signal_game_program(ep: pt.EpisodeContext) -> pt.Outcome:
    """Run the root harness, add the seat finalizer, and grade the episode by the trained reward."""
    result = await ep.run()
    recorded = ep.root.misc.get("glossogen")
    if result.status != "completed" or recorded is None:
        return pt.Outcome(status="error", reason=f"the game did not run: {result.status}")
    game = PlayedGame.model_validate(recorded)
    if not game.scores.finished or not game.scores.rounds:
        return pt.Outcome(status="error", reason=f"game {game.run_id} did not finish")
    reward = str(ep.config.extra[REWARD_SETTING])
    ep.add_finalizer(SeatRewards(game=game, reward=reward))
    return pt.Outcome(status="scored", rewards=outcome_rewards(scores=game.scores, reward=reward))
