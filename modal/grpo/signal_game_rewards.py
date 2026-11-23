"""How the GRPO loop scores a signal_game game: one score per player per round.

The rewards:

- ``win`` scores the round's result, the same for both players.
- ``first_item`` scores 1 when the player ended the round on a square that holds the
  alphabetically first item of its own grid, whatever its partner did. A player can score on it
  without its partner, so a run on it tests whether training changes where players end their
  rounds.

To train on another scenario, write a module like this one. It reads a run's events and gives
each agent a score in each round.
"""

from enum import Enum
from typing import NamedTuple

from glossogen.models.event import AgentRegistered, SimulationEnded, SimulationEvent
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
)


class Reward(str, Enum):
    """The score that a player gets in a round."""

    WIN = "win"
    FIRST_ITEM = "first_item"


class PlayerRound(NamedTuple):
    """One player in one round."""

    player: str
    round_number: int


class GameOutcome(NamedTuple):
    """What a game's event log says about each player in each round.

    ``finished`` says whether the log holds ``simulation_ended``, and ``players`` lists the agent
    ids. ``rounds`` holds the rounds that ended with a result. ``won_rounds`` holds those that the
    players won, and ``first_item_finishes`` the player-rounds that ended on the player's first
    item. ``moves`` counts the accepted moves, and ``player_rounds_without_move`` the player-rounds
    in which the player made none.
    """

    finished: bool
    players: tuple[str, ...]
    rounds: frozenset[int]
    won_rounds: frozenset[int]
    first_item_finishes: frozenset[PlayerRound]
    moves: int
    player_rounds_without_move: int


def game_outcome(*, events: list[SimulationEvent]) -> GameOutcome:
    """Read a signal_game run's events into its outcome."""
    grids: dict[int, dict[str, list[list[str]]]] = {}
    resolved: list[SignalGameRoundResolved] = []
    moved: set[PlayerRound] = set()
    moves = 0
    for event in events:
        if isinstance(event, SignalGameRoundStarted):
            grids[event.round_number] = event.grids
        elif isinstance(event, SignalGameRoundResolved):
            resolved.append(event)
        elif isinstance(event, SignalGameMoveMade):
            moves += 1
            moved.add(PlayerRound(player=event.agent_id, round_number=event.round_number))
    players = tuple(
        sorted({event.agent_id for event in events if isinstance(event, AgentRegistered)})
    )
    return GameOutcome(
        finished=any(isinstance(event, SimulationEnded) for event in events),
        players=players,
        rounds=frozenset(event.round_number for event in resolved),
        won_rounds=frozenset(event.round_number for event in resolved if event.success),
        first_item_finishes=first_item_finishes(resolved=resolved, grids=grids),
        moves=moves,
        player_rounds_without_move=len(players) * len(resolved) - len(moved),
    )


def first_item_finishes(
    *, resolved: list[SignalGameRoundResolved], grids: dict[int, dict[str, list[list[str]]]]
) -> frozenset[PlayerRound]:
    """The player-rounds that ended on a square holding the first item of the player's grid."""
    finishes: set[PlayerRound] = set()
    for event in resolved:
        for player, (row, column) in event.final_squares.items():
            grid = grids[event.round_number][player]
            first = min(item for grid_row in grid for item in grid_row)
            if grid[row - 1][column - 1] == first:
                finishes.add(PlayerRound(player=player, round_number=event.round_number))
    return frozenset(finishes)


def player_score(*, outcome: GameOutcome, player_round: PlayerRound, reward: Reward) -> int:
    """The player's score in the round under ``reward``: 1 or 0."""
    if reward is Reward.WIN:
        return int(player_round.round_number in outcome.won_rounds)
    return int(player_round in outcome.first_item_finishes)
