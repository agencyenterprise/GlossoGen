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
    ACTION_RESULT_TEMPLATE,
    AGENT_IDS,
    BOTH_FINISHED_TRIGGER,
    DELIVERY_POINTS,
    DESCRIPTION_TEMPLATE,
    FINISH_TOOL,
    HAUL_TOOL,
    HIDDEN_BASE_TOOLS,
    INJECTION_TEMPLATE,
    MATCH_BONUS,
    NOTEPAD_TOOL,
    PACK_ICE_TOOL,
    PARTNER_OF,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    READOUT_TEMPLATE,
    RELEASE_NOTICE_TEMPLATE,
    STAND_BY_TOOL,
    SYSTEM_TEMPLATE,
    TEMPERATURE_DELTA,
    Direction,
    HaulMethod,
)
from glossogen.scenarios.move_a_box.knobs import MoveABoxKnobs
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

HAUL_DESCRIPTION = (
    "Carry the crate one square, in the direction you give, by the method you give: drag it, "
    "put it on a sled, or put it on a cart. Each method covers one square. Returns the depot "
    "readout."
)
STAND_BY_DESCRIPTION = "Stand by beside the crate without moving it. Returns the depot readout."
PACK_ICE_DESCRIPTION = "Pack ice around the crate without moving it. Returns the depot readout."
FINISH_DESCRIPTION = (
    "Leave the crate where it stands for the rest of the round. Its square cannot change "
    "after this. Returns the depot readout."
)
NOTEPAD_DESCRIPTION = (
    "Replace your private note with the text you give, and read it back. Nobody else ever "
    "sees it. Call it with an empty text to read the note you have."
)
REASONING_SUFFIX = " reasoning is one sentence on why you are doing this; nobody else sees it."
READ_NOTIFICATIONS_DESCRIPTION = (
    "read_notifications() returns your round briefing at startup and after a round changes; "
    "during a round it waits until the depot readout changes, then returns it. "
    "read_notifications(wait_for='next_round') declares you are done with this round and waits "
    "for the next briefing. The result is a wake package: the reasons, any briefings, the "
    "readout, and a notice when the wait was cut short; type done ends the run. Must be the "
    "only tool call in its response."
)


class PreviousRound(NamedTuple):
    """The previous round from one operator's side, as the briefing reads it.

    ``own_bay`` and ``partner_bay`` are the squares the crates were left on, or
    None for a crate that reached no bay it could score. A bay carries no number
    an operator could name: it is the square it stands on.
    """

    round_number: int
    own_bay: str | None
    partner_bay: str | None
    matched: bool
    own_points: int


class CrateRow(NamedTuple):
    """One crate's line of the depot readout."""

    crate_id: str
    mass_kg: int
    temperature: int
    readings: str
    status: str
    own: bool


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
        """The two operators. The roster never varies with the knobs."""
        _ = knobs
        return [AgentRole(agent_id=agent_id, role_name=agent_id) for agent_id in AGENT_IDS]

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
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = MoveABoxWorld(
            grid_size=knobs.grid_size, steps_per_round=knobs.steps_per_round
        )
        self._depots = generate_depots(
            seed=knobs.seed,
            round_count=knobs.round_count,
            grid_size=knobs.grid_size,
            bay_count=knobs.bay_count,
            bays_allowed_each=knobs.bays_allowed_each,
            bays_differ=knobs.bays_differ,
            crate_start=knobs.crate_start,
            pallet_density=knobs.pallet_density,
        )
        self._crates = crate_tags(seed=knobs.seed)
        self._humidity: tuple[int, ...] = ()
        self._lock = asyncio.Lock()
        # Set when an operator should stop holding its action open: the other
        # acted, parked, or the round closed.
        self._release = {agent_id: asyncio.Event() for agent_id in AGENT_IDS}
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
        tool_names = [HAUL_TOOL, STAND_BY_TOOL, PACK_ICE_TOOL, FINISH_TOOL]
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
            for agent_id in AGENT_IDS
        ]

    def _system_prompt(self, agent_id: str) -> str:
        """The rules, the same for both operators."""
        _ = agent_id
        return self._renderer.render(
            template_name=SYSTEM_TEMPLATE,
            template_variables={
                "grid_size": self._knobs.grid_size,
                "bay_count": self._knobs.bay_count,
                "delivery_points": DELIVERY_POINTS,
                "match_bonus": MATCH_BONUS,
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
        is the other acting.
        """
        self._release[PARTNER_OF[agent_id]].set()
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
        partner = PARTNER_OF[agent_id]
        partner_done = self._world.is_done(agent_id=partner)
        if not partner_done and partner not in parked:
            return
        if not self._world.claim_release(agent_id=agent_id, limit=RELEASE_LIMIT):
            return
        self.runtime.release_wait(
            agent_id=agent_id,
            detail=self._renderer.render(
                template_name=RELEASE_NOTICE_TEMPLATE,
                template_variables={"partner_done": partner_done},
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
        partner = PARTNER_OF[agent_id]
        previous: PreviousRound | None = None
        outcome = self._world.outcome(round_number=round_number - 1)
        if outcome is not None:
            previous = PreviousRound(
                round_number=outcome.round_number,
                own_bay=self._bay_square(
                    round_number=outcome.round_number, bay=outcome.final_bays[agent_id]
                ),
                partner_bay=self._bay_square(
                    round_number=outcome.round_number, bay=outcome.final_bays[partner]
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
                bays_differ=self._knobs.bays_differ,
                crate_start=self._knobs.crate_start.value,
                partner_readout=self._knobs.partner_readout,
                partner_disclosed=self._knobs.partner_disclosed,
                partner_bay_disclosed=self._knobs.partner_bay_disclosed,
                crate_ids={agent_id: tag.crate_id for agent_id, tag in self._crates.items()},
                crate_masses={agent_id: tag.mass_kg for agent_id, tag in self._crates.items()},
            )
        )

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once neither operator can act."""
        if self._world.both_done():
            return BOTH_FINISHED_TRIGGER
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
                        agent_id: (cell.row, cell.col)
                        for agent_id, cell in outcome.final_cells.items()
                    },
                    final_bays=dict(outcome.final_bays),
                    temperatures=dict(outcome.temperatures),
                    steps_used=dict(outcome.steps_used),
                    points=dict(outcome.points),
                    matched=outcome.matched,
                    success=outcome.matched,
                    trigger=trigger,
                )
            )
        self._release_all()

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Success when both crates stand on one bay. No judge."""
        _ = trigger
        outcome = self._world.outcome(round_number=round_number)
        if outcome is None:
            return []
        reason = ", ".join(
            f"{agent_id}=bay {outcome.final_bays[agent_id]}" for agent_id in AGENT_IDS
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
                            agent_id: _cell(pair=pair)
                            for agent_id, pair in event.final_cells.items()
                        },
                        final_bays=dict(event.final_bays),
                        temperatures=dict(event.temperatures),
                        steps_used=dict(event.steps_used),
                        points=dict(event.points),
                        matched=event.matched,
                        trigger=event.trigger,
                    )
                )
                self._started_round = max(self._started_round, event.round_number)

    def get_tools(self) -> list[ScenarioTool]:
        """The floor actions; under ``action_reasoning`` each takes a ``reasoning``."""

        async def haul(
            agent_id: str, method: HaulMethod, direction: Direction, reasoning: str
        ) -> str:
            checked = self._checked_reasoning(reasoning=reasoning)
            round_number = self._open_round_for(agent_id=agent_id)
            async with self._lock:
                entry = self._world.haul(agent_id=agent_id, method=method, direction=direction)
                await self._log_action(round_number=round_number, entry=entry, reasoning=checked)
            return await self._after_action(
                agent_id=agent_id, entry=entry, round_number=round_number
            )

        async def stand_by(agent_id: str, reasoning: str) -> str:
            return await cooling_action(
                agent_id=agent_id, action=STAND_BY_TOOL, reasoning=reasoning
            )

        async def pack_ice(agent_id: str, reasoning: str) -> str:
            return await cooling_action(
                agent_id=agent_id, action=PACK_ICE_TOOL, reasoning=reasoning
            )

        async def cooling_action(agent_id: str, action: str, reasoning: str) -> str:
            checked = self._checked_reasoning(reasoning=reasoning)
            round_number = self._open_round_for(agent_id=agent_id)
            async with self._lock:
                entry = self._world.cool(agent_id=agent_id, action=action)
                await self._log_action(round_number=round_number, entry=entry, reasoning=checked)
            return await self._after_action(
                agent_id=agent_id, entry=entry, round_number=round_number
            )

        async def finish(agent_id: str, reasoning: str) -> str:
            checked = self._checked_reasoning(reasoning=reasoning)
            round_number = self._open_round_for(agent_id=agent_id)
            async with self._lock:
                entry = self._world.finish(agent_id=agent_id)
                bay = self._world.scored_bay_of(agent_id=agent_id, cell=entry.cell)
                bay_square = self._bay_square(round_number=round_number, bay=bay)
                await self._log_event(
                    event=MoveABoxOperatorFinished(
                        round_number=round_number,
                        agent_id=agent_id,
                        cell=(entry.cell.row, entry.cell.col),
                        bay=bay,
                        temperature=entry.temperature,
                        steps_used=self._world.steps_used(agent_id=agent_id),
                        reasoning=checked,
                    )
                )
                view = self._readout(
                    agent_id=agent_id,
                    result=self._renderer.render(
                        template_name=ACTION_RESULT_TEMPLATE,
                        template_variables={
                            "action": FINISH_TOOL,
                            "direction": None,
                            "round_number": round_number,
                            "bay": bay_square,
                        },
                    ),
                )
            self._wake_partner(agent_id=agent_id)
            return view

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

        async def haul_plain(agent_id: str, method: HaulMethod, direction: Direction) -> str:
            return await haul(agent_id=agent_id, method=method, direction=direction, reasoning=".")

        async def stand_by_plain(agent_id: str) -> str:
            return await stand_by(agent_id=agent_id, reasoning=".")

        async def pack_ice_plain(agent_id: str) -> str:
            return await pack_ice(agent_id=agent_id, reasoning=".")

        async def finish_plain(agent_id: str) -> str:
            return await finish(agent_id=agent_id, reasoning=".")

        if self._knobs.action_reasoning:
            tools = [
                ScenarioTool(
                    name=HAUL_TOOL,
                    description=HAUL_DESCRIPTION + REASONING_SUFFIX,
                    executor=haul,
                ),
                ScenarioTool(
                    name=STAND_BY_TOOL,
                    description=STAND_BY_DESCRIPTION + REASONING_SUFFIX,
                    executor=stand_by,
                ),
                ScenarioTool(
                    name=PACK_ICE_TOOL,
                    description=PACK_ICE_DESCRIPTION + REASONING_SUFFIX,
                    executor=pack_ice,
                ),
                ScenarioTool(
                    name=FINISH_TOOL,
                    description=FINISH_DESCRIPTION + REASONING_SUFFIX,
                    executor=finish,
                ),
            ]
        else:
            tools = [
                ScenarioTool(name=HAUL_TOOL, description=HAUL_DESCRIPTION, executor=haul_plain),
                ScenarioTool(
                    name=STAND_BY_TOOL,
                    description=STAND_BY_DESCRIPTION,
                    executor=stand_by_plain,
                ),
                ScenarioTool(
                    name=PACK_ICE_TOOL,
                    description=PACK_ICE_DESCRIPTION,
                    executor=pack_ice_plain,
                ),
                ScenarioTool(
                    name=FINISH_TOOL, description=FINISH_DESCRIPTION, executor=finish_plain
                ),
            ]
        if self._knobs.notepad_enabled:
            tools.append(
                ScenarioTool(name=NOTEPAD_TOOL, description=NOTEPAD_DESCRIPTION, executor=notepad)
            )
        return tools

    def _checked_reasoning(self, reasoning: str) -> str | None:
        """The sentence to log with an action, or None when the run does not ask for one."""
        if not self._knobs.action_reasoning:
            return None
        if not reasoning.strip():
            raise ValueError("Give one sentence of reasoning for this action. Nothing happened.")
        return reasoning.strip()

    async def _after_action(self, agent_id: str, entry: LoggedAction, round_number: int) -> str:
        """Wake the other operator, hold this one until it acts, then render the readout.

        The hold can outlive the round it belongs to, so the readout is rendered
        only while that round is still the open one. Past it there is no state to
        show and the operator is sent to its next briefing.
        """
        self._wake_partner(agent_id=agent_id)
        await self._hold_for_partner(agent_id=agent_id)
        async with self._lock:
            if not self._world.round_open or self.runtime.current_round != round_number:
                return (
                    f"Your {entry.action} stood, and round {round_number} ended before the "
                    "depot readout came back. Call read_notifications(wait_for='next_round')."
                )
            return self._readout(
                agent_id=agent_id,
                result=self._renderer.render(
                    template_name=ACTION_RESULT_TEMPLATE,
                    template_variables={
                        "action": entry.action,
                        "direction": entry.direction,
                        "round_number": round_number,
                        "bay": None,
                    },
                ),
            )

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
        partner = PARTNER_OF[agent_id]
        if self._world.is_done(agent_id=partner):
            return True
        return partner in self.runtime.parked_waits()

    def _wake_partner(self, agent_id: str) -> None:
        """Let the other operator move on: it may be parked, or holding an action open."""
        partner = PARTNER_OF[agent_id]
        self._release[partner].set()
        wait = self.runtime.parked_waits().get(partner)
        if wait is not None and wait.wait_for is not WaitFor.NEXT_ROUND:
            self.runtime.release_wait(agent_id=partner, detail=PARTNER_ACTED)

    def _release_all(self) -> None:
        """Let every held action return, whatever it was waiting for."""
        for event in self._release.values():
            event.set()

    def _readout(self, agent_id: str, result: str) -> str:
        """The depot readout from ``agent_id``'s side, marking the other crate's line shown."""
        rows = [self._crate_row(agent_id=agent_id, own=True)]
        if self._knobs.partner_readout:
            rows.append(self._crate_row(agent_id=PARTNER_OF[agent_id], own=False))
        cell = self._world.cell_of(agent_id=agent_id)
        view = self._renderer.render(
            template_name=READOUT_TEMPLATE,
            template_variables={
                "result": result,
                "round_number": self._world.depot.round_number,
                "cell": cell.label(),
                "bay": self._world.bay_of(cell=cell) is not None,
                "bay_is_yours": self._world.scored_bay_of(agent_id=agent_id, cell=cell) is not None,
                "steps_used": self._world.steps_used(agent_id=agent_id),
                "finished": self._world.has_finished(agent_id=agent_id),
                "crates": rows,
                "decoy_readings": self._knobs.decoy_readings,
                "readout_history": self._knobs.readout_history,
                "humidity": self._humidity_for(agent_id=agent_id),
            },
        )
        self._world.mark_shown(agent_id=agent_id)
        return view

    def _crate_row(self, agent_id: str, own: bool) -> CrateRow:
        """One crate's line, as every operator reading the depot sees it.

        ``status`` says only whether the crate is still being worked on. It never
        says the crate reached a bay, which the other operator has no way to know
        and which an operator out of steps has not done.
        """
        tag = self._crates[agent_id]
        status = "in transit"
        if self._world.is_done(agent_id=agent_id):
            status = "stopped"
        return CrateRow(
            crate_id=tag.crate_id,
            mass_kg=tag.mass_kg,
            temperature=self._world.temperature_of(agent_id=agent_id),
            readings=" ".join(str(value) for value in self._world.readings_of(agent_id=agent_id)),
            status=status,
            own=own,
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
