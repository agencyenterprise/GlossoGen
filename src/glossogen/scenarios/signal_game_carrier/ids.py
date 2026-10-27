"""Agent ids, tool and trigger names, template names and the enums signal_game_carrier shares."""

from enum import Enum

PLAYER_A = "player_a"
PLAYER_B = "player_b"
AGENT_IDS: tuple[str, ...] = (PLAYER_A, PLAYER_B)
PARTNER_OF: dict[str, str] = {PLAYER_A: PLAYER_B, PLAYER_B: PLAYER_A}

READ_SONG_TOOL = "read_song"
WRITE_EXECUTOR_TOOL = "write_executor"
READ_OUTPUT_TOOL = "read_output"
TRANSMIT_TOOL = "transmit"
READ_RECORDING_TOOL = "read_recording"
END_ROUND_TOOL = "end_round"
RUN_PYTHON_TOOL = "run_python"
READ_EXECUTOR_TOOL = "read_executor"
TOOL_NAMES: tuple[str, ...] = (
    READ_SONG_TOOL,
    WRITE_EXECUTOR_TOOL,
    READ_OUTPUT_TOOL,
    TRANSMIT_TOOL,
    READ_RECORDING_TOOL,
    END_ROUND_TOOL,
    RUN_PYTHON_TOOL,
    READ_EXECUTOR_TOOL,
)

HIDDEN_BASE_TOOLS = frozenset(
    {"read_channel", "list_channels", "get_channel_members", "send_message"}
)
"""Every base tool but ``read_notifications``: the run has no channel and no free text."""

BOTH_CHOSE_TRIGGER = "both_chose"
"""The round ended because both players picked a square."""

RECORDING_READY = "recording_ready"
"""The release detail that wakes a player once both have transmitted."""

AWAITING_YOU = "awaiting_you"
"""The release detail that wakes a player who has not transmitted: nothing will arrive
until it does."""

PALETTE: tuple[str, ...] = ("red", "blue", "green", "yellow", "purple", "orange")
"""Colours in the order ``colour_count`` takes them."""

DESCRIPTION_TEMPLATE = "description.jinja"
INJECTION_TEMPLATE = "player_injection.jinja"
BOARD_TEMPLATE = "board_view.jinja"
SEQUENCE_VIEW_TEMPLATE = "sequence_view.jinja"
EXECUTOR_RESULT_TEMPLATE = "executor_result.jinja"
EXECUTOR_SOURCE_TEMPLATE = "executor_source.jinja"
TURN_NOTE_TEMPLATE = "turn_note.jinja"
PYTHON_RESULT_TEMPLATE = "python_result.jinja"
RELEASE_NOTICE_TEMPLATE = "release_notice.jinja"
PROTOCOL_INITIAL_TEMPLATE = "protocol_initial.jinja"
PROTOCOL_CONTINUE_TEMPLATE = "protocol_continue.jinja"


class PromptDetail(str, Enum):
    """How much of the game's mechanics the players are told.

    ``FULL`` spells out how the noise is combined with the song, the volume limit and
    the channel noise. ``LEAN`` says what the game is and what the tools do, and leaves
    the mechanics for the players to find out.
    """

    FULL = "full"
    LEAN = "lean"


SYSTEM_TEMPLATES: dict[PromptDetail, str] = {
    PromptDetail.FULL: "player_system_full.jinja",
    PromptDetail.LEAN: "player_system_lean.jinja",
}
PROTOCOL_SUFFIX_TEMPLATES: dict[PromptDetail, str] = {
    PromptDetail.FULL: "protocol_suffix_full.jinja",
    PromptDetail.LEAN: "protocol_suffix_lean.jinja",
}


class SequenceKind(str, Enum):
    """Which list of numbers a tool result shows."""

    SONG = "song"
    OUTPUT = "output"
    RECORDING = "recording"


class TurnNote(str, Enum):
    """What a finished step's tool result says."""

    TRANSMITTED = "transmitted"
    CHOSE = "chose"
