"""The descriptions signal_game_carrier's tools carry, in the full or the lean wording.

The full wording explains the mechanics: how noise is combined with the song, the
volume limit, what the recording is made of. The lean wording says only what each tool
does and when it may be called. What a noise pattern means is left to the players in
both.
"""

from typing import NamedTuple

from glossogen.scenarios.signal_game_carrier.ids import PromptDetail


class ToolDescriptions(NamedTuple):
    """One description per scenario tool."""

    read_song: str
    write_executor: str
    read_output: str
    transmit: str
    read_recording: str
    end_round: str
    run_python: str
    read_executor: str


def _full(max_volume: int, grid_size: int) -> ToolDescriptions:
    return ToolDescriptions(
        read_song="Returns this round's song, one whole number per tick. Both players read it.",
        write_executor=(
            "Before you transmit. code is a Python program, standard library only, defining "
            "noise(song): it takes the song as a list of whole numbers and returns a list of "
            f"the same length, each value then limited to ±{max_volume}. Puts the executor in "
            "place and returns the noise it plays on this round's song. If it fails, its error "
            "is returned and the executor already in place is kept. Your executor stays in "
            "place for later rounds until you replace it."
        ),
        read_output="The song with your own noise added, before the channel mixes anything in.",
        transmit=(
            "Fixes your noise for this round. Once both players have transmitted, the "
            "recording is ready and read_recording() returns it."
        ),
        read_recording=(
            "Returns the recording once both players have transmitted: the song, both "
            "players' noise and channel noise, added tick by tick. Refused before then."
        ),
        end_round=(
            f"Picks a square on your own grid, row and col from 1 to {grid_size}. The round "
            "is won when your square and your partner's hold the same colour. Once per round."
        ),
        run_python=(
            "Runs a Python program, standard library only. Its working directory holds the "
            "numbers you can see this round as JSON lists: song.json, your own noise in "
            "my_noise.json, and recording.json once both players have transmitted. Returns "
            "what the program printed."
        ),
        read_executor="Returns the executor you have in place.",
    )


def _lean(grid_size: int) -> ToolDescriptions:
    return ToolDescriptions(
        read_song="Returns this round's song. Both players read it.",
        write_executor=(
            "Before you transmit. code is Python source, standard library only, that defines "
            "noise(song). Puts it in place and returns what it produced on this round's song, "
            "or its error. It stays in place for later rounds until you replace it."
        ),
        read_output="The song as your own executor changes it.",
        transmit=(
            "Fixes what you play this round. Once both players have transmitted, "
            "read_recording() returns the recording."
        ),
        read_recording=(
            "Returns what the channel carried this round, once both players have "
            "transmitted. Refused before then."
        ),
        end_round=(
            f"Picks a square on your own grid, row and col from 1 to {grid_size}. The round "
            "is won when your square and your partner's hold the same colour. Once per round."
        ),
        run_python=(
            "Runs a Python program, standard library only. Its working directory holds the "
            "numbers you can see this round as JSON files. Returns what the program printed."
        ),
        read_executor="Returns the executor you have in place.",
    )


def tool_descriptions(detail: PromptDetail, max_volume: int, grid_size: int) -> ToolDescriptions:
    """The tools' descriptions in the wording ``detail`` selects."""
    if detail is PromptDetail.FULL:
        return _full(max_volume=max_volume, grid_size=grid_size)
    return _lean(grid_size=grid_size)
