"""Agent ids, tool and trigger names, template names and the enums signal_game shares."""

from enum import Enum

PLAYER_A = "player_a"
PLAYER_B = "player_b"
AGENT_IDS: tuple[str, ...] = (PLAYER_A, PLAYER_B)
PARTNER_OF: dict[str, str] = {PLAYER_A: PLAYER_B, PLAYER_B: PLAYER_A}

MOVE_TOOL = "move"
END_ROUND_TOOL = "end_round"

RUN_COMMAND_TOOL = "run_command"
"""The shell on the shared server, offered under the ``file_system`` medium."""

HIDDEN_BASE_TOOLS = frozenset(
    {"read_channel", "list_channels", "get_channel_members", "send_message"}
)
"""Every base tool but ``read_notifications``: the run has no channel and no free text."""

MAX_MOVES_PER_CALL = 10
"""The most directions one ``move`` call takes, so a call cannot spend a whole round's
budget in one burst."""

BOTH_FINISHED_TRIGGER = "both_finished"
"""The round ended because each player called end_round or spent its moves."""

PALETTE: tuple[str, ...] = ("red", "blue", "green", "yellow", "purple", "orange")
"""Colours in the order ``colour_count`` takes them; the paper used the first four."""

DESCRIPTION_TEMPLATE = "description.jinja"
SYSTEM_TEMPLATE = "player_system.jinja"
INJECTION_TEMPLATE = "player_injection.jinja"
BOARD_TEMPLATE = "board_view.jinja"
MOVE_RESULT_TEMPLATE = "move_result.jinja"
RELEASE_NOTICE_TEMPLATE = "release_notice.jinja"
PROTOCOL_SUFFIX_TEMPLATE = "protocol_suffix.jinja"
PROTOCOL_INITIAL_TEMPLATE = "protocol_initial.jinja"
PROTOCOL_CONTINUE_TEMPLATE = "protocol_continue.jinja"
JUDGE_SYSTEM_TEMPLATE = "plaintext_judge_system.jinja"
JUDGE_TEXTS_TEMPLATE = "plaintext_judge_texts.jinja"


class Medium(str, Enum):
    """What one player can perceive of the other during a round.

    ``grid``: each player moves a figure and sees the partner's square and every
    move. ``file_system``: no figures; each player names its square in ``end_round``,
    and the two are users of one simulated server.
    """

    GRID = "grid"
    FILE_SYSTEM = "file_system"


class WrittenTextKind(str, Enum):
    """What a text the plaintext judge reads is.

    ``content``: what a file holds. ``name``: what one node is called. ``names``:
    the paths of every node one player has on the server, in the order it made them,
    so a word spelled one letter per name or per directory level is read whole.
    """

    CONTENT = "content"
    NAME = "name"
    NAMES = "names"


class JudgeTool(str, Enum):
    """A tool the plaintext judge investigates with: a shell on a copy of the server, or a
    Python program run in the sandbox over a dump of it."""

    SHELL = "run_command"
    PYTHON = "run_python"


class Direction(str, Enum):
    """A move to the neighbouring square in one direction. There is no move that stays put."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
