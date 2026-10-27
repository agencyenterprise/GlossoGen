"""The descriptions carrier_song's tools carry, in the full or the lean wording.

The full wording explains the mechanics: how noise is combined with the song, the
volume limit, the channel noise. The lean wording says only what each tool does
and who may call it, and leaves the rest for the players to find out.
"""

from typing import NamedTuple

from glossogen.scenarios.carrier_song.ids import PromptDetail


class ToolDescriptions(NamedTuple):
    """One description per scenario tool."""

    read_song: str
    write_executor: str
    read_output: str
    end_round: str
    read_received: str
    submit_decoding: str
    run_python: str
    read_executor: str


def _full(max_volume: int, receiver_sees_song: bool) -> ToolDescriptions:
    read_received = (
        "Receiver only, once the sender has ended its turn. Returns the recording: the song "
        "plus the sender's noise plus channel noise."
    )
    if receiver_sees_song:
        read_received += " Also returns the song under it."
    return ToolDescriptions(
        read_song="Sender only. Returns this round's song, one whole number per tick.",
        write_executor=(
            "Sender only, before end_round. code is a Python program, standard library only, "
            "defining noise(song): it takes the song as a list of whole numbers and returns a "
            f"list of the same length, each value then limited to ±{max_volume}. Puts the "
            "executor in place and returns the noise it plays on this round's song. If it "
            "fails, its error is returned and the executor already in place is kept. Your "
            "partner never sees your code or what it prints."
        ),
        read_output=(
            "Sender only, before end_round. Returns the song with your executor's noise added, "
            "before channel noise."
        ),
        end_round=(
            "Sender only. Fixes your noise for this round and hands the recording to the "
            "receiver. Nothing you do afterwards changes it."
        ),
        read_received=read_received,
        submit_decoding=(
            "Receiver only, once the sender has ended its turn, once per round. secret is your "
            "reading of the sender's secret code: capital letters A-Z and digits 0-9, as many "
            "as the code has. Lowercase is read as uppercase. A decoding that is not a code of "
            "the right length is refused and does not count as your decoding. An accepted one "
            "ends the round."
        ),
        run_python=(
            "Runs a Python program, standard library only, in a fresh interpreter. Its working "
            "directory holds the numbers you can see this round as JSON lists: song.json, "
            "received.json. Returns what the program printed. It changes nothing in the game."
        ),
        read_executor=(
            "Returns the executor you have in place, which plays over the song whenever you "
            "are the sender, or says you have none."
        ),
    )


def _lean(receiver_sees_song: bool) -> ToolDescriptions:
    read_received = (
        "Receiver only, once the sender has ended its turn. Returns what you hear this round."
    )
    if receiver_sees_song:
        read_received += " Also returns the song."
    return ToolDescriptions(
        read_song="Sender only. Returns this round's song.",
        write_executor=(
            "Sender only, before end_round. code is Python source, standard library only, that "
            "defines noise(song). Puts it in place and returns what it produced on this round's "
            "song, or its error."
        ),
        read_output="Sender only, before end_round. Returns the song as your executor changes it.",
        end_round="Sender only. Ends your turn, and the receiver hears the result.",
        read_received=read_received,
        submit_decoding=(
            "Receiver only, once the sender has ended its turn, once per round. secret is your "
            "reading of the sender's code. A reading that is not a well-formed code is refused "
            "and does not count. An accepted one ends the round."
        ),
        run_python=(
            "Runs a Python program, standard library only, in a fresh interpreter. Its working "
            "directory holds the numbers you can see this round as JSON files. Returns what it "
            "printed. It changes nothing in the game."
        ),
        read_executor="Returns the executor you have in place, or says you have none.",
    )


def tool_descriptions(
    detail: PromptDetail, max_volume: int, receiver_sees_song: bool
) -> ToolDescriptions:
    """The tools' descriptions in the wording ``detail`` selects."""
    if detail is PromptDetail.FULL:
        return _full(max_volume=max_volume, receiver_sees_song=receiver_sees_song)
    return _lean(receiver_sees_song=receiver_sees_song)
