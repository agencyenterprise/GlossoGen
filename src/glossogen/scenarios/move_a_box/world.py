"""Round state for move_a_box: where each crate stands, its readings, and the verdicts.

Every action goes into one ordered log per round. Each operator has a read
position in it, so the scenario can tell whether the other operator has acted
since this one last looked, which is what holds a lockstep action open. The log
itself is never rendered to an operator: the only trace of the other crate is
its reading.

A round plays one target or several. Each target is scored when no operator can
act on it any more, and the crates carry on from there into the next target
with the readings, step counts and log of the round unchanged.
"""

from typing import NamedTuple

from glossogen.scenario_contract.scenario_world import ScenarioWorld
from glossogen.scenarios.move_a_box.depot import Cell, RoundDepot, TargetLayout, step
from glossogen.scenarios.move_a_box.ids import (
    BASE_TEMPERATURE,
    DELIVERY_POINTS,
    FINISH_TOOL,
    MATCH_BONUS,
    TEMPERATURE_DELTA,
    Direction,
    HaulMethod,
    crate_ids,
    owner_of,
    slot_of,
)


class LoggedAction(NamedTuple):
    """One entry of a round's log: a haul, a cooling action, or a finish.

    ``agent_id`` is the operator that acted and ``crate_id`` the crate it acted
    on, which differ once an operator works more than one.
    """

    sequence: int
    agent_id: str
    crate_id: str
    action: str
    direction: str | None
    from_cell: Cell
    cell: Cell
    temperature: int


class TargetOutcome(NamedTuple):
    """One scored target of a round.

    The crate maps are keyed by crate id and ``points`` by operator: the
    delivery points and match bonus this target paid. ``matched_slots`` holds
    every crate slot whose copies all ended on one bay, and ``matched`` is true
    when every slot did.
    """

    target_number: int
    final_cells: dict[str, Cell]
    final_bays: dict[str, int | None]
    matched_slots: tuple[int, ...]
    matched: bool
    points: dict[str, int]


class RoundOutcome(NamedTuple):
    """A resolved round.

    The crate maps are keyed by crate id, ``steps_used`` and ``points`` by
    operator. ``final_bays`` and ``matched_slots`` describe the last target the
    round scored, and ``points`` sums every target. ``matched`` is true when
    every target the round holds matched, so a round that ended before its last
    target never matches.
    """

    round_number: int
    final_cells: dict[str, Cell]
    final_bays: dict[str, int | None]
    temperatures: dict[str, int]
    steps_used: dict[str, int]
    points: dict[str, int]
    matched_slots: tuple[int, ...]
    matched: bool
    trigger: str


class _OpenRound(NamedTuple):
    depot: RoundDepot
    targets: list[TargetLayout]
    target_outcomes: list[TargetOutcome]
    cells: dict[str, Cell]
    readings: dict[str, list[int]]
    steps_used: dict[str, int]
    finished: set[str]
    notes: dict[str, str]
    log: list[LoggedAction]
    shown_up_to: dict[str, int]
    releases: dict[str, int]


class MoveABoxWorld(ScenarioWorld):
    """The open round's crates, readings and log, and every resolved round's outcome."""

    def __init__(
        self,
        agent_ids: tuple[str, ...],
        crates_each: int,
        targets_per_round: int,
        grid_size: int,
        steps_per_round: int,
        batched_actions: bool,
    ) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._agent_ids = agent_ids
        self._crates_each = crates_each
        self._crates_of = {
            agent_id: crate_ids(agent_id=agent_id, crates_each=crates_each)
            for agent_id in agent_ids
        }
        self._crate_ids = tuple(
            crate_id for crates in self._crates_of.values() for crate_id in crates
        )
        self._targets_per_round = targets_per_round
        self._grid_size = grid_size
        self._steps_per_round = steps_per_round
        self._batched_actions = batched_actions
        self._open: _OpenRound | None = None
        self._outcomes: dict[int, RoundOutcome] = {}

    def start_round(self, depot: RoundDepot) -> None:
        """Place every crate on its operator's start square with a full step budget."""
        self._open = _OpenRound(
            depot=depot,
            targets=[depot.first_target],
            target_outcomes=[],
            cells={crate_id: depot.starts[owner_of(crate_id)] for crate_id in self._crate_ids},
            readings={crate_id: [BASE_TEMPERATURE] for crate_id in self._crate_ids},
            steps_used=dict.fromkeys(self._agent_ids, 0),
            finished=set(),
            notes=dict.fromkeys(self._agent_ids, ""),
            log=[],
            shown_up_to=dict.fromkeys(self._agent_ids, 0),
            releases=dict.fromkeys(self._agent_ids, 0),
        )

    @property
    def round_open(self) -> bool:
        """Whether a round has started and has not been resolved."""
        return self._open is not None

    def _round(self) -> _OpenRound:
        if self._open is None:
            raise ValueError("No round is in progress.")
        return self._open

    @property
    def depot(self) -> RoundDepot:
        """The open round's floor."""
        return self._round().depot

    @property
    def target(self) -> TargetLayout:
        """The bays of the target the open round is on."""
        return self._round().targets[-1]

    @property
    def target_number(self) -> int:
        """Which of the open round's targets is in play, counted from 1."""
        return len(self._round().targets)

    def target_scored(self) -> bool:
        """Whether the target in play has been scored."""
        state = self._round()
        return len(state.target_outcomes) == len(state.targets)

    def on_last_target(self) -> bool:
        """Whether the target in play is the round's last."""
        return self.target_number >= self._targets_per_round

    def start_target(self, layout: TargetLayout) -> None:
        """Open the next target: every crate stays where it stands and may be worked again.

        Raises ``ValueError`` while the target in play has not been scored.
        """
        state = self._round()
        if len(state.target_outcomes) != len(state.targets):
            raise ValueError("The target in play has not been scored.")
        state.targets.append(layout)
        state.finished.clear()
        for agent_id in self._agent_ids:
            state.releases[agent_id] = 0

    def crates_of(self, agent_id: str) -> tuple[str, ...]:
        """``agent_id``'s crate ids, slot 1 upwards."""
        return self._crates_of[agent_id]

    @property
    def crate_ids(self) -> tuple[str, ...]:
        """Every crate on the depot, operator by operator and slot by slot."""
        return self._crate_ids

    def cell_of(self, crate_id: str) -> Cell:
        """Where ``crate_id`` stands now."""
        return self._round().cells[crate_id]

    def temperature_of(self, crate_id: str) -> int:
        """``crate_id``'s current reading."""
        return self._round().readings[crate_id][-1]

    def readings_of(self, crate_id: str) -> tuple[int, ...]:
        """Every reading taken from ``crate_id`` this round, in order."""
        return tuple(self._round().readings[crate_id])

    def steps_left(self, agent_id: str) -> int:
        """Actions ``agent_id`` may still take this round."""
        return self._steps_per_round - self._round().steps_used[agent_id]

    def steps_used(self, agent_id: str) -> int:
        """Actions ``agent_id`` has taken this round."""
        return self._round().steps_used[agent_id]

    def note_of(self, agent_id: str) -> str:
        """``agent_id``'s private note, empty until it writes one."""
        return self._round().notes[agent_id]

    def write_note(self, agent_id: str, text: str) -> None:
        """Replace ``agent_id``'s private note."""
        self._round().notes[agent_id] = text

    def has_finished(self, crate_id: str) -> bool:
        """Whether ``crate_id`` was called finished on the target in play."""
        return crate_id in self._round().finished

    def is_done(self, agent_id: str) -> bool:
        """Whether ``agent_id`` can no longer act: every crate finished, or no steps left."""
        if self.steps_left(agent_id=agent_id) <= 0:
            return True
        return all(self.has_finished(crate_id=crate_id) for crate_id in self._crates_of[agent_id])

    def _span(self) -> str:
        """What a finish holds for, as an operator reads it: the round, or the target."""
        if self._targets_per_round > 1:
            return "for this target"
        return "this round"

    def _finish_instruction(self) -> str:
        """How an operator out of steps is told to finish its open crates, by the tools it has."""
        if self._batched_actions:
            return "Call act with finish for every crate still open."
        return "Call finish on every crate still open."

    def all_done(self) -> bool:
        """Whether no operator can act again on the target in play."""
        return self._open is not None and all(
            self.is_done(agent_id=agent_id) for agent_id in self._agent_ids
        )

    def bay_of(self, agent_id: str, cell: Cell) -> int | None:
        """The bay number at ``cell`` on ``agent_id``'s floor, or None when no bay stands there."""
        return self.target.bay_at(agent_id=agent_id, cell=cell)

    def scored_bay_of(self, crate_id: str, cell: Cell) -> int | None:
        """The bay ``crate_id`` would score for being left on ``cell``.

        None when no bay stands there, and None when a bay does but the depot
        assigned it to the other operator.
        """
        number = self.bay_of(agent_id=owner_of(crate_id), cell=cell)
        if number is None:
            return None
        if number not in self.target.allowed_bays[owner_of(crate_id)]:
            return None
        return number

    def action_refusal(self, crate_id: str) -> str | None:
        """Why ``crate_id`` cannot be acted on now, or None when it can."""
        state = self._round()
        if crate_id in state.finished:
            return f"You finished this crate {self._span()}; its square is final."
        if self.steps_left(agent_id=owner_of(crate_id)) <= 0:
            return f"You have no steps left this round. {self._finish_instruction()}"
        return None

    def haul_refusal(self, crate_id: str, direction: Direction) -> str | None:
        """Why ``crate_id`` cannot be hauled ``direction`` now, or None when it can."""
        refusal = self.action_refusal(crate_id=crate_id)
        if refusal is not None:
            return refusal
        state = self._round()
        here = state.cells[crate_id]
        there = step(cell=here, direction=direction, grid_size=self._grid_size)
        if there is None:
            return f"Hauling {direction.value} from {here.label()} leaves the floor. No step spent."

        if there in state.depot.pallets[owner_of(crate_id)]:
            return (
                f"{there.label()} is blocked by pallets, so the crate cannot go {direction.value} "
                "from here. No step spent."
            )
        return None

    def haul(self, crate_id: str, method: HaulMethod, direction: Direction) -> LoggedAction:
        """Carry a crate one square; raises ``ValueError`` on anything ``haul_refusal`` names."""
        refusal = self.haul_refusal(crate_id=crate_id, direction=direction)
        if refusal is not None:
            raise ValueError(refusal)
        state = self._round()
        here = state.cells[crate_id]
        there = step(cell=here, direction=direction, grid_size=self._grid_size)
        assert there is not None
        state.cells[crate_id] = there
        return self._spend(
            crate_id=crate_id, action=method.value, direction=direction.value, from_cell=here
        )

    def cool(self, crate_id: str, action: str) -> LoggedAction:
        """Take a cooling action in place; raises ``ValueError`` when the crate cannot be worked."""
        refusal = self.action_refusal(crate_id=crate_id)
        if refusal is not None:
            raise ValueError(refusal)
        state = self._round()
        return self._spend(
            crate_id=crate_id, action=action, direction=None, from_cell=state.cells[crate_id]
        )

    def finish_refusal(self, crate_id: str) -> str | None:
        """Why ``crate_id`` cannot be finished now, or None when it can."""
        if crate_id in self._round().finished:
            return f"You already finished this crate {self._span()}."
        return None

    def finish(self, crate_id: str) -> LoggedAction:
        """Fix ``crate_id`` for the round; raises ``ValueError`` on a second call."""
        refusal = self.finish_refusal(crate_id=crate_id)
        if refusal is not None:
            raise ValueError(refusal)
        state = self._round()
        state.finished.add(crate_id)
        return self._append(
            crate_id=crate_id,
            action=FINISH_TOOL,
            direction=None,
            from_cell=state.cells[crate_id],
        )

    def _spend(
        self, crate_id: str, action: str, direction: str | None, from_cell: Cell
    ) -> LoggedAction:
        """Charge the operator one step and move that crate's reading by the action's delta."""
        state = self._round()
        state.steps_used[owner_of(crate_id)] += 1
        state.readings[crate_id].append(state.readings[crate_id][-1] + TEMPERATURE_DELTA[action])
        return self._append(
            crate_id=crate_id, action=action, direction=direction, from_cell=from_cell
        )

    def _append(
        self, crate_id: str, action: str, direction: str | None, from_cell: Cell
    ) -> LoggedAction:
        state = self._round()
        entry = LoggedAction(
            sequence=len(state.log) + 1,
            agent_id=owner_of(crate_id),
            crate_id=crate_id,
            action=action,
            direction=direction,
            from_cell=from_cell,
            cell=state.cells[crate_id],
            temperature=state.readings[crate_id][-1],
        )
        state.log.append(entry)
        return entry

    def mark_shown(self, agent_id: str) -> None:
        """Record that ``agent_id`` has been shown the readout as it stands."""
        if self._open is None:
            return
        self._open.shown_up_to[agent_id] = len(self._open.log)

    def has_unseen(self, agent_id: str) -> bool:
        """Whether the other operator has acted since ``agent_id`` was last shown the readout."""
        if self._open is None:
            return False
        state = self._open
        return any(entry.agent_id != agent_id for entry in state.log[state.shown_up_to[agent_id] :])

    def claim_release(self, agent_id: str, limit: int) -> bool:
        """Count one release of ``agent_id`` from a wait; False once ``limit`` are spent."""
        if self._open is None:
            return False
        releases = self._open.releases
        if releases[agent_id] >= limit:
            return False
        releases[agent_id] += 1
        return True

    def resolve_target(self) -> TargetOutcome:
        """Score the target in play: the bay under each crate decides it, if the depot assigned it.

        A bay takes one crate per floor, so when an operator leaves two crates on
        one bay only the lower slot scores its delivery. A crate slot converges
        when every operator's crate in that slot ended on one bay, and each
        converged slot pays every operator the bonus. Raises ``ValueError`` when
        the target was already scored.
        """
        state = self._round()
        if len(state.target_outcomes) == len(state.targets):
            raise ValueError("The target in play has already been scored.")
        final_bays: dict[str, int | None] = {}
        taken: dict[str, set[int]] = {agent_id: set() for agent_id in self._agent_ids}
        for crate_id in self._crate_ids:
            bay = self.scored_bay_of(crate_id=crate_id, cell=state.cells[crate_id])
            owner = owner_of(crate_id)
            if bay is not None and bay in taken[owner]:
                bay = None
            if bay is not None:
                taken[owner].add(bay)
            final_bays[crate_id] = bay

        matched_slots: list[int] = []
        for slot in range(1, self._crates_each + 1):
            bays = [
                final_bays[crate_id] for crate_id in self._crate_ids if slot_of(crate_id) == slot
            ]
            if None not in bays and len(set(bays)) == 1:
                matched_slots.append(slot)

        points: dict[str, int] = {}
        for agent_id in self._agent_ids:
            scored = sum(
                DELIVERY_POINTS
                for crate_id in self._crates_of[agent_id]
                if final_bays[crate_id] is not None
            )
            scored += MATCH_BONUS * len(matched_slots)
            points[agent_id] = scored

        outcome = TargetOutcome(
            target_number=len(state.targets),
            final_cells=dict(state.cells),
            final_bays=final_bays,
            matched_slots=tuple(matched_slots),
            matched=len(matched_slots) == self._crates_each,
            points=points,
        )
        state.target_outcomes.append(outcome)
        return outcome

    def resolve(self, round_number: int, trigger: str) -> RoundOutcome:
        """Close the round on the targets it scored, scoring the one in play if it has not been.

        The round matches only when it scored every target it holds and each of
        them matched.
        """
        state = self._round()
        if len(state.target_outcomes) != len(state.targets):
            self.resolve_target()
        last = state.target_outcomes[-1]
        outcome = RoundOutcome(
            round_number=round_number,
            final_cells=dict(state.cells),
            final_bays=last.final_bays,
            temperatures={crate_id: readings[-1] for crate_id, readings in state.readings.items()},
            steps_used=dict(state.steps_used),
            points={
                agent_id: sum(target.points[agent_id] for target in state.target_outcomes)
                for agent_id in self._agent_ids
            },
            matched_slots=last.matched_slots,
            matched=len(state.target_outcomes) == self._targets_per_round
            and all(target.matched for target in state.target_outcomes),
            trigger=trigger,
        )
        self._outcomes[round_number] = outcome
        self._open = None
        return outcome

    def outcome(self, round_number: int) -> RoundOutcome | None:
        """The resolved round, or None."""
        return self._outcomes.get(round_number)

    def seed_outcome(self, outcome: RoundOutcome) -> None:
        """Restore a round resolved before a fork or resume."""
        self._outcomes[outcome.round_number] = outcome

    def points_so_far(self, agent_id: str) -> int:
        """``agent_id``'s points over every resolved round and the open round's scored targets."""
        resolved = sum(outcome.points[agent_id] for outcome in self._outcomes.values())
        if self._open is None:
            return resolved
        return resolved + sum(target.points[agent_id] for target in self._open.target_outcomes)
