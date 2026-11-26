"""A step's finished games, their advantages, the training batch and the counts that describe them.

A player's advantage in a round is its score minus the mean score of the same seat in the same
round, over the seed's finished games. When a seed has fewer than 2 finished games, every
answer token of its finished game gets advantage 0. The batch holds the training sequences of
the trained seats of each finished game (token_sequences.py).
"""

from collections import defaultdict
from collections.abc import Callable
from typing import NamedTuple

from grpo_records import TrainingSequence
from loop_services import SCENARIO, Game, LoopSettings
from partner import Partner, trained_seats
from signal_game_rewards import GameOutcome, PlayerRound, Reward, game_outcome, player_score
from token_sequences import game_sequences

from glossogen.models.event import SimulationEvent
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.run_file_paths import event_log_path


class FinishedGame(NamedTuple):
    """A game that ended with ``simulation_ended``, with its events and its outcome."""

    game: Game
    events: list[SimulationEvent]
    outcome: GameOutcome


class PlayerRoundAdvantage(NamedTuple):
    """One player's advantage in one round of one game."""

    run_id: str
    player_round: PlayerRound
    advantage: float


class Batch(NamedTuple):
    """The training sequences of a step, and counts that describe them."""

    sequences: list[TrainingSequence]
    answers: int
    answer_tokens: int
    sequence_tokens: int
    chain_breaks: int


async def finished_games(*, settings: LoopSettings, games: list[Game]) -> list[FinishedGame]:
    """The games whose event log holds ``simulation_ended``, read with their outcomes."""
    finished: list[FinishedGame] = []
    for game in games:
        log_path = event_log_path(run_dir=settings.runs_dir / game.run_id, scenario_name=SCENARIO)
        events = await load_events(log_path=log_path)
        outcome = game_outcome(events=events)
        if outcome.finished:
            finished.append(FinishedGame(game=game, events=events, outcome=outcome))
    return finished


def seed_advantages(*, group: list[FinishedGame], reward: Reward) -> list[PlayerRoundAdvantage]:
    """Each player's score in each round, minus the seat's mean score in that round in the group."""
    if len(group) < 2:
        return []
    advantages: list[PlayerRoundAdvantage] = []
    player_rounds = {
        PlayerRound(player=player, round_number=round_number)
        for finished in group
        for player in finished.outcome.players
        for round_number in finished.outcome.rounds
    }
    for player_round in sorted(player_rounds):
        scores = [
            player_score(outcome=finished.outcome, player_round=player_round, reward=reward)
            for finished in group
        ]
        mean = sum(scores) / len(scores)
        for finished, score in zip(group, scores, strict=True):
            advantages.append(
                PlayerRoundAdvantage(
                    run_id=finished.game.run_id,
                    player_round=player_round,
                    advantage=score - mean,
                )
            )
    return advantages


def step_advantages(*, finished: list[FinishedGame], reward: Reward) -> list[PlayerRoundAdvantage]:
    """The advantages of every finished game, each against the mean of its seed's finished games."""
    by_seed: dict[int, list[FinishedGame]] = defaultdict(list)
    for game in finished:
        by_seed[game.game.seed].append(game)
    return [
        advantage
        for group in by_seed.values()
        for advantage in seed_advantages(group=group, reward=reward)
    ]


def batch(
    *,
    finished: list[FinishedGame],
    advantages: list[PlayerRoundAdvantage],
    partner: Partner | None,
) -> Batch:
    """The training sequences of every finished game's trained seats, one player at a time."""
    sequences: list[TrainingSequence] = []
    answers = answer_tokens = sequence_tokens = chain_breaks = 0
    for game in finished:
        for player in trained_seats(players=game.outcome.players, partner=partner):
            by_round = {
                advantage.player_round.round_number: advantage.advantage
                for advantage in advantages
                if advantage.run_id == game.game.run_id and advantage.player_round.player == player
            }
            built = game_sequences(events=game.events, agent_id=player, advantages=by_round)
            sequences.extend(built.sequences)
            answers += built.answers
            answer_tokens += built.answer_tokens
            sequence_tokens += built.sequence_tokens
            chain_breaks += built.chain_breaks
    return Batch(
        sequences=sequences,
        answers=answers,
        answer_tokens=answer_tokens,
        sequence_tokens=sequence_tokens,
        chain_breaks=chain_breaks,
    )


def counts_by_seed(
    *, finished: list[FinishedGame], count: Callable[[GameOutcome], int]
) -> dict[str, list[int]]:
    """``count`` of each finished game's outcome, in game order, grouped by seed."""
    grouped: dict[str, list[int]] = defaultdict(list)
    for game in sorted(finished, key=lambda game: (game.game.seed, game.game.game)):
        grouped[str(game.game.seed)].append(count(game.outcome))
    return dict(grouped)


def rounds_won(outcome: GameOutcome) -> int:
    """The number of rounds that the game's players won."""
    return len(outcome.won_rounds)


def first_item_count(outcome: GameOutcome) -> int:
    """The number of the game's player-rounds that ended on the player's first item."""
    return len(outcome.first_item_finishes)


def first_item_by_seat(*, finished: list[FinishedGame]) -> dict[str, int]:
    """The player-rounds that ended on the player's first item, counted for each seat."""
    counts: dict[str, int] = {}
    for game in finished:
        for player in game.outcome.players:
            counts.setdefault(player, 0)
        for finish in game.outcome.first_item_finishes:
            counts[finish.player] += 1
    return dict(sorted(counts.items()))


def player_rounds(*, finished: list[FinishedGame]) -> int:
    """The player-rounds of the finished games."""
    return sum(len(game.outcome.rounds) * len(game.outcome.players) for game in finished)
