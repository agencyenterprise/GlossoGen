"""Agent ids, tool and trigger names, template names and the roles carrier_song shares."""

from enum import Enum

PLAYER_A = "player_a"
PLAYER_B = "player_b"
AGENT_IDS: tuple[str, ...] = (PLAYER_A, PLAYER_B)
PARTNER_OF: dict[str, str] = {PLAYER_A: PLAYER_B, PLAYER_B: PLAYER_A}

READ_SONG_TOOL = "read_song"
WRITE_EXECUTOR_TOOL = "write_executor"
READ_OUTPUT_TOOL = "read_output"
END_ROUND_TOOL = "end_round"
READ_RECEIVED_TOOL = "read_received"
SUBMIT_DECODING_TOOL = "submit_decoding"
RUN_PYTHON_TOOL = "run_python"
TOOL_NAMES: tuple[str, ...] = (
    READ_SONG_TOOL,
    WRITE_EXECUTOR_TOOL,
    READ_OUTPUT_TOOL,
    END_ROUND_TOOL,
    READ_RECEIVED_TOOL,
    SUBMIT_DECODING_TOOL,
    RUN_PYTHON_TOOL,
)
HIDDEN_BASE_TOOLS = frozenset(
    {"read_channel", "list_channels", "get_channel_members", "send_message"}
)
"""Every base tool but ``read_notifications``: the run has no channel and no free text."""

DECODED_TRIGGER = "decoded"
"""The round ended because the receiver submitted its decoding."""

TRANSMITTED = "transmitted"
"""The release detail that wakes a waiting receiver once the sender has ended its turn."""

SENDER_IDLE = "sender_idle"
"""The release detail that wakes a sender waiting before it ended its turn: nothing will
arrive, since the receiver is waiting for it."""

DESCRIPTION_TEMPLATE = "description.jinja"
SYSTEM_TEMPLATE = "player_system.jinja"
INJECTION_TEMPLATE = "player_injection.jinja"
SEQUENCE_VIEW_TEMPLATE = "sequence_view.jinja"
EXECUTOR_RESULT_TEMPLATE = "executor_result.jinja"
TURN_NOTE_TEMPLATE = "turn_note.jinja"
EXECUTOR_WARNING_TEMPLATE = "executor_warning.jinja"
PYTHON_RESULT_TEMPLATE = "python_result.jinja"
RELEASE_NOTICE_TEMPLATE = "release_notice.jinja"
PROTOCOL_SUFFIX_TEMPLATE = "protocol_suffix.jinja"
PROTOCOL_INITIAL_TEMPLATE = "protocol_initial.jinja"
PROTOCOL_CONTINUE_TEMPLATE = "protocol_continue.jinja"


class Role(str, Enum):
    """What a player does in a round. The roles swap every round."""

    SENDER = "sender"
    RECEIVER = "receiver"


class SequenceKind(str, Enum):
    """Which list of numbers a tool result shows."""

    SONG = "song"
    OUTPUT = "output"
    RECORDING = "recording"


class TurnNote(str, Enum):
    """What a finished turn's tool result says."""

    TRANSMITTED = "transmitted"
    DECODED = "decoded"
