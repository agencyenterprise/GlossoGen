"""move_a_box extension to the platform run-detail API.

Gives the round-detail panel each round's floor as each operator saw it, the
pallets and bays on it, and the crate's whole path with the reading it took after
every action. Both floors of a round come back together, so the panel can show
what one operator could have read off the other's crate.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenarios.move_a_box.events import (
    MoveABoxActionTaken,
    MoveABoxOperatorFinished,
    MoveABoxRoundResolved,
    MoveABoxRoundStarted,
)
from glossogen.scenarios.move_a_box.ids import (
    BASE_TEMPERATURE,
    TEMPERATURE_DELTA,
    owner_of,
    slot_of,
)


class MoveABoxCell(BaseModel):
    """A square of the floor, counted from 1 at the top left."""

    row: int
    col: int


class MoveABoxCrateStep(BaseModel):
    """One action, and where the crate stood and what it read after it.

    ``action`` is the haul method, ``stand_by`` or ``pack_ice``. ``direction``
    is None for the actions that do not move the crate.
    """

    sequence: int
    action: str
    direction: str | None
    cell: MoveABoxCell
    temperature: int
    reasoning: str | None


class MoveABoxCrateTrace(BaseModel):
    """One crate's path through a round and where it ended.

    ``slot`` is which of its operator's crates this is, counted from 1. Crates
    are matched by slot, so every operator's slot 1 has to meet on one bay.
    ``final_bay`` is None when the crate ended off the bays, on one the depot
    did not assign it, or on a bay another of its operator's crates already took.
    """

    crate_id: str
    marking: str
    slot: int
    steps: list[MoveABoxCrateStep]
    final_cell: MoveABoxCell
    final_bay: int | None
    final_temperature: int
    finished: bool


class MoveABoxOperatorFloor(BaseModel):
    """One operator's side of a round: its floor, its crates and what it scored.

    ``pallets`` and ``allowed_bays`` are this operator's alone; the depot
    assigns every other operator a different set.
    """

    agent_id: str
    start: MoveABoxCell
    pallets: list[MoveABoxCell]
    allowed_bays: list[int]
    points: int
    crates: list[MoveABoxCrateTrace]


class MoveABoxRoundFloor(BaseModel):
    """One round: the bays every operator shares, and each operator's side of it."""

    round_number: int
    grid_size: int
    bays: list[MoveABoxCell]
    shared_bays: list[int]
    matched_slots: list[int]
    matched: bool
    operators: list[MoveABoxOperatorFloor]


class MoveABoxRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for move_a_box runs.

    One case is one round's floors. ``base_temperature`` and
    ``temperature_delta`` travel with them so the panel draws the readings from
    the scenario's own numbers instead of keeping a copy that drifts.
    """

    scenario_name: Literal["move_a_box"] = "move_a_box"
    base_temperature: int
    temperature_delta: dict[str, int]
    cases: list[MoveABoxRoundFloor]


def _cell(pair: tuple[int, int]) -> MoveABoxCell:
    return MoveABoxCell(row=pair[0], col=pair[1])


def _crate_trace(
    crate_id: str,
    started: MoveABoxRoundStarted,
    actions: list[MoveABoxActionTaken],
    finished: MoveABoxOperatorFinished | None,
    resolved: MoveABoxRoundResolved | None,
) -> MoveABoxCrateTrace:
    """One crate's path through a round, from the events of that round."""
    steps = [
        MoveABoxCrateStep(
            sequence=action.sequence,
            action=action.action,
            direction=action.direction,
            cell=_cell(pair=action.to_cell),
            temperature=action.temperature,
            reasoning=action.reasoning,
        )
        for action in actions
    ]
    final_cell = started.start_cells[owner_of(crate_id)]
    final_temperature = BASE_TEMPERATURE
    if actions:
        final_cell = actions[-1].to_cell
        final_temperature = actions[-1].temperature
    final_bay: int | None = None
    if resolved is not None:
        final_cell = resolved.final_cells[crate_id]
        final_bay = resolved.final_bays[crate_id]
        final_temperature = resolved.temperatures[crate_id]
    return MoveABoxCrateTrace(
        crate_id=crate_id,
        marking=started.crate_ids[crate_id],
        slot=slot_of(crate_id),
        steps=steps,
        final_cell=_cell(pair=final_cell),
        final_bay=final_bay,
        final_temperature=final_temperature,
        finished=finished is not None,
    )


def _operator_floor(
    agent_id: str,
    started: MoveABoxRoundStarted,
    actions: list[MoveABoxActionTaken],
    finishes: dict[str, MoveABoxOperatorFinished],
    resolved: MoveABoxRoundResolved | None,
) -> MoveABoxOperatorFloor:
    """One operator's floor and every crate it worked, from the events of one round."""
    mine = [crate_id for crate_id in started.crate_ids if owner_of(crate_id) == agent_id]
    points = 0
    if resolved is not None:
        points = resolved.points[agent_id]
    return MoveABoxOperatorFloor(
        agent_id=agent_id,
        start=_cell(pair=started.start_cells[agent_id]),
        pallets=[_cell(pair=pair) for pair in started.pallets[agent_id]],
        allowed_bays=list(started.allowed_bays[agent_id]),
        points=points,
        crates=[
            _crate_trace(
                crate_id=crate_id,
                started=started,
                actions=[action for action in actions if action.crate_id == crate_id],
                finished=finishes.get(crate_id),
                resolved=resolved,
            )
            for crate_id in sorted(mine, key=slot_of)
        ],
    )


def _shared_bays(started: MoveABoxRoundStarted) -> list[int]:
    """The bay numbers the depot assigned to every operator."""
    sets: list[set[int]] = [set(bays) for bays in started.allowed_bays.values()]
    if not sets:
        return []
    shared = sets[0]
    for other in sets[1:]:
        shared = shared & other
    return sorted(shared)


def _build_round(
    started: MoveABoxRoundStarted,
    actions: list[MoveABoxActionTaken],
    finishes: dict[str, MoveABoxOperatorFinished],
    resolved: MoveABoxRoundResolved | None,
) -> MoveABoxRoundFloor:
    matched = False
    matched_slots: list[int] = []
    if resolved is not None:
        matched = resolved.matched
        matched_slots = list(resolved.matched_slots)
    return MoveABoxRoundFloor(
        round_number=started.round_number,
        grid_size=started.grid_size,
        bays=[_cell(pair=pair) for pair in started.bays],
        shared_bays=_shared_bays(started=started),
        matched_slots=matched_slots,
        matched=matched,
        operators=[
            _operator_floor(
                agent_id=agent_id,
                started=started,
                actions=[action for action in actions if action.agent_id == agent_id],
                finishes=finishes,
                resolved=resolved,
            )
            for agent_id in sorted(started.start_cells)
        ],
    )


class MoveABoxRunDetailExtension(ScenarioRunDetailExtension):
    """move_a_box hook into :class:`RunDetailResponse.scenario_extras`."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = MoveABoxRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],  # noqa: ARG002 — protocol-required
        messages: list[ChannelMessage],  # noqa: ARG002 — protocol-required
    ) -> MoveABoxRunExtras:
        started_by_round: dict[int, MoveABoxRoundStarted] = {}
        actions_by_round: dict[int, list[MoveABoxActionTaken]] = {}
        finishes_by_round: dict[int, dict[str, MoveABoxOperatorFinished]] = {}
        resolved_by_round: dict[int, MoveABoxRoundResolved] = {}
        for event in events:
            if isinstance(event, MoveABoxRoundStarted):
                started_by_round[event.round_number] = event
            elif isinstance(event, MoveABoxActionTaken):
                actions_by_round.setdefault(event.round_number, []).append(event)
            elif isinstance(event, MoveABoxOperatorFinished):
                finishes_by_round.setdefault(event.round_number, {})[event.crate_id] = event
            elif isinstance(event, MoveABoxRoundResolved):
                resolved_by_round[event.round_number] = event
        return MoveABoxRunExtras(
            base_temperature=BASE_TEMPERATURE,
            temperature_delta=dict(TEMPERATURE_DELTA),
            cases=[
                _build_round(
                    started=started,
                    actions=actions_by_round.get(round_number, []),
                    finishes=finishes_by_round.get(round_number, {}),
                    resolved=resolved_by_round.get(round_number),
                )
                for round_number, started in sorted(started_by_round.items())
            ],
        )
