"""The scores of one finished signal_game game, as the GlossoGen-side scorer prints them and the
harness reads them.

The module imports only pydantic, so both environments import it: GlossoGen's, where
``glossogen_side/score_game.py`` writes the scores, and this project's, where the harness and the
episode program read them.
"""

from pydantic import BaseModel, ConfigDict

ANSWER_KEY_TEXT_CHARACTERS = 40


def answer_key(*, tool_names: list[str], text: str | None) -> str:
    """What the episode program compares to match a logged response with a recorded call: the
    names of the answer's tool calls, in order, and the first characters of its text with its
    whitespace collapsed."""
    words = ""
    if text is not None:
        words = " ".join(text.split())[:ANSWER_KEY_TEXT_CHARACTERS]
    return ",".join(tool_names) + "|" + words


class SeatScores(BaseModel):
    """One seat's scores in one game.

    ``answer_rounds`` holds the round of each of the seat's model responses, in the order of the
    event log, and ``answer_keys`` the ``answer_key`` of each. ``scores[reward][round]`` is the
    seat's score in that round under that reward, 0 or 1.
    """

    model_config = ConfigDict(extra="forbid")

    answer_rounds: list[int]
    answer_keys: list[str]
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
