"""move_a_box's events: each round's floor, every action, each finish and the verdict.

Cells are ``[row, col]`` pairs counted from 1, as operators read them. The
readings an operator took are logged with its actions, so a run's channel can be
read back from the log without replaying the world.
"""

from typing import Any, Literal, cast

from pydantic import BaseModel, model_validator

from glossogen.models.event_base import EventBase
from glossogen.scenarios.move_a_box.depot import Cell
from glossogen.scenarios.move_a_box.ids import SQUARE_BAY_MARK, BayIdentity


class MoveABoxBay(BaseModel):
    """A bay on one operator's floor, as that operator was shown it.

    ``number`` is what scoring compares across floors. ``name`` is what the
    operator calls the bay, its square, its symbol or its letter, and ``mark`` is
    how the floor drawing shows it.
    """

    number: int
    name: str
    mark: str
    cell: tuple[int, int]


class MoveABoxRoundStarted(EventBase):
    """Each operator's bays, start square, pallets and assigned bays for one round.

    No operator sees another's floor, start square, pallets or assigned bays.
    ``floor_bays`` holds every bay on each operator's floor, and
    ``bay_identity`` says whether a bay is named by its square, its symbol or
    its letter.
    ``crate_ids`` and ``crate_masses`` are keyed by crate id and hold the
    markings the readout shows, fixed for the run. ``crates_each`` says how many
    crates each operator works, which is how a crate id's slot is read back.
    ``virtual_time_s`` is the virtual second of the run the round started at
    under ``virtual_clock``, and None otherwise.
    """

    event_type: Literal["move_a_box_round_started"] = "move_a_box_round_started"
    round_number: int
    grid_size: int
    start_cells: dict[str, tuple[int, int]]
    bay_identity: str
    floor_bays: dict[str, list[MoveABoxBay]]
    pallets: dict[str, list[tuple[int, int]]]
    allowed_bays: dict[str, list[int]]
    steps_per_round: int
    crates_each: int
    bays_differ: bool
    crate_start: str
    partner_readout: bool
    partner_disclosed: bool
    partner_bay_disclosed: bool
    crate_ids: dict[str, str]
    crate_masses: dict[str, int]
    virtual_time_s: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _backfill_floor_bays(cls, data: Any) -> Any:
        """Runs from before ``bay_identity`` logged one ``bays`` list that every floor shared."""
        if not isinstance(data, dict):
            return data
        typed = cast(dict[str, Any], data)
        if "floor_bays" in typed or "bays" not in typed:
            return typed
        shared = [
            {
                "number": number,
                "name": Cell(row=pair[0], col=pair[1]).label(),
                "mark": SQUARE_BAY_MARK,
                "cell": pair,
            }
            for number, pair in enumerate(cast(list[list[int]], typed["bays"]), start=1)
        ]
        operators = cast(dict[str, Any], typed.get("start_cells", {}))
        return {
            **typed,
            "bay_identity": BayIdentity.SQUARE.value,
            "floor_bays": dict.fromkeys(operators, shared),
        }


class MoveABoxTargetStarted(EventBase):
    """A round's next target: the bays now on each floor and the ones each operator may use.

    Logged for every target after the first, which ``move_a_box_round_started``
    carries. Each crate begins the target where the previous
    ``move_a_box_target_resolved`` left it. Actions logged after this event and
    before the next target or the round's end belong to this target.
    """

    event_type: Literal["move_a_box_target_started"] = "move_a_box_target_started"
    round_number: int
    target_number: int
    bay_identity: str
    floor_bays: dict[str, list[MoveABoxBay]]
    allowed_bays: dict[str, list[int]]


class MoveABoxTargetResolved(EventBase):
    """One scored target of a round that holds more than one.

    ``final_bays`` is the bay number each crate scored for, or None, and
    ``points`` what the target paid each operator. Logged for every target of a
    round when ``targets_per_round`` is above 1; the round's own result follows
    in ``move_a_box_round_resolved``.
    """

    event_type: Literal["move_a_box_target_resolved"] = "move_a_box_target_resolved"
    round_number: int
    target_number: int
    final_cells: dict[str, tuple[int, int]]
    final_bays: dict[str, int | None]
    matched_slots: tuple[int, ...]
    matched: bool
    points: dict[str, int]


class MoveABoxActionTaken(EventBase):
    """One accepted action. ``sequence`` orders both operators' actions within the round.

    ``action`` is the haul method, ``stand_by`` or ``pack_ice``. ``temperature``
    is the crate's reading after it, which is what the other operator can see.
    ``reasoning`` is the sentence the operator gave, never shown to the other
    operator, and None when the run's ``action_reasoning`` is off.
    ``virtual_time_s`` is the virtual second of the run the action landed at
    under ``virtual_clock``, and None otherwise.
    """

    event_type: Literal["move_a_box_action_taken"] = "move_a_box_action_taken"
    round_number: int
    agent_id: str
    crate_id: str
    crate_marking: str
    sequence: int
    action: str
    direction: str | None
    from_cell: tuple[int, int]
    to_cell: tuple[int, int]
    temperature: int
    steps_used: int
    reasoning: str | None
    virtual_time_s: float | None = None


class MoveABoxNoteWritten(EventBase):
    """An operator wrote its private note. The other operator never sees it."""

    event_type: Literal["move_a_box_note_written"] = "move_a_box_note_written"
    round_number: int
    agent_id: str
    text: str


class MoveABoxOperatorFinished(EventBase):
    """An operator called finish; its crate's square is final for the round.

    ``bay`` is the bay number the crate stands on, or None when it stands
    elsewhere. ``virtual_time_s`` is the virtual second of the run the finish
    landed at under ``virtual_clock``, and None otherwise.
    """

    event_type: Literal["move_a_box_operator_finished"] = "move_a_box_operator_finished"
    round_number: int
    agent_id: str
    crate_id: str
    crate_marking: str
    cell: tuple[int, int]
    bay: int | None
    temperature: int
    steps_used: int
    reasoning: str | None
    virtual_time_s: float | None = None


class MoveABoxRequestReleased(EventBase):
    """One operator's model response, released by the virtual clock.

    ``started_at_s`` and ``completed_at_s`` are virtual seconds since the run
    started: the request costs ``virtual_base_latency_s`` plus its
    ``output_tokens`` at ``virtual_output_tokens_per_second``. Logged only under
    ``virtual_clock``.
    """

    event_type: Literal["move_a_box_request_released"] = "move_a_box_request_released"
    agent_id: str
    started_at_s: float
    completed_at_s: float
    output_tokens: int


class MoveABoxRoundResolved(EventBase):
    """Where each crate ended, on which bay, and whether the round matched.

    ``final_bays`` and ``matched_slots`` describe the round's last scored
    target. ``points`` is each operator's score over every target of the round:
    the delivery points, plus the match bonus for every slot that met. ``matched``
    is true when every target the round holds matched.
    """

    event_type: Literal["move_a_box_round_resolved"] = "move_a_box_round_resolved"
    round_number: int
    final_cells: dict[str, tuple[int, int]]
    final_bays: dict[str, int | None]
    temperatures: dict[str, int]
    steps_used: dict[str, int]
    points: dict[str, int]
    matched_slots: tuple[int, ...]
    matched: bool
    success: bool
    trigger: str
