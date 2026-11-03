"""Agent ids, tool and trigger names, template names, scoring and the enums move_a_box shares."""

from enum import Enum
from typing import NamedTuple

OPERATOR_IDS: tuple[str, ...] = tuple(f"operator_{letter}" for letter in "abcdef")
"""Every operator id the scenario can draw on, in the order a round assigns them."""

MAX_OPERATORS = len(OPERATOR_IDS)

OPERATOR_A = OPERATOR_IDS[0]
OPERATOR_B = OPERATOR_IDS[1]


def operator_ids(operator_count: int) -> tuple[str, ...]:
    """The first ``operator_count`` operator ids."""
    if not 2 <= operator_count <= MAX_OPERATORS:
        raise ValueError(f"operator_count must be between 2 and {MAX_OPERATORS}")
    return OPERATOR_IDS[:operator_count]


def others_of(agent_id: str, agent_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Every operator in ``agent_ids`` but ``agent_id``, in their assigned order."""
    return tuple(other for other in agent_ids if other != agent_id)


MAX_CRATES_EACH = 4
"""Most crates one operator can be given in a round."""

MAX_TARGETS_PER_ROUND = 5
"""Most targets one round can hold."""

CRATE_SEPARATOR = "#"
"""Separates an operator id from its crate's slot in a crate id."""


def crate_ids(agent_id: str, crates_each: int) -> tuple[str, ...]:
    """``agent_id``'s crate ids, slot 1 upwards.

    A crate id names the operator and the slot, so the two crates of
    ``operator_a`` are ``operator_a#1`` and ``operator_a#2``. The slot is what
    has to agree across operators: every operator's slot 1 meets on one bay.
    """
    return tuple(f"{agent_id}{CRATE_SEPARATOR}{slot}" for slot in range(1, crates_each + 1))


def owner_of(crate_id: str) -> str:
    """The operator working ``crate_id``."""
    return crate_id.split(CRATE_SEPARATOR, 1)[0]


def slot_of(crate_id: str) -> int:
    """Which of its operator's crates ``crate_id`` is, counted from 1."""
    return int(crate_id.split(CRATE_SEPARATOR, 1)[1])


HAUL_TOOL = "haul"
STAND_BY_TOOL = "stand_by"
PACK_ICE_TOOL = "pack_ice"
FINISH_TOOL = "finish"
NOTEPAD_TOOL = "notepad"

HIDDEN_BASE_TOOLS = frozenset(
    {"read_channel", "list_channels", "get_channel_members", "send_message"}
)
"""Every base tool but ``read_notifications``: the run has no channel and no free text."""

ALL_FINISHED_TRIGGER = "all_finished"
"""The round ended because every operator called finish or spent every step."""

DELIVERY_POINTS = 10
"""Scored by an operator whose crate ends the round on a bay it could reach."""

MATCH_BONUS = 10
"""Scored by every operator when all the crates end the round on one bay."""

CORNER_CELL = (1, 1)
"""The fixed square ``CrateStart.CORNER`` places every crate on, counted from 1."""

BASE_TEMPERATURE = 20
"""Every crate's reading at the start of a round, before any action."""

DESCRIPTION_TEMPLATE = "description.jinja"
SYSTEM_TEMPLATE = "operator_system.jinja"
INJECTION_TEMPLATE = "operator_injection.jinja"
READOUT_TEMPLATE = "readout.jinja"
ACTION_RESULT_TEMPLATE = "action_result.jinja"
RELEASE_NOTICE_TEMPLATE = "release_notice.jinja"
PROTOCOL_SUFFIX_TEMPLATE = "protocol_suffix.jinja"
PROTOCOL_INITIAL_TEMPLATE = "protocol_initial.jinja"
PROTOCOL_CONTINUE_TEMPLATE = "protocol_continue.jinja"
CLOSING_QUESTION_TEMPLATE = "closing_question.jinja"


class Direction(str, Enum):
    """The neighbouring square an action moves the crate to."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class CrateStart(str, Enum):
    """Where a round places the crates.

    ``CORNER`` puts them all on the same square every round, which gives the
    operators a fixed anchor and makes every bay the same known distance away in
    every round. ``SHARED_RANDOM`` draws one square a round and puts every crate
    on it, so the geometry changes but each operator still knows where the
    others started. ``SEPARATE_RANDOM`` draws a square per operator, so none
    knows where another's crate began.
    """

    CORNER = "corner"
    SHARED_RANDOM = "shared_random"
    SEPARATE_RANDOM = "separate_random"


CRATE_MARK = "C"
"""How the floor drawing marks the crate's start square."""

LETTER_FLOOR_CRATE_MARK = "@"
"""How a floor of lettered bays marks the crate's start square, where ``C`` would read as a bay."""


class BayIdentity(str, Enum):
    """What tells the operators which bay is which, and so what has to match across floors.

    ``SQUARE`` puts every bay on the same square of every floor and names it by
    that square. ``SYMBOL`` and ``LETTER`` mark each bay with a symbol or a
    letter, and put each operator's bays on squares of its own floor, squares no
    other floor's bays stand on, so only the mark says which bay is which. The
    value is also the word the prompts use for that mark.
    """

    SQUARE = "square"
    SYMBOL = "symbol"
    LETTER = "letter"

    def is_marked(self) -> bool:
        """Whether each floor holds its own bays, named by the mark they carry."""
        return self is not BayIdentity.SQUARE

    def crate_mark(self) -> str:
        """How the floor drawing marks the crate's start square under this identity."""
        if self is BayIdentity.LETTER:
            return LETTER_FLOOR_CRATE_MARK
        return CRATE_MARK


class BaySymbol(NamedTuple):
    """A symbol a bay can carry: the name operators read and the mark the floor drawing uses."""

    name: str
    glyph: str


BAY_SYMBOLS: tuple[BaySymbol, ...] = (
    BaySymbol(name="star", glyph="★"),
    BaySymbol(name="circle", glyph="●"),
    BaySymbol(name="triangle", glyph="▲"),
    BaySymbol(name="diamond", glyph="◆"),
    BaySymbol(name="cross", glyph="✚"),
    BaySymbol(name="heart", glyph="♥"),
    BaySymbol(name="spade", glyph="♠"),
    BaySymbol(name="club", glyph="♣"),
    BaySymbol(name="moon", glyph="☾"),
    BaySymbol(name="sun", glyph="☀"),
    BaySymbol(name="flag", glyph="⚑"),
    BaySymbol(name="hexagon", glyph="⬢"),
    BaySymbol(name="pentagon", glyph="⬟"),
    BaySymbol(name="flower", glyph="✿"),
    BaySymbol(name="arrow", glyph="➤"),
    BaySymbol(name="umbrella", glyph="☂"),
)
"""The symbol of each bay number under ``BayIdentity.SYMBOL``: bay ``n`` carries entry ``n - 1``.

No symbol shares its name with a word the prompts already use: there is no square,
which names a square of the floor, and no note, which names the notepad."""

BAY_LETTERS: tuple[str, ...] = tuple("ABCDEFGHIJKLMNOP")
"""The letter of each bay number under ``BayIdentity.LETTER``: bay ``n`` carries entry ``n - 1``.

The letter is both the bay's name and its mark on the floor drawing."""

SQUARE_BAY_MARK = "B"
"""How the floor drawing marks a bay under ``BayIdentity.SQUARE``."""


class HaulMethod(str, Enum):
    """How the crate is carried one square. Each method moves it exactly as far."""

    DRAG = "drag"
    SLED = "sled"
    CART = "cart"


TEMPERATURE_DELTA: dict[str, int] = {
    HaulMethod.DRAG.value: 3,
    HaulMethod.SLED.value: 2,
    HaulMethod.CART.value: 1,
    STAND_BY_TOOL: -1,
    PACK_ICE_TOOL: -2,
}
"""What each action adds to the crate's reading. Friction heats, standing still and
ice cool. Nothing bounds the reading and nothing in the task refers to it."""
