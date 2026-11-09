"""move_a_box extension to the platform run-detail API.

Gives the round-detail panel each round's targets, and for each target every
operator's floor as that operator saw it: the pallets and bays on it, where the
crate began the target, and its path with the reading it took after every
action. A round of one target has one. All floors of a round come back together,
so the panel can show what one operator could have read off the other's crate.
A run on the virtual clock also gets each round's clock lanes.
"""

from typing import ClassVar, Literal, NamedTuple

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent, SimulationStarted
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenarios.move_a_box.clock_lanes import MoveABoxRoundClock, round_clocks
from glossogen.scenarios.move_a_box.events import (
    MoveABoxActionTaken,
    MoveABoxBay,
    MoveABoxOperatorFinished,
    MoveABoxRoundResolved,
    MoveABoxRoundStarted,
    MoveABoxTargetResolved,
    MoveABoxTargetStarted,
)
from glossogen.scenarios.move_a_box.ids import (
    BASE_TEMPERATURE,
    TEMPERATURE_DELTA,
    BayIdentity,
    owner_of,
    slot_of,
)


class MoveABoxCell(BaseModel):
    """A square of the floor, counted from 1 at the top left."""

    row: int
    col: int


class MoveABoxFloorBay(BaseModel):
    """A bay on one operator's floor.

    ``number`` is what scoring compares across floors. ``name`` is what the
    operators called it: its square, its symbol or its letter. ``label`` is what
    the panel draws on it: the bay number when bays are named by square, the
    mark the operator saw otherwise.
    """

    number: int
    name: str
    label: str
    cell: MoveABoxCell


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
    """One crate's path through one target and where it ended.

    ``slot`` is which of its operator's crates this is, counted from 1. Crates
    are matched by slot, so every operator's slot 1 has to meet on one bay.
    ``final_bay`` is None when the crate ended off the bays, on one the depot
    did not assign it, or on a bay another of its operator's crates already
    took, and while the target has not been scored.
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
    """One operator's side of one target: its floor, its crates and what the target paid it.

    ``start`` is the square the crate began the target on: the round's start
    square for the first target, where the crate was left for every later one.
    ``bays`` is every bay on this floor for this target. ``pallets`` and
    ``allowed_bays`` are this operator's alone; the depot assigns every other
    operator a different set.
    """

    agent_id: str
    start: MoveABoxCell
    bays: list[MoveABoxFloorBay]
    pallets: list[MoveABoxCell]
    allowed_bays: list[int]
    points: int
    crates: list[MoveABoxCrateTrace]


class MoveABoxTargetFloor(BaseModel):
    """One target of a round: the bay numbers on every list, its result, each operator's side.

    ``scored`` is false while the target is still being played, and then
    ``matched`` and ``matched_slots`` say nothing yet.
    """

    target_number: int
    shared_bays: list[int]
    matched_slots: list[int]
    matched: bool
    scored: bool
    operators: list[MoveABoxOperatorFloor]


class MoveABoxRoundFloor(BaseModel):
    """One round: every target it has reached, in order, and whether every target matched.

    ``clock`` is each operator's time on the virtual clock in this round, or None
    for a run with the clock off.
    """

    round_number: int
    grid_size: int
    matched: bool
    targets: list[MoveABoxTargetFloor]
    clock: MoveABoxRoundClock | None


class MoveABoxRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for move_a_box runs.

    One case is one round. ``targets_per_round`` is how many targets each round
    holds. ``base_temperature`` and ``temperature_delta`` travel with the cases so
    the panel draws the readings from the scenario's own numbers instead of
    keeping a copy that drifts.
    """

    scenario_name: Literal["move_a_box"] = "move_a_box"
    targets_per_round: int
    base_temperature: int
    temperature_delta: dict[str, int]
    cases: list[MoveABoxRoundFloor]


class _TargetLayout(NamedTuple):
    """The bays a target put on each floor, as its round or target event logged them."""

    bay_identity: str
    floor_bays: dict[str, list[MoveABoxBay]]
    allowed_bays: dict[str, list[int]]


class _TargetResult(NamedTuple):
    """A scored target, from its own event or, for a round of one target, the round's."""

    final_cells: dict[str, tuple[int, int]]
    final_bays: dict[str, int | None]
    matched_slots: tuple[int, ...]
    matched: bool
    points: dict[str, int]


class _RoundEvents(NamedTuple):
    """Everything one round logged, its actions and finishes sorted by the target they fell in."""

    started: MoveABoxRoundStarted
    layouts: list[_TargetLayout]
    actions: list[list[MoveABoxActionTaken]]
    finishes: list[dict[str, MoveABoxOperatorFinished]]
    results: dict[int, _TargetResult]


def _cell(pair: tuple[int, int]) -> MoveABoxCell:
    return MoveABoxCell(row=pair[0], col=pair[1])


def _floor_bay(bay: MoveABoxBay, bay_identity: str) -> MoveABoxFloorBay:
    """One bay of a floor as the panel draws it."""
    label = bay.mark
    if bay_identity == BayIdentity.SQUARE.value:
        label = str(bay.number)
    return MoveABoxFloorBay(
        number=bay.number, name=bay.name, label=label, cell=_cell(pair=bay.cell)
    )


def _targets_per_round(events: list[SimulationEvent]) -> int:
    """The run's ``targets_per_round``; a run recorded before the knob holds one target a round."""
    for event in events:
        if isinstance(event, SimulationStarted):
            return int(event.scenario_config.get("targets_per_round", 1))
    return 1


def _group_rounds(events: list[SimulationEvent]) -> dict[int, _RoundEvents]:
    """Every started round's events, each action and finish filed under the target in play.

    The log is in order, so an action belongs to the latest target started
    before it in its round.
    """
    rounds: dict[int, _RoundEvents] = {}
    resolved: dict[int, MoveABoxRoundResolved] = {}
    for event in events:
        if isinstance(event, MoveABoxRoundStarted):
            rounds[event.round_number] = _RoundEvents(
                started=event,
                layouts=[
                    _TargetLayout(
                        bay_identity=event.bay_identity,
                        floor_bays=event.floor_bays,
                        allowed_bays=event.allowed_bays,
                    )
                ],
                actions=[[]],
                finishes=[{}],
                results={},
            )
        elif event.round_number not in rounds:
            continue
        elif isinstance(event, MoveABoxTargetStarted):
            played = rounds[event.round_number]
            played.layouts.append(
                _TargetLayout(
                    bay_identity=event.bay_identity,
                    floor_bays=event.floor_bays,
                    allowed_bays=event.allowed_bays,
                )
            )
            played.actions.append([])
            played.finishes.append({})
        elif isinstance(event, MoveABoxActionTaken):
            rounds[event.round_number].actions[-1].append(event)
        elif isinstance(event, MoveABoxOperatorFinished):
            rounds[event.round_number].finishes[-1][event.crate_id] = event
        elif isinstance(event, MoveABoxTargetResolved):
            rounds[event.round_number].results[event.target_number] = _TargetResult(
                final_cells=event.final_cells,
                final_bays=event.final_bays,
                matched_slots=event.matched_slots,
                matched=event.matched,
                points=event.points,
            )
        elif isinstance(event, MoveABoxRoundResolved):
            resolved[event.round_number] = event
    for round_number, event in resolved.items():
        played = rounds[round_number]
        if not played.results:
            played.results[len(played.layouts)] = _TargetResult(
                final_cells=event.final_cells,
                final_bays=event.final_bays,
                matched_slots=event.matched_slots,
                matched=event.matched,
                points=event.points,
            )
    return rounds


def _crate_trace(
    crate_id: str,
    marking: str,
    start: tuple[int, int],
    start_temperature: int,
    actions: list[MoveABoxActionTaken],
    finished: bool,
    result: _TargetResult | None,
) -> MoveABoxCrateTrace:
    """One crate's path through one target, from that target's events."""
    final_cell = start
    final_temperature = start_temperature
    if actions:
        final_cell = actions[-1].to_cell
        final_temperature = actions[-1].temperature
    final_bay: int | None = None
    if result is not None:
        final_cell = result.final_cells[crate_id]
        final_bay = result.final_bays[crate_id]
    return MoveABoxCrateTrace(
        crate_id=crate_id,
        marking=marking,
        slot=slot_of(crate_id),
        steps=[
            MoveABoxCrateStep(
                sequence=action.sequence,
                action=action.action,
                direction=action.direction,
                cell=_cell(pair=action.to_cell),
                temperature=action.temperature,
                reasoning=action.reasoning,
            )
            for action in actions
        ],
        final_cell=_cell(pair=final_cell),
        final_bay=final_bay,
        final_temperature=final_temperature,
        finished=finished,
    )


def _shared_bays(allowed_bays: dict[str, list[int]]) -> list[int]:
    """The bay numbers the depot assigned to every operator."""
    sets: list[set[int]] = [set(bays) for bays in allowed_bays.values()]
    if not sets:
        return []
    shared = sets[0]
    for other in sets[1:]:
        shared = shared & other
    return sorted(shared)


def _build_round(
    played: _RoundEvents, round_matched: bool, clock: MoveABoxRoundClock | None
) -> MoveABoxRoundFloor:
    """One round's targets in order, each crate starting where the target before left it."""
    started = played.started
    crates_of = {
        agent_id: sorted(
            (crate_id for crate_id in started.crate_ids if owner_of(crate_id) == agent_id),
            key=slot_of,
        )
        for agent_id in sorted(started.start_cells)
    }
    position = {
        crate_id: started.start_cells[agent_id]
        for agent_id, crate_ids in crates_of.items()
        for crate_id in crate_ids
    }
    temperature = dict.fromkeys(position, BASE_TEMPERATURE)
    targets: list[MoveABoxTargetFloor] = []
    for index, layout in enumerate(played.layouts):
        target_number = index + 1
        result = played.results.get(target_number)
        operators: list[MoveABoxOperatorFloor] = []
        for agent_id, crate_ids in crates_of.items():
            traces = [
                _crate_trace(
                    crate_id=crate_id,
                    marking=started.crate_ids[crate_id],
                    start=position[crate_id],
                    start_temperature=temperature[crate_id],
                    actions=[
                        action for action in played.actions[index] if action.crate_id == crate_id
                    ],
                    finished=crate_id in played.finishes[index],
                    result=result,
                )
                for crate_id in crate_ids
            ]
            points = 0
            if result is not None:
                points = result.points[agent_id]
            operators.append(
                MoveABoxOperatorFloor(
                    agent_id=agent_id,
                    start=_cell(pair=position[crate_ids[0]]),
                    bays=[
                        _floor_bay(bay=bay, bay_identity=layout.bay_identity)
                        for bay in layout.floor_bays[agent_id]
                    ],
                    pallets=[_cell(pair=pair) for pair in started.pallets[agent_id]],
                    allowed_bays=list(layout.allowed_bays[agent_id]),
                    points=points,
                    crates=traces,
                )
            )
            for trace in traces:
                position[trace.crate_id] = (trace.final_cell.row, trace.final_cell.col)
                temperature[trace.crate_id] = trace.final_temperature
        matched = False
        matched_slots: list[int] = []
        if result is not None:
            matched = result.matched
            matched_slots = list(result.matched_slots)
        targets.append(
            MoveABoxTargetFloor(
                target_number=target_number,
                shared_bays=_shared_bays(allowed_bays=layout.allowed_bays),
                matched_slots=matched_slots,
                matched=matched,
                scored=result is not None,
                operators=operators,
            )
        )
    return MoveABoxRoundFloor(
        round_number=started.round_number,
        grid_size=started.grid_size,
        matched=round_matched,
        targets=targets,
        clock=clock,
    )


def _operator_ids(rounds: dict[int, _RoundEvents]) -> list[str]:
    """The operators in the order the panel lists them, from the first round's start squares."""
    if not rounds:
        return []
    return sorted(rounds[min(rounds)].started.start_cells)


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
        round_matched = {
            event.round_number: event.matched
            for event in events
            if isinstance(event, MoveABoxRoundResolved)
        }
        rounds = _group_rounds(events=events)
        clocks = round_clocks(events=events, agent_ids=_operator_ids(rounds=rounds))
        return MoveABoxRunExtras(
            targets_per_round=_targets_per_round(events=events),
            base_temperature=BASE_TEMPERATURE,
            temperature_delta=dict(TEMPERATURE_DELTA),
            cases=[
                _build_round(
                    played=played,
                    round_matched=round_matched.get(round_number, False),
                    clock=clocks.get(round_number),
                )
                for round_number, played in sorted(rounds.items())
            ],
        )
