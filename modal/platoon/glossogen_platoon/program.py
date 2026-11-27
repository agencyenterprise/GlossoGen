"""``program: glossogen-signal-game``: run the root harness, then give each seat's trajectory its
rounds as spans.

Each trajectory of a seat that platoon served gets the sum of its round scores as its reward, and
``misc["spans"]``: one span for each round of the game, in round order, holding the seat's model
calls of that round with the round's score as the span's reward. A span's place in the list is
therefore its round. The scorer gives each logged ``llm_response_received`` its round and its
``answer_key``: its tool names and the start of its text. The program walks the seat's recorded
calls in order and matches each logged response with the next call that has the same key. The
gateway records some calls that GlossoGen logs no response for: pydantic-ai asks the model again
after an empty answer or a call to a tool that does not exist. Such a call matches no logged
response, so it is in no span. Calls before the seat's first tool call (round 0) are in no span
either. A call in no span trains on no round's score. A logged response that no recorded call
matches fails the episode.

The rollout setting ``extra.glossogen_reward`` names the reward that trains, ``first_item`` or
``win``. The episode's outcome holds the mean score per player-round under that reward (``reward``),
and under each reward by its name.
"""

from collections import defaultdict
from typing import Any, NamedTuple

import platoon as pt
from glossogen_platoon.game_scores import GameScores, PlayedGame, SeatScores, answer_key

PROGRAM_NAME = "glossogen-signal-game"
REWARD_SETTING = "glossogen_reward"
PRIMARY_REWARD = "reward"


class RecordedCall(NamedTuple):
    """One model call that platoon's gateway recorded: its completion id and its ``answer_key``."""

    call_id: str
    key: str


def recorded_calls(*, trajectory: Any) -> list[RecordedCall]:
    """A trajectory's recorded model calls, in order."""
    calls: list[RecordedCall] = []
    for step in trajectory.steps:
        message = step.misc["message"]
        tool_names = [call["function"]["name"] for call in message.get("tool_calls") or []]
        content = message.get("content")
        text = None
        if content is not None:
            text = str(content)
        calls.append(
            RecordedCall(
                call_id=step.misc["action_misc"]["completion_id"],
                key=answer_key(tool_names=tool_names, text=text),
            )
        )
    return calls


def call_rounds(*, calls: list[RecordedCall], seat: SeatScores) -> dict[str, int]:
    """The round of each recorded call that matches a logged response, by call id. Each logged
    response matches the next recorded call with the same key."""
    rounds: dict[str, int] = {}
    position = 0
    for key, round_number in zip(seat.answer_keys, seat.answer_rounds, strict=True):
        while position < len(calls) and calls[position].key != key:
            position += 1
        if position == len(calls):
            raise ValueError(f"no recorded call matches the logged response {key!r}")
        rounds[calls[position].call_id] = round_number
        position += 1
    return rounds


def round_spans(
    *, calls: list[RecordedCall], seat: SeatScores, rounds: list[int], reward: str
) -> list[dict[str, Any]]:
    """One span per round of the game, in round order: the seat's calls of that round and its
    score."""
    matched = call_rounds(calls=calls, seat=seat)
    calls_by_round: dict[int, list[str]] = defaultdict(list)
    for call in calls:
        if call.call_id in matched:
            calls_by_round[matched[call.call_id]].append(call.call_id)
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
            calls = recorded_calls(trajectory=trajectory)
            spans = round_spans(
                calls=calls,
                seat=seat,
                rounds=self.game.scores.rounds,
                reward=self.reward,
            )
            trajectory.misc["spans"] = spans
            trajectory.misc["calls_outside_rounds"] = sum(
                1 for round_number in seat.answer_rounds if round_number == 0
            )
            trajectory.misc["unlogged_calls"] = len(calls) - len(seat.answer_rounds)
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
