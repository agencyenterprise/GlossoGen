"""Agent ids, tool and trigger names, template names, scoring and the enums move_a_box shares."""

from enum import Enum

OPERATOR_A = "operator_a"
OPERATOR_B = "operator_b"
AGENT_IDS: tuple[str, ...] = (OPERATOR_A, OPERATOR_B)
PARTNER_OF: dict[str, str] = {OPERATOR_A: OPERATOR_B, OPERATOR_B: OPERATOR_A}

HAUL_TOOL = "haul"
STAND_BY_TOOL = "stand_by"
PACK_ICE_TOOL = "pack_ice"
FINISH_TOOL = "finish"
NOTEPAD_TOOL = "notepad"

HIDDEN_BASE_TOOLS = frozenset(
    {"read_channel", "list_channels", "get_channel_members", "send_message"}
)
"""Every base tool but ``read_notifications``: the run has no channel and no free text."""

BOTH_FINISHED_TRIGGER = "both_finished"
"""The round ended because each operator called finish or spent every step."""

DELIVERY_POINTS = 10
"""Scored by an operator whose crate ends the round on a bay it could reach."""

MATCH_BONUS = 10
"""Scored by both operators when the two crates end the round on the same bay."""

CORNER_CELL = (1, 1)
"""The fixed square ``CrateStart.CORNER`` places both crates on, counted from 1."""

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
    """Where a round places the two crates.

    ``CORNER`` puts both on the same square every round, which gives the
    operators a fixed anchor and makes every bay the same known distance away in
    every round. ``SHARED_RANDOM`` draws one square a round and puts both crates
    on it, so the geometry changes but both operators still know where the other
    started. ``SEPARATE_RANDOM`` draws a square per operator, so neither knows
    where the other's crate began.
    """

    CORNER = "corner"
    SHARED_RANDOM = "shared_random"
    SEPARATE_RANDOM = "separate_random"


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
