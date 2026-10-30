"""Agent ids, tool and trigger names, template names, scoring and the enums move_a_box shares."""

from enum import Enum

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


ACT_TOOL = "act"
NOTEPAD_TOOL = "notepad"

STAND_BY_ACTION = "stand_by"
PACK_ICE_ACTION = "pack_ice"
FINISH_ACTION = "finish"

MAX_ACTIONS_PER_CALL = 20
"""The most actions ``actions_per_call`` can let one ``act`` call take."""

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


class HaulMethod(str, Enum):
    """How the crate is carried one square. Each method moves it exactly as far."""

    DRAG = "drag"
    SLED = "sled"
    CART = "cart"


class CrateAction(str, Enum):
    """What one step of an ``act`` call does to a crate.

    The three carrying methods take a direction and move the crate one square.
    The other three act in place: standing by and packing ice each spend a step,
    and finishing leaves the crate where it stands for the rest of the round.
    """

    DRAG = HaulMethod.DRAG.value
    SLED = HaulMethod.SLED.value
    CART = HaulMethod.CART.value
    STAND_BY = STAND_BY_ACTION
    PACK_ICE = PACK_ICE_ACTION
    FINISH = FINISH_ACTION


_HAUL_METHODS: dict[str, HaulMethod] = {method.value: method for method in HaulMethod}


def haul_method_of(action: CrateAction) -> HaulMethod | None:
    """The carrying method ``action`` names, or None when it does not move the crate."""
    return _HAUL_METHODS.get(action.value)


TEMPERATURE_DELTA: dict[str, int] = {
    HaulMethod.DRAG.value: 3,
    HaulMethod.SLED.value: 2,
    HaulMethod.CART.value: 1,
    STAND_BY_ACTION: -1,
    PACK_ICE_ACTION: -2,
}
"""What each action adds to the crate's reading. Friction heats, standing still and
ice cool. Nothing bounds the reading and nothing in the task refers to it."""
