"""A scripted signal_game player for CPU tests: it reads the last message of its prompt and answers
with a tool call.

At the start it reads its notifications. On a round's briefing it makes one random move, then ends
the round, then waits for the next round, and it writes plain text once the game is done. Tool calls
are in the Qwen3 format that the toy tokenizer's ``qwen3_instruct`` renderer parses
(``platoon.testing.tool_call``).
"""

import random
import re

from platoon.testing import last_user_message, tool_call

DIRECTIONS = ("up", "down", "left", "right")
BRIEFING = re.compile(r'"briefings":\["ROUND \d+')
GAME_OVER = "The game is over."


def signal_game_player(prompt: str) -> str:
    """The next completion of a player whose decoded prompt is ``prompt``."""
    last = last_user_message(prompt)
    if '"type":"done"' in last:
        return GAME_OVER
    if "<tool_response>" not in last:
        return tool_call("read_notifications", wait_for="any")
    if BRIEFING.search(last):
        return tool_call(
            "move", directions=[random.choice(DIRECTIONS)], reasoning="Trying a square."
        )
    if "You finished round" in last:
        return tool_call("read_notifications", wait_for="next_round")
    return tool_call("end_round", reasoning="Ending here.")
