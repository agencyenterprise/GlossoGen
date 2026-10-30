"""move_a_box's events: each round's floor, every action, each finish and the verdict.

Cells are ``[row, col]`` pairs counted from 1, as operators read them. The
readings an operator took are logged with its actions, so a run's channel can be
read back from the log without replaying the world.
"""

from typing import Literal

from glossogen.models.event_base import EventBase


class MoveABoxRoundStarted(EventBase):
    """A round's bays and each operator's start square, pallets and assigned bays.

    No operator sees the other's start square, pallets or assigned bays.
    ``crate_ids`` and ``crate_masses`` are the markings the readout shows, fixed
    for the run.
    """

    event_type: Literal["move_a_box_round_started"] = "move_a_box_round_started"
    round_number: int
    grid_size: int
    start_cells: dict[str, tuple[int, int]]
    bays: list[tuple[int, int]]
    pallets: dict[str, list[tuple[int, int]]]
    allowed_bays: dict[str, list[int]]
    steps_per_round: int
    bays_differ: bool
    crate_start: str
    partner_readout: bool
    partner_disclosed: bool
    partner_bay_disclosed: bool
    crate_ids: dict[str, str]
    crate_masses: dict[str, int]


class MoveABoxActionTaken(EventBase):
    """One accepted action. ``sequence`` orders both operators' actions within the round.

    ``action`` is the haul method, ``stand_by`` or ``pack_ice``. ``temperature``
    is the crate's reading after it, which is what the other operator can see.
    ``reasoning`` is the sentence the operator gave, never shown to the other
    operator, and None when the run's ``action_reasoning`` is off.
    """

    event_type: Literal["move_a_box_action_taken"] = "move_a_box_action_taken"
    round_number: int
    agent_id: str
    sequence: int
    action: str
    direction: str | None
    from_cell: tuple[int, int]
    to_cell: tuple[int, int]
    temperature: int
    steps_used: int
    reasoning: str | None


class MoveABoxNoteWritten(EventBase):
    """An operator wrote its private note. The other operator never sees it."""

    event_type: Literal["move_a_box_note_written"] = "move_a_box_note_written"
    round_number: int
    agent_id: str
    text: str


class MoveABoxOperatorFinished(EventBase):
    """An operator called finish; its crate's square is final for the round.

    ``bay`` is the bay number the crate stands on, or None when it stands
    elsewhere.
    """

    event_type: Literal["move_a_box_operator_finished"] = "move_a_box_operator_finished"
    round_number: int
    agent_id: str
    cell: tuple[int, int]
    bay: int | None
    temperature: int
    steps_used: int
    reasoning: str | None


class MoveABoxRoundResolved(EventBase):
    """Where each crate ended, on which bay, and whether the two bays matched.

    ``points`` is each operator's score for the round: the delivery points, plus
    the match bonus when both crates stand on one bay.
    """

    event_type: Literal["move_a_box_round_resolved"] = "move_a_box_round_resolved"
    round_number: int
    final_cells: dict[str, tuple[int, int]]
    final_bays: dict[str, int | None]
    temperatures: dict[str, int]
    steps_used: dict[str, int]
    points: dict[str, int]
    matched: bool
    success: bool
    trigger: str
