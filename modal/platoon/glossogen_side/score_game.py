"""Print one finished signal_game game's scores as ``GameScores`` JSON, and write the game's labels.

It runs in GlossoGen's environment, from this project's folder, so that it imports both GlossoGen
and this project's ``glossogen_platoon.game_scores``. The harness runs it after each game:

    cd modal/platoon && VIRTUAL_ENV= uv run --no-sync --project ../.. \\
      python -m glossogen_side.score_game --run-dir <run dir> --labels platoon seed=1000

A seat's ``answer_rounds`` follow one rule: a response takes the round of its first tool call, a
response without a tool call takes the round of the seat's previous tool call, and a response before
the seat's first tool call takes round 0.
"""

import argparse
import asyncio
import json
from pathlib import Path

from glossogen_platoon.game_scores import GameScores, SeatScores, answer_key
from glossogen_side.signal_game_rewards import PlayerRound, Reward, game_outcome, player_score

from glossogen.models.event import LLMResponseReceived, SimulationEvent, ToolCallInvoked
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.run_storage.run_labels_file import RUN_LABELS_FILENAME
from glossogen.scenario_contract.scenario_sources import (
    load_configured_scenario_catalog_unless_loaded,
)

SCENARIO = "signal_game"


def answer_rounds(*, events: list[SimulationEvent], agent_id: str) -> list[int]:
    """The round of each of the agent's model responses, in the order of the event log."""
    call_round = {
        event.call_id: event.round_number for event in events if isinstance(event, ToolCallInvoked)
    }
    rounds: list[int] = []
    current = 0
    for event in events:
        if isinstance(event, LLMResponseReceived) and event.agent_id == agent_id:
            if event.tool_calls:
                current = call_round[event.tool_calls[0].call_id]
            rounds.append(current)
    return rounds


def answer_keys(*, events: list[SimulationEvent], agent_id: str) -> list[str]:
    """The ``answer_key`` of each of the agent's model responses, in the order of the event log."""
    return [
        answer_key(tool_names=[call.tool_name for call in event.tool_calls], text=event.text)
        for event in events
        if isinstance(event, LLMResponseReceived) and event.agent_id == agent_id
    ]


def seat_scores(*, events: list[SimulationEvent], agent_id: str, rounds: list[int]) -> SeatScores:
    """One seat's answer rounds and its score in each round under each reward."""
    outcome = game_outcome(events=events)
    scores = {
        reward.value: {
            round_number: player_score(
                outcome=outcome,
                player_round=PlayerRound(player=agent_id, round_number=round_number),
                reward=reward,
            )
            for round_number in rounds
        }
        for reward in Reward
    }
    return SeatScores(
        answer_rounds=answer_rounds(events=events, agent_id=agent_id),
        answer_keys=answer_keys(events=events, agent_id=agent_id),
        scores=scores,
    )


async def score(*, run_dir: Path) -> GameScores:
    """The scores of the game in ``run_dir``."""
    load_configured_scenario_catalog_unless_loaded()
    events = await load_events(log_path=event_log_path(run_dir=run_dir, scenario_name=SCENARIO))
    outcome = game_outcome(events=events)
    rounds = sorted(outcome.rounds)
    return GameScores(
        finished=outcome.finished,
        rounds=rounds,
        seats={
            player: seat_scores(events=events, agent_id=player, rounds=rounds)
            for player in outcome.players
        },
    )


def write_labels(*, run_dir: Path, labels: list[str]) -> None:
    """Write the game's labels into its run directory's labels file."""
    (run_dir / RUN_LABELS_FILENAME).write_text(json.dumps(labels) + "\n")


def main() -> None:
    """Write the labels, then print the scores."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--labels", required=True, nargs="+")
    arguments = parser.parse_args()
    write_labels(run_dir=arguments.run_dir, labels=arguments.labels)
    print(asyncio.run(score(run_dir=arguments.run_dir)).model_dump_json())


if __name__ == "__main__":
    main()
