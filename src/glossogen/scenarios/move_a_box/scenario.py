"""Two depot operators who can affect each other only through a crate's temperature.

Each operator moves a crate across its own floor to one of the numbered loading
bays. The depot assigns each a different list of bays with one bay on both, so
the bay they can agree on is one neither can name alone. The depot readout
returns every crate's reading after every action, and how the crate is carried
decides what its reading does. Nothing in the task says the reading means
anything.

The geometry is in ``depot``, the round state in ``world``. This module wires
them to the platform.
"""

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event_base import EventBase
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.runtime.activity_notification import DoneNotification, NewInfoNotification
from glossogen.runtime.notification_payload import Wake
from glossogen.runtime.scenario_tool import ScenarioTool
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenario_base import PrimaryChannel, RoundResult
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_run_detail_extension import ScenarioRunDetailExtension
from glossogen.scenarios.move_a_box.depot import (
    Cell,
    crate_tags,
    floor_rows,
    generate_depots,
    humidity_series,
)
from glossogen.scenarios.move_a_box.evaluation.bay_match_metric import BayMatchMetric
from glossogen.scenarios.move_a_box.evaluation.thermal_excess_metric import ThermalExcessMetric
from glossogen.scenarios.move_a_box.events import (
    MoveABoxActionTaken,
    MoveABoxNoteWritten,
    MoveABoxOperatorFinished,
    MoveABoxRoundResolved,
    MoveABoxRoundStarted,
)
from glossogen.scenarios.move_a_box.ids import (
    ACT_TOOL,
    ACTION_RESULT_TEMPLATE,
    ALL_FINISHED_TRIGGER,
    DELIVERY_POINTS,
    DESCRIPTION_TEMPLATE,
    HIDDEN_BASE_TOOLS,
    INJECTION_TEMPLATE,
    MATCH_BONUS,
    NOTEPAD_TOOL,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    READOUT_TEMPLATE,
    RELEASE_NOTICE_TEMPLATE,
    SYSTEM_TEMPLATE,
    TEMPERATURE_DELTA,
    CrateAction,
    haul_method_of,
    operator_ids,
    others_of,
    owner_of,
)
from glossogen.scenarios.move_a_box.knobs import MoveABoxKnobs
from glossogen.scenarios.move_a_box.planned_action import (
    AppliedStep,
    PlannedCrateStep,
    PlannedStep,
    ResolvedStep,
)
from glossogen.scenarios.move_a_box.run_detail_extension import MoveABoxRunDetailExtension
from glossogen.scenarios.move_a_box.wake_package import MoveABoxWake
from glossogen.scenarios.move_a_box.world import LoggedAction, MoveABoxWorld, RoundOutcome
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

RELEASE_LIMIT = 2
"""Times per round an operator is released from a wait nothing can end. Past it the
operator stays parked, and the round ends once both are."""

PARTNER_ACTED = "other_crate_moved"
"""The release detail that wakes a parked operator when the other has acted."""


def act_description(actions_per_call: int) -> str:
    """The ``act`` tool's description, which states how long a list one call takes."""
    return (
        f"Work the crate through a list of 1 to {actions_per_call} actions, applied in order. "
        "drag, sled and cart each carry it one square in the direction you give; stand_by and "
        "pack_ice each take an action without moving it; finish leaves it where it stands for "
        "the rest of the round. Give direction for drag, sled and cart, and null for the other "
        "three. The whole list is applied before any other operator reads the depot readout. "
        "An action the floor refuses stops the list there: the actions before it stand, and the "
        "one that stopped it spends nothing. Returns the depot readout."
    )


NOTEPAD_DESCRIPTION = (
    "Replace your private note with the text you give, and read it back. Nobody else ever "
    "sees it. Call it with an empty text to read the note you have."
)
REASONING_SUFFIX = " reasoning is one sentence on why you are acting this way; nobody else sees it."
CRATE_SUFFIX = " crate is the marking of the crate the action is for, as the readout shows it."
READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing at startup and after a round changes; "
    "during a round it waits until the depot readout changes, then returns it. "
    "read_notifications(wait_for='next_round') declares you are done with this round and waits "
    "for the next briefing. The result is a wake package: the reasons, any briefings, the "
    "readout, and a notice when the wait was cut short; type done ends the run. Must be the "
    "only tool call in its response."
)


class CrateOutcome(NamedTuple):
    """Where one crate was left, as the next round's briefing names it.

    ``bay`` is the square the crate was left on, or None when it reached no bay
    it could score. A bay carries no number an operator could name: it is the
    square it stands on.
    """

    marking: str
    bay: str | None


class PreviousRound(NamedTuple):
    """The previous round from one operator's side, as the briefing reads it.

    ``own_crates`` runs in slot order, and ``other_crates`` in operator order
    then slot order with this operator left out, which is the order the readout
    lists them in. Crates are matched by slot, so an operator that cannot tell
    which of its crates landed where cannot learn anything from the round.
    """

    round_number: int
    own_crates: tuple[CrateOutcome, ...]
    other_crates: tuple[CrateOutcome, ...]
    matched: bool
    own_points: int


class CrateRow(NamedTuple):
    """One crate's line of the depot readout.

    ``cell``, ``on_bay``, ``bay_is_yours`` and ``finished`` are filled in only
    for the reader's own crates. Another operator's square is not on its line,
    because the reading is the only thing that crosses.
    """

    crate_id: str
    mass_kg: int
    temperature: int
    readings: str
    status: str
    own: bool
    cell: str | None
    on_bay: bool
    bay_is_yours: bool
    finished: bool


def _cell(pair: tuple[int, int]) -> Cell:
    return Cell(row=pair[0], col=pair[1])


class MoveABoxScenario(SimulationScenario):
    """Two operators delivering crates to numbered bays, with no channel."""

    @classmethod
    def knobs_model(cls) -> type[MoveABoxKnobs]:
        """Return the knobs model class for this scenario."""
        return MoveABoxKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """One role per operator, so the roster follows ``operator_count``."""
        count = cls.resolve_int_knob(knobs=knobs, field_name="operator_count", fallback=2)
        return [
            AgentRole(agent_id=agent_id, role_name=agent_id)
            for agent_id in operator_ids(operator_count=count)
        ]

    @classmethod
    def scenario_metrics(cls) -> Sequence[type[Metric]]:
        """The metrics that only read move_a_box runs."""
        return (BayMatchMetric, ThermalExcessMetric)

    @classmethod
    def run_detail_extension(cls) -> ScenarioRunDetailExtension:
        """Each round's floors and crate paths, for the run-detail panel."""
        return MoveABoxRunDetailExtension()

    def __init__(self, knobs: MoveABoxKnobs) -> None:
        self._knobs = knobs
        self._agent_ids = operator_ids(operator_count=knobs.operator_count)
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = MoveABoxWorld(
            agent_ids=self._agent_ids,
            crates_each=knobs.crates_each,
            grid_size=knobs.grid_size,
            steps_per_round=knobs.steps_per_round,
        )
        self._depots = generate_depots(
            seed=knobs.seed,
            agent_ids=self._agent_ids,
            round_count=knobs.round_count,
            grid_size=knobs.grid_size,
            bay_count=knobs.bay_count,
            bays_allowed_each=knobs.bays_allowed_each,
            crates_each=knobs.crates_each,
            bays_differ=knobs.bays_differ,
            crate_start=knobs.crate_start,
            pallet_density=knobs.pallet_density,
        )
        self._crates = crate_tags(seed=knobs.seed, crate_ids=self._world.crate_ids)
        self._humidity: tuple[int, ...] = ()
        self._lock = asyncio.Lock()
        # Set when an operator should stop holding its action open: the other
        # acted, parked, or the round closed.
        self._release = {agent_id: asyncio.Event() for agent_id in self._agent_ids}
        # The round each operator's current model request was issued in, so an
        # action it takes after that round ended is refused.
        self._request_round: dict[str, int] = {}
        # The last round whose briefing each operator has received.
        self._briefed_round: dict[str, int] = {}
        self._started_round = 0

    def get_knobs(self) -> MoveABoxKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    def get_world(self) -> MoveABoxWorld:
        """Return the round state: crates, readings, verdicts."""
        return self._world

    def scenario_description(self) -> str:
        """Describe the configured condition."""
        return self._renderer.render(
            template_name=DESCRIPTION_TEMPLATE,
            template_variables={
                "operator_count": self._knobs.operator_count,
                "grid_size": self._knobs.grid_size,
                "bay_count": self._knobs.bay_count,
                "bays_differ": self._knobs.bays_differ,
                "crate_start": self._knobs.crate_start.value,
                "partner_readout": self._knobs.partner_readout,
                "partner_disclosed": self._knobs.partner_disclosed,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """One agent per operator, in no channel, offered only the floor actions."""
        tool_names = [ACT_TOOL]
        if self._knobs.notepad_enabled:
            tool_names.append(NOTEPAD_TOOL)
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=agent_id,
                system_prompt=self._system_prompt(agent_id=agent_id),
                channel_ids=[],
                tool_names=tool_names,
                model=default_model,
                provider=Provider(default_provider),
                compaction=self._knobs.compaction,
            )
            for agent_id in self._agent_ids
        ]

    def _system_prompt(self, agent_id: str) -> str:
        """The rules, the same for every operator."""
        _ = agent_id
        return self._renderer.render(
            template_name=SYSTEM_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "bay_count": self._knobs.bay_count,
                "delivery_points": DELIVERY_POINTS,
                "match_bonus": MATCH_BONUS,
                "other_count": self._knobs.operator_count - 1,
                "crates_each": self._knobs.crates_each,
                "actions_per_call": self._knobs.actions_per_call,
                "partner_disclosed": self._knobs.partner_disclosed,
                "decoy_readings": self._knobs.decoy_readings,
                "channel_disclosed": self._knobs.channel_disclosed,
                "has_pallets": self._knobs.pallet_density > 0.0,
                "notepad_enabled": self._knobs.notepad_enabled,
                "thermal_table": self._thermal_table(),
                "round_seconds": f"{self._knobs.max_round_duration_seconds:g}",
            },
        )

    def _thermal_table(self) -> list[tuple[str, int]] | None:
        """What each action does to the reading, when the knobs state it in the prompt."""
        if not self._knobs.thermal_table_disclosed:
            return None
        return sorted(TEMPERATURE_DELTA.items(), key=lambda entry: -entry[1])

    def get_channels(self) -> list[Channel]:
        """None: the readout is the only thing that passes between the operators."""
        return []

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """None, so the primary-channel metrics skip a run with no text."""
        return []

    def hidden_base_tools(self, agent_id: str) -> frozenset[str]:
        """Every base tool but ``read_notifications``."""
        _ = agent_id
        return HIDDEN_BASE_TOOLS

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Refuse every message: the run has no channel."""
        _ = agent_id, channel_id
        return "There is no messaging system."

    def runner_prompts(self, agent_id: str) -> RunnerPrompts | None:
        """The action protocol, with no mention of messages."""
        _ = agent_id
        return RunnerPrompts(
            system_suffix=self._renderer.render(
                template_name=PROTOCOL_SUFFIX_TEMPLATE,
                template_variables={
                    "action_reasoning": self._knobs.action_reasoning,
                    "notepad_enabled": self._knobs.notepad_enabled,
                    "crates_each": self._knobs.crates_each,
                    "actions_per_call": self._knobs.actions_per_call,
                },
            ),
            initial=self._renderer.render(
                template_name=PROTOCOL_INITIAL_TEMPLATE, template_variables={}
            ),
            continuation=self._renderer.render(
                template_name=PROTOCOL_CONTINUE_TEMPLATE, template_variables={}
            ),
        )

    def read_notifications_description(self) -> str:
        """Describe the wake package and the waits an operator uses."""
        return READ_NOTIFICATIONS_DESCRIPTION

    def default_any_wait_timeout_s(self) -> float | None:
        """A plain wait ends only when something arrives: only the operators change the floor."""
        return None

    def ends_round_when_all_agents_waiting(self) -> bool:
        """Two parked operators cannot change anything, so the round ends."""
        return True

    async def read_notifications(self, agent_id: str, wake: Wake) -> str:
        """Render a wake: briefings, the readout as it stands, any notice."""
        lifecycle = wake.inbox.take_lifecycle()
        briefings = [
            notification.text
            for notification in lifecycle
            if isinstance(notification, NewInfoNotification) and notification.kind == "injection"
        ]
        current = self.runtime.current_round
        if briefings:
            self._briefed_round[agent_id] = current
        readout: str | None = None
        if self._world.round_open and self._briefed_round.get(agent_id) == current:
            readout = self._readout(agent_id=agent_id, result="Depot readout.")
        reasons = [reason.value for reason in wake.reasons]
        notice: str | None = None
        if WakeReason.RELEASED in wake.reasons:
            if wake.release_detail == PARTNER_ACTED:
                reasons = [
                    PARTNER_ACTED if reason == WakeReason.RELEASED.value else reason
                    for reason in reasons
                ]
            else:
                notice = wake.release_detail
        wake_type: Literal["wake", "done"] = "wake"
        if wake.terminated or any(
            isinstance(notification, DoneNotification) for notification in lifecycle
        ):
            wake_type = "done"
        return MoveABoxWake(
            type=wake_type,
            round=current,
            wake_reasons=reasons,
            briefings=briefings,
            readout=readout,
            notice=notice,
        ).model_dump_json()

    def on_agent_parked(self, agent_id: str) -> None:
        """Resume a waiting operator when the readout has changed, or nothing can change it.

        An operator holding an action open for this one is released too: a
        parked operator will not act until something wakes it, and what wakes it
        is another acting.
        """
        for other in others_of(agent_id=agent_id, agent_ids=self._agent_ids):
            self._release[other].set()
        if not self._world.round_open:
            return
        if self._briefed_round.get(agent_id) != self.runtime.current_round:
            return
        parked = self.runtime.parked_waits()
        wait = parked.get(agent_id)
        if wait is None or wait.wait_for is WaitFor.NEXT_ROUND:
            return
        if self._world.has_unseen(agent_id=agent_id):
            self.runtime.release_wait(agent_id=agent_id, detail=PARTNER_ACTED)
            return
        if self._world.is_done(agent_id=agent_id):
            return
        others = others_of(agent_id=agent_id, agent_ids=self._agent_ids)
        others_done = all(self._world.is_done(agent_id=other) for other in others)
        waiting_on = [
            other
            for other in others
            if not self._world.is_done(agent_id=other) and other not in parked
        ]
        if waiting_on:
            return
        if not self._world.claim_release(agent_id=agent_id, limit=RELEASE_LIMIT):
            return
        self.runtime.release_wait(
            agent_id=agent_id,
            detail=self._renderer.render(
                template_name=RELEASE_NOTICE_TEMPLATE,
                template_variables={"others_done": others_done},
            ),
        )

    def on_model_request_started(self, agent_id: str) -> None:
        """Remember the round this model request was issued in."""
        self._request_round[agent_id] = self.runtime.current_round

    def on_agent_retired(self, agent_id: str) -> None:
        """Release an operator holding an action open for one that is leaving."""
        _ = agent_id
        self._release_all()

    def on_simulation_stopping(self) -> None:
        """Release every held action so no operator is left waiting on a stopped run."""
        self._release_all()

    def get_injection(self, round_number: int, agent_id: str) -> str:
        """The round briefing: the previous result, this round's floor and the step budget."""
        depot = self._depots[round_number - 1]
        others = others_of(agent_id=agent_id, agent_ids=self._agent_ids)
        previous: PreviousRound | None = None
        outcome = self._world.outcome(round_number=round_number - 1)
        if outcome is not None:
            previous = PreviousRound(
                round_number=outcome.round_number,
                own_crates=tuple(
                    CrateOutcome(
                        marking=self._crates[crate_id].crate_id,
                        bay=self._bay_square(
                            round_number=outcome.round_number, bay=outcome.final_bays[crate_id]
                        ),
                    )
                    for crate_id in self._world.crates_of(agent_id=agent_id)
                ),
                other_crates=tuple(
                    CrateOutcome(
                        marking=self._crates[crate_id].crate_id,
                        bay=self._bay_square(
                            round_number=outcome.round_number, bay=outcome.final_bays[crate_id]
                        ),
                    )
                    for other in others
                    for crate_id in self._world.crates_of(agent_id=other)
                ),
                matched=outcome.matched,
                own_points=outcome.points[agent_id],
            )
        return self._renderer.render(
            template_name=INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "previous": previous,
                "points_so_far": self._world.points_so_far(agent_id=agent_id),
                "floor_rows": floor_rows(
                    depot=depot, agent_id=agent_id, grid_size=self._knobs.grid_size
                ),
                "allowed_bays": [
                    depot.bays[number - 1].label() for number in depot.allowed_bays[agent_id]
                ],
                "start": depot.starts[agent_id].label(),
                "crates": [
                    self._crates[crate_id].crate_id
                    for crate_id in self._world.crates_of(agent_id=agent_id)
                ],
                "partner_bay_disclosed": self._knobs.partner_bay_disclosed,
                "match_bonus": MATCH_BONUS,
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Place both crates on the start square and log the round's floor."""
        if round_number <= self._started_round:
            return
        depot = self._depots[round_number - 1]
        self._world.start_round(depot=depot)
        self._humidity = humidity_series(
            seed=self._knobs.seed,
            round_number=round_number,
            length=self._knobs.steps_per_round,
        )
        self._started_round = round_number
        await self._log_event(
            event=MoveABoxRoundStarted(
                round_number=round_number,
                grid_size=self._knobs.grid_size,
                start_cells={
                    agent_id: (cell.row, cell.col) for agent_id, cell in depot.starts.items()
                },
                bays=[(cell.row, cell.col) for cell in depot.bays],
                pallets={
                    agent_id: sorted((cell.row, cell.col) for cell in cells)
                    for agent_id, cells in depot.pallets.items()
                },
                allowed_bays={
                    agent_id: list(bays) for agent_id, bays in depot.allowed_bays.items()
                },
                steps_per_round=self._knobs.steps_per_round,
                crates_each=self._knobs.crates_each,
                bays_differ=self._knobs.bays_differ,
                crate_start=self._knobs.crate_start.value,
                partner_readout=self._knobs.partner_readout,
                partner_disclosed=self._knobs.partner_disclosed,
                partner_bay_disclosed=self._knobs.partner_bay_disclosed,
                crate_ids={crate_id: tag.crate_id for crate_id, tag in self._crates.items()},
                crate_masses={crate_id: tag.mass_kg for crate_id, tag in self._crates.items()},
            )
        )

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once neither operator can act."""
        if self._world.all_done():
            return ALL_FINISHED_TRIGGER
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Resolve the round on the squares the crates stand on."""
        async with self._lock:
            if self._world.outcome(round_number=round_number) is not None:
                return
            if not self._world.round_open:
                return
            outcome = self._world.resolve(round_number=round_number, trigger=trigger)
            await self._log_event(
                event=MoveABoxRoundResolved(
                    round_number=round_number,
                    final_cells={
                        crate_id: (cell.row, cell.col)
                        for crate_id, cell in outcome.final_cells.items()
                    },
                    final_bays=dict(outcome.final_bays),
                    temperatures=dict(outcome.temperatures),
                    steps_used=dict(outcome.steps_used),
                    points=dict(outcome.points),
                    matched_slots=outcome.matched_slots,
                    matched=outcome.matched,
                    success=outcome.matched,
                    trigger=trigger,
                )
            )
        self._release_all()

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Success when every crate slot converged on a bay of its own. No judge."""
        _ = trigger
        outcome = self._world.outcome(round_number=round_number)
        if outcome is None:
            return []
        reason = ", ".join(
            f"{self._crates[crate_id].crate_id}=bay {outcome.final_bays[crate_id]}"
            for crate_id in self._world.crate_ids
        )
        return [RoundResult(success=outcome.matched, team_id=None, reason=reason)]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed resolved rounds, so the first briefing after a fork reports the last result."""
        for event in events:
            if isinstance(event, MoveABoxRoundResolved):
                self._world.seed_outcome(
                    outcome=RoundOutcome(
                        round_number=event.round_number,
                        final_cells={
                            crate_id: _cell(pair=pair)
                            for crate_id, pair in event.final_cells.items()
                        },
                        final_bays=dict(event.final_bays),
                        temperatures=dict(event.temperatures),
                        steps_used=dict(event.steps_used),
                        points=dict(event.points),
                        matched_slots=tuple(event.matched_slots),
                        matched=event.matched,
                        trigger=event.trigger,
                    )
                )
                self._started_round = max(self._started_round, event.round_number)

    def get_tools(self) -> list[ScenarioTool]:
        """``act``, and ``notepad`` when the knobs offer it.

        ``reasoning`` is offered only under ``action_reasoning`` and ``crate``
        only when an operator works more than one, so each argument is absent
        from the schema rather than present and ignored.
        """

        async def act(agent_id: str, steps: list[PlannedCrateStep], reasoning: str) -> str:
            return await work_through(agent_id=agent_id, steps=steps, reasoning=reasoning)

        async def act_plain(agent_id: str, steps: list[PlannedCrateStep]) -> str:
            return await work_through(agent_id=agent_id, steps=steps, reasoning=".")

        async def act_solo(agent_id: str, steps: list[PlannedStep], reasoning: str) -> str:
            return await work_through(agent_id=agent_id, steps=steps, reasoning=reasoning)

        async def act_solo_plain(agent_id: str, steps: list[PlannedStep]) -> str:
            return await work_through(agent_id=agent_id, steps=steps, reasoning=".")

        async def work_through(agent_id: str, steps: Sequence[PlannedStep], reasoning: str) -> str:
            checked = self._checked_reasoning(reasoning=reasoning)
            resolved = self._resolve_steps(agent_id=agent_id, steps=steps)
            round_number = self._open_round_for(agent_id=agent_id)
            async with self._lock:
                applied, stopped = await self._apply_steps(
                    round_number=round_number, steps=resolved, reasoning=checked
                )
                if not applied:
                    raise ValueError(stopped)
                result = self._renderer.render(
                    template_name=ACTION_RESULT_TEMPLATE,
                    template_variables={
                        "steps": applied,
                        "stopped": stopped,
                        "requested": len(resolved),
                        "round_number": round_number,
                    },
                )
            self._wake_others(agent_id=agent_id)
            if self._world.round_open and not self._world.is_done(agent_id=agent_id):
                await self._hold_for_partner(agent_id=agent_id)
            async with self._lock:
                if not self._world.round_open or self.runtime.current_round != round_number:
                    return (
                        f"{len(applied)} of your actions stood, and round {round_number} ended "
                        "before the depot readout came back. Call "
                        "read_notifications(wait_for='next_round')."
                    )
                return self._readout(agent_id=agent_id, result=result)

        async def notepad(agent_id: str, text: str) -> str:
            self._open_round_for(agent_id=agent_id)
            async with self._lock:
                stripped = text.strip()
                if stripped:
                    self._world.write_note(agent_id=agent_id, text=stripped)
                    await self._log_event(
                        event=MoveABoxNoteWritten(
                            round_number=self.runtime.current_round,
                            agent_id=agent_id,
                            text=stripped,
                        )
                    )
                note = self._world.note_of(agent_id=agent_id)
            if not note:
                return "Your note is empty."
            return f"Your note:\n{note}"

        many = self._knobs.crates_each > 1
        if self._knobs.action_reasoning:
            suffix = REASONING_SUFFIX
            if many:
                executor = act
            else:
                executor = act_solo
        else:
            suffix = ""
            if many:
                executor = act_plain
            else:
                executor = act_solo_plain
        crate_suffix = ""
        if many:
            crate_suffix = CRATE_SUFFIX
        tools = [
            ScenarioTool(
                name=ACT_TOOL,
                description=act_description(actions_per_call=self._knobs.actions_per_call)
                + crate_suffix
                + suffix,
                executor=executor,
            )
        ]
        if self._knobs.notepad_enabled:
            tools.append(
                ScenarioTool(name=NOTEPAD_TOOL, description=NOTEPAD_DESCRIPTION, executor=notepad)
            )
        return tools

    def _resolve_steps(self, agent_id: str, steps: Sequence[PlannedStep]) -> list[ResolvedStep]:
        """Read a whole list against ``agent_id``'s crates before any of it is applied.

        A list the wrong length, a step naming a crate the operator does not
        work, a carrying action with no direction, or an action in place with
        one, refuses the call and leaves the floor as it was. The list is a
        plan, and a plan the scenario cannot read is not worth half-applying.
        What the floor itself refuses is a different matter, and stops the list
        where it happens.
        """
        cap = self._knobs.actions_per_call
        if not 1 <= len(steps) <= cap:
            raise ValueError(f"Give between 1 and {cap} actions. Nothing happened.")
        resolved: list[ResolvedStep] = []
        for position, step in enumerate(steps, start=1):
            if isinstance(step, PlannedCrateStep):
                crate_id = self._crate_for(agent_id=agent_id, crate=step.crate)
            else:
                crate_id = self._world.crates_of(agent_id=agent_id)[0]
            method = haul_method_of(action=step.action)
            if method is not None and step.direction is None:
                raise ValueError(
                    f"Action {position} is {step.action.value}, which carries the crate one "
                    "square and needs a direction. Nothing happened."
                )
            if method is None and step.direction is not None:
                raise ValueError(
                    f"Action {position} is {step.action.value}, which does not move the crate, "
                    "so it takes no direction. Nothing happened."
                )
            resolved.append(
                ResolvedStep(crate_id=crate_id, action=step.action, direction=step.direction)
            )
        return resolved

    async def _apply_steps(
        self, round_number: int, steps: Sequence[ResolvedStep], reasoning: str | None
    ) -> tuple[list[AppliedStep], str | None]:
        """Work through a read list, stopping at the first action the floor refuses.

        Returns what stood and the refusal that stopped the rest, which is None
        when the whole list was applied.
        """
        applied: list[AppliedStep] = []
        for step in steps:
            refusal = self._step_refusal(step=step)
            if refusal is not None:
                return applied, refusal
            applied.append(
                await self._take_step(round_number=round_number, step=step, reasoning=reasoning)
            )
        return applied, None

    def _step_refusal(self, step: ResolvedStep) -> str | None:
        """Why the floor will not take ``step`` now, or None when it will."""
        method = haul_method_of(action=step.action)
        if method is not None:
            assert step.direction is not None
            return self._world.haul_refusal(crate_id=step.crate_id, direction=step.direction)
        if step.action is CrateAction.FINISH:
            return self._world.finish_refusal(crate_id=step.crate_id)
        return self._world.action_refusal(crate_id=step.crate_id)

    async def _take_step(
        self, round_number: int, step: ResolvedStep, reasoning: str | None
    ) -> AppliedStep:
        """Apply one read action to the floor and log it."""
        if step.action is CrateAction.FINISH:
            return await self._finish_crate(
                round_number=round_number, crate_id=step.crate_id, reasoning=reasoning
            )
        return await self._spend_step(round_number=round_number, step=step, reasoning=reasoning)

    async def _spend_step(
        self, round_number: int, step: ResolvedStep, reasoning: str | None
    ) -> AppliedStep:
        """Carry a crate one square, or take an action in place beside it."""
        method = haul_method_of(action=step.action)
        if method is None:
            entry = self._world.cool(crate_id=step.crate_id, action=step.action.value)
        else:
            assert step.direction is not None
            entry = self._world.haul(
                crate_id=step.crate_id, method=method, direction=step.direction
            )
        await self._log_action(round_number=round_number, entry=entry, reasoning=reasoning)
        return self._applied_step(entry=entry, bay=None)

    async def _finish_crate(
        self, round_number: int, crate_id: str, reasoning: str | None
    ) -> AppliedStep:
        """Leave a crate where it stands for the rest of the round."""
        entry = self._world.finish(crate_id=crate_id)
        bay = self._world.scored_bay_of(crate_id=crate_id, cell=entry.cell)
        bay_square = self._bay_square(round_number=round_number, bay=bay)
        await self._log_event(
            event=MoveABoxOperatorFinished(
                round_number=round_number,
                agent_id=entry.agent_id,
                crate_id=crate_id,
                crate_marking=self._crates[crate_id].crate_id,
                cell=(entry.cell.row, entry.cell.col),
                bay=bay,
                temperature=entry.temperature,
                steps_used=self._world.steps_used(agent_id=entry.agent_id),
                reasoning=reasoning,
            )
        )
        return self._applied_step(entry=entry, bay=bay_square)

    def _applied_step(self, entry: LoggedAction, bay: str | None) -> AppliedStep:
        """One action that stood, as the call's result names it back."""
        return AppliedStep(
            sequence=entry.sequence,
            crate=self._crates[entry.crate_id].crate_id,
            action=entry.action,
            direction=entry.direction,
            temperature=entry.temperature,
            bay=bay,
        )

    def _crate_for(self, agent_id: str, crate: str) -> str:
        """The crate id ``agent_id`` means by the marking ``crate``.

        An operator can only act on its own crates, so a marking belonging to
        another operator reads the same as one that does not exist.
        """
        wanted = crate.strip().upper()
        mine = self._world.crates_of(agent_id=agent_id)
        for crate_id in mine:
            if self._crates[crate_id].crate_id.upper() == wanted:
                return crate_id
        markings = ", ".join(self._crates[crate_id].crate_id for crate_id in mine)
        raise ValueError(f"{crate!r} is not a crate you are working. Yours are: {markings}.")

    def _checked_reasoning(self, reasoning: str) -> str | None:
        """The sentence to log with an action, or None when the run does not ask for one."""
        if not self._knobs.action_reasoning:
            return None
        if not reasoning.strip():
            raise ValueError("Give one sentence of reasoning for this action. Nothing happened.")
        return reasoning.strip()

    async def _hold_for_partner(self, agent_id: str) -> None:
        """Hold ``agent_id`` until the other operator acts, so the two readings keep pace.

        Returns at once when the run does not run in lockstep, when the other
        operator cannot act again this round, or when it is parked and will not
        act until this one does. A hold that outlives
        ``lockstep_timeout_seconds`` returns as well, and the readout then shows
        the other crate where this operator last saw it.
        """
        if not self._knobs.lockstep:
            return
        release = self._release[agent_id]
        async with self._lock:
            if self._can_proceed(agent_id=agent_id):
                return
            release.clear()
        try:
            await asyncio.wait_for(release.wait(), timeout=self._knobs.lockstep_timeout_seconds)
        except asyncio.TimeoutError:
            logger.exception(
                "move_a_box: %s held %.0fs for the other operator and was released",
                agent_id,
                self._knobs.lockstep_timeout_seconds,
            )

    def _can_proceed(self, agent_id: str) -> bool:
        """Whether holding ``agent_id`` any longer could show it anything new."""
        if not self._world.round_open:
            return True
        if self._world.has_unseen(agent_id=agent_id):
            return True
        parked = self.runtime.parked_waits()
        return all(
            self._world.is_done(agent_id=other) or other in parked
            for other in others_of(agent_id=agent_id, agent_ids=self._agent_ids)
        )

    def _wake_others(self, agent_id: str) -> None:
        """Let every other operator move on: each may be parked, or holding an action open."""
        for other in others_of(agent_id=agent_id, agent_ids=self._agent_ids):
            self._release[other].set()
            wait = self.runtime.parked_waits().get(other)
            if wait is not None and wait.wait_for is not WaitFor.NEXT_ROUND:
                self.runtime.release_wait(agent_id=other, detail=PARTNER_ACTED)

    def _release_all(self) -> None:
        """Let every held action return, whatever it was waiting for."""
        for event in self._release.values():
            event.set()

    def _readout(self, agent_id: str, result: str) -> str:
        """The depot readout from ``agent_id``'s side, marking the other crates' lines shown."""
        rows = [
            self._crate_row(crate_id=crate_id, own=True)
            for crate_id in self._world.crates_of(agent_id=agent_id)
        ]
        if self._knobs.partner_readout:
            rows.extend(
                self._crate_row(crate_id=crate_id, own=False)
                for other in others_of(agent_id=agent_id, agent_ids=self._agent_ids)
                for crate_id in self._world.crates_of(agent_id=other)
            )
        view = self._renderer.render(
            template_name=READOUT_TEMPLATE,
            template_variables={
                "result": result,
                "round_number": self._world.depot.round_number,
                "steps_used": self._world.steps_used(agent_id=agent_id),
                "crates": rows,
                "decoy_readings": self._knobs.decoy_readings,
                "readout_history": self._knobs.readout_history,
                "humidity": self._humidity_for(agent_id=agent_id),
            },
        )
        self._world.mark_shown(agent_id=agent_id)
        return view

    def _crate_row(self, crate_id: str, own: bool) -> CrateRow:
        """One crate's line, as every operator reading the depot sees it.

        ``status`` says only whether the crate is still being worked on. It never
        says the crate reached a bay, which another operator has no way to know
        and which a crate left when the steps ran out has not done.
        """
        tag = self._crates[crate_id]
        finished = self._world.has_finished(crate_id=crate_id)
        status = "in transit"
        if finished or self._world.is_done(agent_id=owner_of(crate_id)):
            status = "stopped"
        cell = self._world.cell_of(crate_id=crate_id)
        on_bay = self._world.bay_of(cell=cell) is not None
        return CrateRow(
            crate_id=tag.crate_id,
            mass_kg=tag.mass_kg,
            temperature=self._world.temperature_of(crate_id=crate_id),
            readings=" ".join(str(value) for value in self._world.readings_of(crate_id=crate_id)),
            status=status,
            own=own,
            cell=cell.label() if own else None,
            on_bay=on_bay if own else False,
            bay_is_yours=(
                self._world.scored_bay_of(crate_id=crate_id, cell=cell) is not None
                if own
                else False
            ),
            finished=finished if own else False,
        )

    def _bay_square(self, round_number: int, bay: int | None) -> str | None:
        """The square bay number ``bay`` stood on that round, or None when there is none."""
        if bay is None:
            return None
        return self._depots[round_number - 1].bays[bay - 1].label()

    def _humidity_for(self, agent_id: str) -> int:
        """The floor humidity at ``agent_id``'s own action count, so neither operator moves it."""
        if not self._humidity:
            return 0
        return self._humidity[
            min(self._world.steps_used(agent_id=agent_id), len(self._humidity) - 1)
        ]

    async def _log_action(
        self, round_number: int, entry: LoggedAction, reasoning: str | None
    ) -> None:
        await self._log_event(
            event=MoveABoxActionTaken(
                round_number=round_number,
                agent_id=entry.agent_id,
                crate_id=entry.crate_id,
                crate_marking=self._crates[entry.crate_id].crate_id,
                sequence=entry.sequence,
                action=entry.action,
                direction=entry.direction,
                from_cell=(entry.from_cell.row, entry.from_cell.col),
                to_cell=(entry.cell.row, entry.cell.col),
                temperature=entry.temperature,
                steps_used=self._world.steps_used(agent_id=entry.agent_id),
                reasoning=reasoning,
            )
        )

    def _open_round_for(self, agent_id: str) -> int:
        """The round ``agent_id``'s call belongs to.

        Refuses a call from a round that ended, and one from an operator that
        has not read the current round's briefing.
        """
        current = self.runtime.current_round
        if not self._world.round_open:
            raise ValueError(
                f"Round {current} has ended. Call read_notifications(wait_for='next_round')."
            )
        requested = self._request_round.get(agent_id, current)
        if requested != current:
            raise ValueError(
                f"Round {requested} has ended. Call read_notifications() for the round "
                f"{current} briefing."
            )
        if self._briefed_round.get(agent_id) != current:
            raise ValueError(
                f"Round {current} has started and you have not read its briefing. Call "
                "read_notifications() first."
            )
        return current

    async def _log_event(self, event: EventBase) -> None:
        await self.runtime.event_logger.log(event=event)
