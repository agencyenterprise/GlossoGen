"""The scores of one finished signal_game game, as the GlossoGen-side scorer prints them and the
harness reads them.

The module imports only pydantic, so both environments import it: GlossoGen's, where
``glossogen_side/score_game.py`` writes the scores, and this project's, where the harness and the
episode program read them.
"""

from pydantic import BaseModel, ConfigDict


class SeatScores(BaseModel):
    """One seat's scores in one game.

    ``answer_rounds`` holds the round of each of the seat's model responses, in the order of the
    event log. ``scores[reward][round]`` is the seat's score in that round under that reward, 0 or
    1.
    """

    model_config = ConfigDict(extra="forbid")

    answer_rounds: list[int]
    scores: dict[str, dict[int, int]]


class GameScores(BaseModel):
    """A game's scores: whether it ended with ``simulation_ended``, its resolved rounds, and each
    seat's scores."""

    model_config = ConfigDict(extra="forbid")

    finished: bool
    rounds: list[int]
    seats: dict[str, SeatScores]


class PlayedGame(BaseModel):
    """What the harness records on the root agent of an episode: the game's run id and seed, the
    platoon agent of each seat that platoon served, and the game's scores."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    seed: int
    seat_agents: dict[str, str]
    scores: GameScores
