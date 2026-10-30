"""Round state for move_a_box: where each crate stands, its readings, and the verdicts.

Every action goes into one ordered log per round. Each operator has a read
position in it, so the scenario can tell whether the other operator has acted
since this one last looked, which is what holds a lockstep action open. The log
itself is never rendered to an operator: the only trace of the other crate is
its reading.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.move_a_box.depot import Cell, RoundDepot, step
from glossogen.scenarios.move_a_box.ids import (
    BASE_TEMPERATURE,
    DELIVERY_POINTS,
    FINISH_TOOL,
    MATCH_BONUS,
    TEMPERATURE_DELTA,
    Direction,
    HaulMethod,
)


class LoggedAction(NamedTuple):
    """One entry of a round's log: a haul, a cooling action, or a finish."""

    sequence: int
    agent_id: str
    action: str
    direction: str | None
    from_cell: Cell
    cell: Cell
    temperature: int


class RoundOutcome(NamedTuple):
    """A resolved round."""

    round_number: int
    final_cells: dict[str, Cell]
    final_bays: dict[str, int | None]
    temperatures: dict[str, int]
    steps_used: dict[str, int]
    points: dict[str, int]
    matched: bool
    trigger: str


class _OpenRound(NamedTuple):
    depot: RoundDepot
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

    def __init__(self, agent_ids: tuple[str, ...], grid_size: int, steps_per_round: int) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._agent_ids = agent_ids
        self._grid_size = grid_size
        self._steps_per_round = steps_per_round
        self._open: _OpenRound | None = None
        self._outcomes: dict[int, RoundOutcome] = {}

    def start_round(self, depot: RoundDepot) -> None:
        """Place each crate on its start square with a full step budget."""
        self._open = _OpenRound(
            depot=depot,
            cells=dict(depot.starts),
            readings={agent_id: [BASE_TEMPERATURE] for agent_id in self._agent_ids},
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

    def cell_of(self, agent_id: str) -> Cell:
        """Where ``agent_id``'s crate stands now."""
        return self._round().cells[agent_id]

    def temperature_of(self, agent_id: str) -> int:
        """``agent_id``'s crate's current reading."""
        return self._round().readings[agent_id][-1]

    def readings_of(self, agent_id: str) -> tuple[int, ...]:
        """Every reading taken from ``agent_id``'s crate this round, in order."""
        return tuple(self._round().readings[agent_id])

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

    def has_finished(self, agent_id: str) -> bool:
        """Whether ``agent_id`` called finish this round."""
        return agent_id in self._round().finished

    def is_done(self, agent_id: str) -> bool:
        """Whether ``agent_id`` can no longer act: it finished or spent every step."""
        return self.has_finished(agent_id=agent_id) or self.steps_left(agent_id=agent_id) <= 0

    def all_done(self) -> bool:
        """Whether no operator can act again this round."""
        return self._open is not None and all(
            self.is_done(agent_id=agent_id) for agent_id in self._agent_ids
        )

    def bay_of(self, cell: Cell) -> int | None:
        """The bay number at ``cell``, or None when no bay stands there."""
        for number, bay in enumerate(self._round().depot.bays, start=1):
            if bay == cell:
                return number
        return None

    def scored_bay_of(self, agent_id: str, cell: Cell) -> int | None:
        """The bay ``agent_id`` would score for leaving its crate on ``cell``.

        None when no bay stands there, and None when a bay does but the depot
        assigned it to the other operator.
        """
        number = self.bay_of(cell=cell)
        if number is None:
            return None
        if number not in self._round().depot.allowed_bays[agent_id]:
            return None
        return number

    def allowed_bays(self, agent_id: str) -> tuple[int, ...]:
        """The bay numbers the depot assigned ``agent_id`` this round."""
        return self._round().depot.allowed_bays[agent_id]

    def action_refusal(self, agent_id: str) -> str | None:
        """Why ``agent_id`` cannot act now, or None when it can."""
        state = self._round()
        if agent_id in state.finished:
            return "You finished this round; the crate's square is final."
        if self.steps_left(agent_id=agent_id) <= 0:
            return "You have no steps left this round. Call finish."
        return None

    def haul_refusal(self, agent_id: str, direction: Direction) -> str | None:
        """Why ``agent_id`` cannot haul ``direction`` now, or None when it can."""
        refusal = self.action_refusal(agent_id=agent_id)
        if refusal is not None:
            return refusal
        state = self._round()
        here = state.cells[agent_id]
        there = step(cell=here, direction=direction, grid_size=self._grid_size)
        if there is None:
            return f"Hauling {direction.value} from {here.label()} leaves the floor. No step spent."

        if there in state.depot.pallets[agent_id]:
            return (
                f"{there.label()} is blocked by pallets, so the crate cannot go {direction.value} "
                "from here. No step spent."
            )
        return None

    def haul(self, agent_id: str, method: HaulMethod, direction: Direction) -> LoggedAction:
        """Carry the crate one square; raises ``ValueError`` on anything ``haul_refusal`` names."""
        refusal = self.haul_refusal(agent_id=agent_id, direction=direction)
        if refusal is not None:
            raise ValueError(refusal)
        state = self._round()
        here = state.cells[agent_id]
        there = step(cell=here, direction=direction, grid_size=self._grid_size)
        assert there is not None
        state.cells[agent_id] = there
        return self._spend(
            agent_id=agent_id, action=method.value, direction=direction.value, from_cell=here
        )

    def cool(self, agent_id: str, action: str) -> LoggedAction:
        """Take a cooling action in place; raises ``ValueError`` when the operator cannot act."""
        refusal = self.action_refusal(agent_id=agent_id)
        if refusal is not None:
            raise ValueError(refusal)
        state = self._round()
        return self._spend(
            agent_id=agent_id, action=action, direction=None, from_cell=state.cells[agent_id]
        )

    def finish(self, agent_id: str) -> LoggedAction:
        """Fix ``agent_id``'s crate for the round; raises ``ValueError`` on a second call."""
        state = self._round()
        if agent_id in state.finished:
            raise ValueError("You already finished this round.")
        state.finished.add(agent_id)
        return self._append(
            agent_id=agent_id,
            action=FINISH_TOOL,
            direction=None,
            from_cell=state.cells[agent_id],
        )

    def _spend(
        self, agent_id: str, action: str, direction: str | None, from_cell: Cell
    ) -> LoggedAction:
        """Charge one step and move the reading by what ``action`` does to it."""
        state = self._round()
        state.steps_used[agent_id] += 1
        state.readings[agent_id].append(state.readings[agent_id][-1] + TEMPERATURE_DELTA[action])
        return self._append(
            agent_id=agent_id, action=action, direction=direction, from_cell=from_cell
        )

    def _append(
        self, agent_id: str, action: str, direction: str | None, from_cell: Cell
    ) -> LoggedAction:
        state = self._round()
        entry = LoggedAction(
            sequence=len(state.log) + 1,
            agent_id=agent_id,
            action=action,
            direction=direction,
            from_cell=from_cell,
            cell=state.cells[agent_id],
            temperature=state.readings[agent_id][-1],
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

    def resolve(self, round_number: int, trigger: str) -> RoundOutcome:
        """Close the round: the bay under each crate decides it, when the depot assigned it.

        ``matched`` needs every operator on one bay, so a round where some agree
        and one does not scores the deliveries and no bonus.
        """
        state = self._round()
        final_bays = {
            agent_id: self.scored_bay_of(agent_id=agent_id, cell=cell)
            for agent_id, cell in state.cells.items()
        }
        delivered = [bay for bay in final_bays.values() if bay is not None]
        matched = len(delivered) == len(self._agent_ids) and len(set(delivered)) == 1
        points: dict[str, int] = {}
        for agent_id, bay in final_bays.items():
            scored = 0
            if bay is not None:
                scored += DELIVERY_POINTS
            if matched:
                scored += MATCH_BONUS
            points[agent_id] = scored
        outcome = RoundOutcome(
            round_number=round_number,
            final_cells=dict(state.cells),
            final_bays=final_bays,
            temperatures={agent_id: readings[-1] for agent_id, readings in state.readings.items()},
            steps_used=dict(state.steps_used),
            points=points,
            matched=matched,
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
        """``agent_id``'s points over every resolved round."""
        return sum(outcome.points[agent_id] for outcome in self._outcomes.values())
