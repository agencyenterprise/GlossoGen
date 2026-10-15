"""Agent ids, tool and trigger names, template names and the enums signal_game shares."""

from enum import Enum

PLAYER_A = "player_a"
PLAYER_B = "player_b"
AGENT_IDS: tuple[str, ...] = (PLAYER_A, PLAYER_B)
PARTNER_OF: dict[str, str] = {PLAYER_A: PLAYER_B, PLAYER_B: PLAYER_A}

MOVE_TOOL = "move"
OBSERVE_TOOL = "observe"
HIDDEN_BASE_TOOLS = frozenset(
    {"read_channel", "list_channels", "get_channel_members", "send_message"}
)
"""Every base tool but ``read_notifications``: the run has no channel and no free text."""

MAX_MOVES_PER_CALL = 10
"""The most directions one ``move`` call takes, so a call cannot spend a whole round's
budget in one burst."""

BOTH_FINISHED_TRIGGER = "both_finished"
"""The round ended because each player finished or spent its moves."""

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
UNSEEN_REFUSAL_TEMPLATE = "unseen_refusal.jinja"


class Direction(str, Enum):
    """A move of one square."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class TurnKind(str, Enum):
    """What one entry of a round's log records.

    ``move`` is one ``move`` call, ``wait`` a turn passed under ``turn_based`` by
    waiting on it, and ``finish`` a player fixing its square by waiting for the
    next round.
    """

    MOVE = "move"
    WAIT = "wait"
    FINISH = "finish"


class TurnState(str, Enum):
    """Who may act next under ``turn_based``, from one player's side.

    ``open`` is a round no one has moved in yet; ``free`` is a player whose
    partner has finished, so it no longer waits for turns.
    """

    YOURS = "yours"
    PARTNERS = "partners"
    OPEN = "open"
    FREE = "free"
