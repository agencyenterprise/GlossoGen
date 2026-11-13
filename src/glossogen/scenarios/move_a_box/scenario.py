"""Two depot operators who can affect each other only through a crate's temperature.

Each operator moves a crate across its own floor to one of the loading bays. The
depot assigns each a different list of bays with one bay on both, so the bay
they can agree on is one neither can name alone. A bay is named by its square,
the same on every floor, or by its symbol or letter, with each floor's bays on
squares of their own. The depot readout
returns every crate's reading after every action, and how the crate is carried
decides what its reading does. Nothing in the task says the reading means
anything.

The geometry is in ``depot``, the round state in ``world``. This module wires
them to the platform.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple

from glossogen.model_catalog.provider_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event_base import EventBase
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.models.wait_for import WaitFor
from glossogen.runtime.virtual_clock import VirtualClock, VirtualClockConfig
from glossogen.scenario_contract.activity_notification import DoneNotification, NewInfoNotification
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.notification_delivery import Wake
from glossogen.scenario_contract.parked_wait import WakeReason
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.registration import scenario
from glossogen.scenario_contract.run_detail_extension import ScenarioRunDetailExtension
from glossogen.scenario_contract.scenario_base import PrimaryChannel, RoundResult
from glossogen.scenario_contract.scenario_tool import ScenarioTool
from glossogen.scenarios.move_a_box.clock_charge import charged_output_tokens
from glossogen.scenarios.move_a_box.depot import (
    Bay,
    Cell,
    RoundDepot,
    TargetLayout,
    crate_tags,
    draw_next_target,
    floor_rows,
    generate_depots,
    humidity_series,
    landmark_floor_rows,
)
from glossogen.scenarios.move_a_box.evaluation.bay_match_metric import BayMatchMetric
from glossogen.scenarios.move_a_box.evaluation.thermal_excess_metric import ThermalExcessMetric
from glossogen.scenarios.move_a_box.events import (
    MoveABoxActionTaken,
    MoveABoxBay,
    MoveABoxFloorView,
    MoveABoxNoteWritten,
    MoveABoxOperatorFinished,
    MoveABoxRequestReleased,
    MoveABoxRoundResolved,
    MoveABoxRoundStarted,
    MoveABoxTargetResolved,
    MoveABoxTargetStarted,
)
from glossogen.scenarios.move_a_box.ids import (
    ACT_RESULT_TEMPLATE,
    ACT_TOOL,
    ACTION_RESULT_TEMPLATE,
    ALL_FINISHED_TRIGGER,
    CLOSING_QUESTION_TEMPLATE,
    DELIVERY_POINTS,
    DESCRIPTION_TEMPLATE,
    FINISH_TOOL,
    HAUL_TOOL,
    HIDDEN_BASE_TOOLS,
    INJECTION_TEMPLATE,
    LANDMARK_CRATE_MARK,
    MATCH_BONUS,
    NOTEPAD_TOOL,
    PACK_ICE_TOOL,
    PROTOCOL_CONTINUE_TEMPLATE,
    PROTOCOL_INITIAL_TEMPLATE,
    PROTOCOL_SUFFIX_TEMPLATE,
    READ_NOTIFICATIONS_TEMPLATE,
    READOUT_TEMPLATE,
    RELEASE_NOTICE_TEMPLATE,
    STAND_BY_TOOL,
    SYSTEM_TEMPLATE,
    TEMPERATURE_DELTA,
    BayIdentity,
    Direction,
    HaulMethod,
    operator_ids,
    others_of,
    owner_of,
)
from glossogen.scenarios.move_a_box.knobs import MoveABoxKnobs
from glossogen.scenarios.move_a_box.planned_action import (
    AppliedList,
    AppliedStep,
    CrateAction,
    PlannedCrateStep,
    PlannedStep,
    ResolvedStep,
    StepReport,
    haul_method_of,
)
from glossogen.scenarios.move_a_box.run_detail_extension import MoveABoxRunDetailExtension
from glossogen.scenarios.move_a_box.wake_package import MoveABoxWake
from glossogen.scenarios.move_a_box.world import (
    LoggedAction,
    MoveABoxWorld,
    RoundOutcome,
    TargetOutcome,
)
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

RELEASE_LIMIT = 2
"""Times per target an operator is released from a wait nothing can end. Past it the
operator stays parked, and the round ends once both are."""

PARTNER_ACTED = "other_crate_moved"
"""The release detail that wakes a parked operator when the other has acted."""

TARGET_STARTED = "next_target"
"""The release detail that hands a parked operator the briefing of the round's next target."""

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
FINISH_TARGET_DESCRIPTION = (
    "Leave the crate where it stands for the rest of this target. Its square cannot change "
    "until the next target begins. Returns the depot readout."
)


def _act_description(
    targets_per_round: int, partner_disclosed: bool, other_count: int, step_time: str | None
) -> str:
    """The ``act`` tool's description, naming what a finish leaves the crate for.

    It mentions the other operators only when the run tells the operators that
    others exist: they wait for the list, or when actions take ``step_time``
    they keep acting and reading while it runs.
    """
    span = "round"
    if targets_per_round > 1:
        span = "target"
    timing = ""
    if step_time is not None:
        timing = (
            f"Each action but finish takes {step_time}, and the call returns once the last has "
            "landed. "
        )
    others = ""
    if partner_disclosed and step_time is None:
        others = "No other operator reads the depot readout until the list is done. "
    elif partner_disclosed:
        others = _others_keep_acting(other_count=other_count, during="while the list runs") + " "
    return (
        "Work the crate through a list of actions, as many as you like, applied in order. "
        "drag, sled and cart each carry it one square in the direction you give; stand_by and "
        "pack_ice each take an action without moving it; finish leaves it where it stands for "
        f"the rest of the {span}. Give direction for drag, sled and cart, and null for the other "
        f"three. {timing}{others}An action the floor refuses stops the list there: the actions "
        "before it stand, and the one that stopped it spends nothing. Returns the depot readout."
    )


def _timed_action_note(step_time: str | None, partner_disclosed: bool, other_count: int) -> str:
    """What a one-action tool's description adds when its action takes ``step_time``.

    Empty when actions take no time. It mentions the other operators only when
    the run tells the operators that others exist.
    """
    if step_time is None:
        return ""
    note = f" The action takes {step_time}, and the call returns once it has landed."
    if not partner_disclosed:
        return note
    return f"{note} {_others_keep_acting(other_count=other_count, during='meanwhile')}"


def _others_keep_acting(other_count: int, during: str) -> str:
    """The sentence saying the other operators act and read the readout ``during`` a timed call."""
    if other_count > 1:
        return f"The other operators keep acting and reading the depot readout {during}."
    return f"The other operator keeps acting and reading the depot readout {during}."


NOTEPAD_DESCRIPTION = (
    "Replace your private note with the text you give, and read it back. Nobody else ever "
    "sees it. Call it with an empty text to read the note you have."
)
ROUND_ENDED_DURING_HOLD = (
    "ended before the depot readout came back. Call read_notifications(wait_for='next_round')."
)
"""What a held call returns, after naming what stood, when its round ended during the hold."""


def _round_has_ended(round_number: int) -> str:
    """The refusal of a call made after its round ended."""
    return f"Round {round_number} has ended. Call read_notifications(wait_for='next_round')."


def _ended_before_landing(round_number: int, landed: int, requested: int) -> str:
    """What a floor call returns when its round ended before all its actions landed."""
    return (
        f"Round {round_number} ended after {landed} of {requested} actions landed. Call "
        "read_notifications(wait_for='next_round')."
    )


REASONING_SUFFIX = " reasoning is one sentence on why you are doing this; nobody else sees it."
CRATE_SUFFIX = " crate is the marking of the crate you are acting on, as the readout shows it."


class CrateOutcome(NamedTuple):
    """Where one crate was left, as the next briefing names it.

    ``bay`` is the name of the bay the crate was left on, its square or its
    symbol, or None when it reached no bay it could score.
    """

    marking: str
    bay: str | None


class PreviousResult(NamedTuple):
    """The last scored target from one operator's side, as the next briefing reads it.

    A round briefing reports the previous round's last target, with
    ``closes_round`` set and ``own_points`` the whole round's points. A target
    briefing reports the target before it in the same round, and ``own_points``
    is what that target paid. ``own_crates`` runs in slot order, and
    ``other_crates`` in operator order then slot order with this operator left
    out, which is the order the readout lists them in. Crates are matched by
    slot, so an operator that cannot tell which of its crates landed where
    cannot learn anything from the result.
    """

    round_number: int
    target_number: int
    closes_round: bool
    bay_identity: BayIdentity
    own_crates: tuple[CrateOutcome, ...]
    other_crates: tuple[CrateOutcome, ...]
    matched: bool
    own_points: int


class PlayedTarget(NamedTuple):
    """A round's latest target and its bays, which name the bays its result fell on."""

    target_number: int
    layout: TargetLayout


class IdentitySwitch(NamedTuple):
    """A round whose bays are marked differently from the round before it.

    The scenario description lists every switch, and the briefing of
    ``round_number`` announces its own.
    """

    round_number: int
    previous: BayIdentity
    current: BayIdentity


class CrateRow(NamedTuple):
    """One crate's line of the depot readout.

    ``cell``, ``bay``, ``bay_is_yours`` and ``finished`` are filled in only
    for the reader's own crates. ``bay`` is the name of the bay the crate stands
    on, or None off the bays. Another operator's square is not on its line,
    because the reading is the only thing that crosses.
    """

    crate_id: str
    mass_kg: int
    temperature: int
    readings: str
    status: str
    own: bool
    cell: str | None
    bay: str | None
    bay_is_yours: bool
    finished: bool


class BayListing(NamedTuple):
    """One bay the depot assigned an operator, as its briefing lists it."""

    name: str
    mark: str
    square: str


def _cell(pair: tuple[int, int]) -> Cell:
    return Cell(row=pair[0], col=pair[1])


@scenario(name="move_a_box")
class MoveABoxScenario(SimulationScenario):
    """Operators delivering crates to bays, with no channel."""

    @classmethod
    def event_types(cls) -> tuple[type[EventBase], ...]:
        """Return the event classes this scenario logs, all defined in its ``events`` module."""
        return (
            MoveABoxRoundStarted,
            MoveABoxTargetStarted,
            MoveABoxTargetResolved,
            MoveABoxActionTaken,
            MoveABoxNoteWritten,
            MoveABoxOperatorFinished,
            MoveABoxRequestReleased,
            MoveABoxRoundResolved,
        )

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
            targets_per_round=knobs.targets_per_round,
            grid_size=knobs.grid_size,
            steps_per_round=knobs.steps_per_round,
            batched_actions=knobs.batched_actions,
        )
        self._depots = generate_depots(
            seed=knobs.seed,
            agent_ids=self._agent_ids,
            bay_identities=tuple(
                knobs.bay_identity_of(round_number=round_number)
                for round_number in range(1, knobs.round_count + 1)
            ),
            grid_size=knobs.grid_size,
            bay_count=knobs.bay_count,
            bays_allowed_each=knobs.bays_allowed_each,
            crates_each=knobs.crates_each,
            bays_differ=knobs.bays_differ,
            crate_start=knobs.crate_start,
            pallet_density=knobs.pallet_density,
            yard_setup=knobs.yard_setup(),
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
        # The round and target whose briefing each operator last received.
        self._briefed_target: dict[str, tuple[int, int]] = {}
        # A target briefing handed out once its operator next reads notifications.
        self._pending_target: dict[str, str] = {}
        # Each round's latest target, from play or from a restored log.
        self._played_targets: dict[int, PlayedTarget] = {}
        self._started_round = 0
        # Under step_duration_s an operator's haul, stand_by, pack_ice, finish and
        # act calls run one after another, in the order its response lists them:
        # the clock tracks one busy interval per operator, and a finish must not
        # land ahead of an action listed before it.
        self._timed_calls = {agent_id: asyncio.Lock() for agent_id in self._agent_ids}
        self._clock: VirtualClock | None = None
        if knobs.virtual_clock:
            self._clock = VirtualClock(
                config=VirtualClockConfig(
                    base_latency_s=knobs.virtual_base_latency_s,
                    output_tokens_per_second=knobs.virtual_output_tokens_per_second,
                ),
                agent_ids=list(self._agent_ids),
            )

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
                "bay_identity": self._knobs.bay_identity,
                "landmark_mirrored": self._knobs.landmark_mirrored,
                "view_shift": self._knobs.view_shift,
                "private_bays_outside_overlap": self._knobs.private_bays_outside_overlap,
                "identity_switches": self._identity_switches(),
                "targets_per_round": self._knobs.targets_per_round,
                "crate_start": self._knobs.crate_start.value,
                "partner_readout": self._knobs.partner_readout,
                "partner_disclosed": self._knobs.partner_disclosed,
                "batched_actions": self._knobs.batched_actions,
                "virtual_clock": self._knobs.virtual_clock,
                "step_time": self._step_time(),
            },
        )

    def _step_time(self) -> str | None:
        """How long an action takes, as the prompts state it, or None when actions take no time."""
        seconds = self._knobs.step_duration_s
        if not seconds:
            return None
        if seconds == 1:
            return "1 second"
        return f"{seconds:g} seconds"

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """One agent per operator, in no channel, offered only the floor actions."""
        tool_names = [HAUL_TOOL, STAND_BY_TOOL, PACK_ICE_TOOL, FINISH_TOOL]
        if self._knobs.batched_actions:
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
                "targets_per_round": self._knobs.targets_per_round,
                "bay_identity": self._knobs.bay_identity,
                "view_shift": self._knobs.view_shift,
                "partner_disclosed": self._knobs.partner_disclosed,
                "decoy_readings": self._knobs.decoy_readings,
                "channel_disclosed": self._knobs.channel_disclosed,
                "has_pallets": self._knobs.pallet_density > 0.0,
                "notepad_enabled": self._knobs.notepad_enabled,
                "batched_actions": self._knobs.batched_actions,
                "step_time": self._step_time(),
                "virtual_clock": self._knobs.virtual_clock,
                "thermal_table": self._thermal_table(),
                "round_seconds": f"{self._knobs.max_round_duration_seconds:g}",
            },
        )

    def _identity_switches(self) -> list[IdentitySwitch]:
        """Every round marked differently from the round before it, in round order."""
        switches: list[IdentitySwitch] = []
        for round_number in range(2, self._knobs.round_count + 1):
            previous = self._knobs.bay_identity_of(round_number=round_number - 1)
            current = self._knobs.bay_identity_of(round_number=round_number)
            if current is not previous:
                switches.append(
                    IdentitySwitch(round_number=round_number, previous=previous, current=current)
                )
        return switches

    def _identity_switch_at(self, round_number: int) -> IdentitySwitch | None:
        """The switch taking effect at ``round_number``, or None when its marks are unchanged."""
        for switch in self._identity_switches():
            if switch.round_number == round_number:
                return switch
        return None

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
        """The action protocol, with no mention of messages.

        Under ``describe_protocol_at_end`` it also carries the closing question.
        """
        _ = agent_id
        return RunnerPrompts(
            system_suffix=self._renderer.render(
                template_name=PROTOCOL_SUFFIX_TEMPLATE,
                template_variables={
                    "action_reasoning": self._knobs.action_reasoning,
                    "notepad_enabled": self._knobs.notepad_enabled,
                    "targets_per_round": self._knobs.targets_per_round,
                    "batched_actions": self._knobs.batched_actions,
                    "crates_each": self._knobs.crates_each,
                },
            ),
            initial=self._renderer.render(
                template_name=PROTOCOL_INITIAL_TEMPLATE,
                template_variables={"batched_actions": self._knobs.batched_actions},
            ),
            continuation=self._renderer.render(
                template_name=PROTOCOL_CONTINUE_TEMPLATE,
                template_variables={"batched_actions": self._knobs.batched_actions},
            ),
            closing=self._closing_question(),
        )

    def _closing_question(self) -> str | None:
        """What the runner asks each operator once the run is over, or None when nothing is asked.

        The question does not mention temperature, the readout or any action.
        """
        if not self._knobs.describe_protocol_at_end:
            return None
        return self._renderer.render(
            template_name=CLOSING_QUESTION_TEMPLATE,
            template_variables={"other_count": self._knobs.operator_count - 1},
        )

    def read_notifications_description(self) -> str:
        """Describe the wake package and the waits an operator uses."""
        return self._renderer.render(
            template_name=READ_NOTIFICATIONS_TEMPLATE,
            template_variables={"virtual_clock": self._knobs.virtual_clock},
        )

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
            self._briefed_target[agent_id] = (current, 1)
        pending = self._pending_target.pop(agent_id, None)
        if pending is not None and self._world.round_open:
            briefings.append(pending)
            self._briefed_target[agent_id] = (current, self._world.target_number)
        readout: str | None = None
        if self._world.round_open and self._briefed_round.get(agent_id) == current:
            readout = self._readout(agent_id=agent_id, result="Depot readout.")
        reasons = [reason.value for reason in wake.reasons]
        notice: str | None = None
        if WakeReason.RELEASED in wake.reasons:
            if wake.release_detail in (PARTNER_ACTED, TARGET_STARTED):
                reasons = [
                    wake.release_detail if reason == WakeReason.RELEASED.value else reason
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
        is another acting. An operator with a target briefing it has not read is
        released at once, whatever it waits for.

        Under ``virtual_clock`` the clock hears of the park first, because a
        release from here resumes the operator before this hook returns.
        """
        if self._clock is not None:
            self._clock.park(agent_id=agent_id)
        for other in others_of(agent_id=agent_id, agent_ids=self._agent_ids):
            self._release[other].set()
        if not self._world.round_open:
            return
        if agent_id in self._pending_target:
            self.runtime.release_wait(agent_id=agent_id, detail=TARGET_STARTED)
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
                template_variables={
                    "others_done": others_done,
                    "batched_actions": self._knobs.batched_actions,
                },
            ),
        )

    def on_agent_resumed(self, agent_id: str) -> None:
        """Under ``virtual_clock``, start the operator's next request at the instant it woke."""
        if self._clock is not None:
            self._clock.wake(agent_id=agent_id)

    def on_model_request_started(self, agent_id: str) -> None:
        """Remember the round this model request was issued in, and start its virtual latency."""
        self._request_round[agent_id] = self.runtime.current_round
        if self._clock is not None:
            self._clock.begin_inference(agent_id=agent_id)

    async def gate_model_response(
        self,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
        tool_calls: list[ToolCallRequest],
    ) -> None:
        """Under ``virtual_clock``, hold the response until its virtual turn and log its release.

        Under ``virtual_list_cost_fixed`` each ``act`` list costs a fixed time
        instead of its tokens; the logged ``output_tokens`` stay the reported count.
        """
        _ = input_tokens
        if self._clock is None:
            return
        charged = output_tokens
        if self._knobs.virtual_list_cost_fixed:
            charged = charged_output_tokens(
                output_tokens=output_tokens,
                tool_calls=tool_calls,
                list_cost_s=self._knobs.virtual_list_cost_s,
                tokens_per_second=self._knobs.virtual_output_tokens_per_second,
            )
        timing = await self._clock.complete_inference(agent_id=agent_id, output_tokens=charged)
        await self._log_event(
            event=MoveABoxRequestReleased(
                round_number=self.runtime.current_round,
                agent_id=agent_id,
                started_at_s=timing.started_at,
                completed_at_s=timing.completed_at,
                output_tokens=output_tokens,
            )
        )

    def schedule_wait_timeout(
        self, agent_id: str, timeout_s: float, fire: Callable[[], None]
    ) -> Callable[[], None]:
        """Count a parked operator's timeout in virtual seconds under ``virtual_clock``."""
        if self._clock is None:
            return super().schedule_wait_timeout(agent_id=agent_id, timeout_s=timeout_s, fire=fire)
        return self._clock.schedule_timer(delay_seconds=timeout_s, callback=fire)

    def clock_now_s(self) -> float:
        """Virtual seconds under ``virtual_clock``, so waits report virtual durations."""
        if self._clock is None:
            return super().clock_now_s()
        return self._clock.time()

    def scenario_tool_timeout_s(self) -> float:
        """A round's length when actions take time: a list's call waits on the others' requests."""
        if not self._knobs.step_duration_s:
            return super().scenario_tool_timeout_s()
        return self._knobs.max_round_duration_seconds

    def on_agent_retired(self, agent_id: str) -> None:
        """Release an operator holding an action open for one that is leaving.

        Under ``virtual_clock`` the leaving operator stops being scheduled.
        """
        if self._clock is not None:
            self._clock.retire(agent_id=agent_id)
        self._release_all()

    def on_agent_enlisted(self, agent_id: str) -> None:
        """Under ``virtual_clock``, schedule a swapped-in operator from the swap instant on."""
        if self._clock is not None:
            self._clock.enlist(agent_id=agent_id)

    def on_simulation_stopping(self) -> None:
        """Release every held action and every response the clock holds, so none is left waiting."""
        if self._clock is not None:
            self._clock.stop()
        self._release_all()

    def get_injection(self, round_number: int, agent_id: str) -> str:
        """The round briefing: the previous round's last result and this round's first target."""
        depot = self._depots[round_number - 1]
        return self._briefing(
            agent_id=agent_id,
            round_number=round_number,
            target_number=1,
            target=depot.first_target,
            crate=depot.starts[agent_id],
            previous=self._previous_round_result(agent_id=agent_id, round_number=round_number),
            identity_switch=self._identity_switch_at(round_number=round_number),
        )

    def _previous_round_result(self, agent_id: str, round_number: int) -> PreviousResult | None:
        """The last target of the round before ``round_number``, or None in the first round."""
        outcome = self._world.outcome(round_number=round_number - 1)
        if outcome is None:
            return None
        played = self._played_target(round_number=outcome.round_number)
        return self._previous_result(
            agent_id=agent_id,
            round_number=outcome.round_number,
            target_number=played.target_number,
            closes_round=True,
            layout=played.layout,
            final_bays=outcome.final_bays,
            matched=len(outcome.matched_slots) == self._knobs.crates_each,
            own_points=outcome.points[agent_id],
        )

    def _previous_result(
        self,
        agent_id: str,
        round_number: int,
        target_number: int,
        closes_round: bool,
        layout: TargetLayout,
        final_bays: dict[str, int | None],
        matched: bool,
        own_points: int,
    ) -> PreviousResult:
        """One scored target as ``agent_id``'s next briefing reports it, named by ``layout``."""

        def outcome_of(crate_id: str) -> CrateOutcome:
            number = final_bays[crate_id]
            bay: str | None = None
            if number is not None:
                bay = layout.bay_name(number=number, agent_id=owner_of(crate_id))
            return CrateOutcome(marking=self._crates[crate_id].crate_id, bay=bay)

        return PreviousResult(
            round_number=round_number,
            target_number=target_number,
            closes_round=closes_round,
            bay_identity=layout.bay_identity,
            own_crates=tuple(
                outcome_of(crate_id=crate_id)
                for crate_id in self._world.crates_of(agent_id=agent_id)
            ),
            other_crates=tuple(
                outcome_of(crate_id=crate_id)
                for other in others_of(agent_id=agent_id, agent_ids=self._agent_ids)
                for crate_id in self._world.crates_of(agent_id=other)
            ),
            matched=matched,
            own_points=own_points,
        )

    def _floor_drawing(
        self, agent_id: str, round_number: int, target: TargetLayout, crate: Cell
    ) -> list[str]:
        """``agent_id``'s floor with its crate on ``crate``, drawn for ``target``'s bay identity."""
        depot = self._depots[round_number - 1]
        if target.bay_identity.is_landmark():
            return landmark_floor_rows(
                landmarks=depot.landmarks[agent_id],
                bays=target.bays[agent_id],
                crates={crate: LANDMARK_CRATE_MARK},
                grid_size=self._knobs.grid_size,
            )
        return floor_rows(
            target=target,
            pallets=depot.pallets[agent_id],
            crate=crate,
            agent_id=agent_id,
            grid_size=self._knobs.grid_size,
        )

    def _floor_now(self, agent_id: str) -> list[str]:
        """``agent_id``'s landmark floor with its crate where it stands now; no rows off landmarks.

        A landmark floor numbers no square, so a result that moved the crate
        draws the floor again to say where it went.
        """
        target = self._world.target
        if not target.bay_identity.is_landmark():
            return []
        return self._floor_drawing(
            agent_id=agent_id,
            round_number=self._world.depot.round_number,
            target=target,
            crate=self._world.cell_of(crate_id=self._world.crates_of(agent_id=agent_id)[0]),
        )

    def _briefing(
        self,
        agent_id: str,
        round_number: int,
        target_number: int,
        target: TargetLayout,
        crate: Cell,
        previous: PreviousResult | None,
        identity_switch: IdentitySwitch | None,
    ) -> str:
        """A briefing for one target: the result before it, the floor, the bays and the crate."""
        return self._renderer.render(
            template_name=INJECTION_TEMPLATE,
            template_variables={
                "round_number": round_number,
                "target_number": target_number,
                "targets_per_round": self._knobs.targets_per_round,
                "previous": previous,
                "points_so_far": self._world.points_so_far(agent_id=agent_id),
                "floor_rows": self._floor_drawing(
                    agent_id=agent_id, round_number=round_number, target=target, crate=crate
                ),
                "allowed_bays": _bay_listings(target=target, agent_id=agent_id),
                "bay_identity": target.bay_identity,
                "identity_switch": identity_switch,
                "start": crate.label(),
                "crates": [
                    self._crates[crate_id].crate_id
                    for crate_id in self._world.crates_of(agent_id=agent_id)
                ],
                "partner_bay_disclosed": self._knobs.partner_bay_disclosed,
                "view_shift": self._knobs.view_shift,
                "match_bonus": MATCH_BONUS,
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Place both crates on the start square and log the round's floor."""
        if round_number <= self._started_round:
            return
        depot = self._depots[round_number - 1]
        self._world.start_round(depot=depot)
        self._pending_target.clear()
        self._played_targets[round_number] = PlayedTarget(
            target_number=1, layout=depot.first_target
        )
        self._humidity = humidity_series(
            seed=self._knobs.seed,
            round_number=round_number,
            length=self._knobs.steps_per_round,
        )
        self._started_round = round_number
        if self._clock is not None:
            self._clock.start_round()
        await self._log_event(
            event=MoveABoxRoundStarted(
                round_number=round_number,
                grid_size=self._knobs.grid_size,
                start_cells={
                    agent_id: (cell.row, cell.col) for agent_id, cell in depot.starts.items()
                },
                bay_identity=depot.first_target.bay_identity.value,
                floor_bays=_logged_bays(target=depot.first_target),
                pallets={
                    agent_id: sorted((cell.row, cell.col) for cell in cells)
                    for agent_id, cells in depot.pallets.items()
                },
                allowed_bays={
                    agent_id: list(bays)
                    for agent_id, bays in depot.first_target.allowed_bays.items()
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
                virtual_time_s=self._virtual_now(),
                floor_views=_logged_views(
                    depot=depot,
                    over_a_yard=(
                        self._knobs.bay_identity.is_landmark() or self._knobs.view_shift > 0
                    ),
                ),
            )
        )

    def _virtual_now(self) -> float | None:
        """The virtual second of the run under ``virtual_clock``, and None otherwise."""
        if self._clock is None:
            return None
        return self._clock.time()

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once no operator can act on its last target."""
        if self._world.all_done() and self._world.on_last_target():
            return ALL_FINISHED_TRIGGER
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Resolve the round on the squares the crates stand on."""
        async with self._lock:
            if self._world.outcome(round_number=round_number) is not None:
                return
            if not self._world.round_open:
                return
            if not self._world.target_scored():
                target = self._world.resolve_target()
                await self._log_target_resolved(round_number=round_number, outcome=target)
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
        """Seed resolved rounds, so the first briefing after a fork reports the last result.

        A round that played several targets reports its last one, whose bays its
        ``move_a_box_target_started`` event recorded. Under ``virtual_clock`` the
        clock carries on from the latest virtual instant the log records.
        """
        for event in events:
            if isinstance(event, MoveABoxTargetStarted):
                self._played_targets[event.round_number] = PlayedTarget(
                    target_number=event.target_number, layout=_layout_from_event(event=event)
                )
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
        resumed_at = _latest_virtual_time(events=events)
        if self._clock is not None and resumed_at is not None:
            self._clock.resume_at(time_s=resumed_at)

    def get_tools(self) -> list[ScenarioTool]:
        """The floor actions, and ``notepad`` when the knobs offer it.

        Under ``batched_actions`` the floor actions are one ``act`` tool taking
        a list of them. Otherwise they are ``haul``, ``stand_by``, ``pack_ice``
        and ``finish``, one action a call.
        """
        if self._knobs.batched_actions:
            tools = [self._act_tool()]
        else:
            tools = self._single_action_tools()
        if self._knobs.notepad_enabled:
            tools.append(self._notepad_tool())
        return tools

    def _single_action_tools(self) -> list[ScenarioTool]:
        """``haul``, ``stand_by``, ``pack_ice`` and ``finish``, each taking one action.

        ``reasoning`` is offered only under ``action_reasoning`` and ``crate``
        only when an operator works more than one, so each argument is absent
        from the schema rather than present and ignored.
        """

        async def spend(
            agent_id: str,
            crate: str,
            action: CrateAction,
            direction: Direction | None,
            reasoning: str,
        ) -> str:
            crate_id = self._crate_for(agent_id=agent_id, crate=crate)
            checked = self._checked_reasoning(reasoning=reasoning, subject="this action")
            round_number = self._open_round_for(agent_id=agent_id)
            step = ResolvedStep(crate_id=crate_id, action=action, direction=direction)
            if self._knobs.step_duration_s:
                async with self._timed_calls[agent_id]:
                    return await self._land_single_step(
                        agent_id=agent_id, round_number=round_number, step=step, reasoning=checked
                    )
            return await self._land_single_step(
                agent_id=agent_id, round_number=round_number, step=step, reasoning=checked
            )

        async def haul(
            agent_id: str, crate: str, method: HaulMethod, direction: Direction, reasoning: str
        ) -> str:
            return await spend(
                agent_id=agent_id,
                crate=crate,
                action=CrateAction(method.value),
                direction=direction,
                reasoning=reasoning,
            )

        async def stand_by(agent_id: str, crate: str, reasoning: str) -> str:
            return await spend(
                agent_id=agent_id,
                crate=crate,
                action=CrateAction.STAND_BY,
                direction=None,
                reasoning=reasoning,
            )

        async def pack_ice(agent_id: str, crate: str, reasoning: str) -> str:
            return await spend(
                agent_id=agent_id,
                crate=crate,
                action=CrateAction.PACK_ICE,
                direction=None,
                reasoning=reasoning,
            )

        async def finish(agent_id: str, crate: str, reasoning: str) -> str:
            crate_id = self._crate_for(agent_id=agent_id, crate=crate)
            checked = self._checked_reasoning(reasoning=reasoning, subject="this action")
            round_number = self._open_round_for(agent_id=agent_id)
            if self._knobs.step_duration_s:
                async with self._timed_calls[agent_id]:
                    return await self._land_finish(
                        agent_id=agent_id,
                        round_number=round_number,
                        crate_id=crate_id,
                        reasoning=checked,
                    )
            return await self._land_finish(
                agent_id=agent_id, round_number=round_number, crate_id=crate_id, reasoning=checked
            )

        def only(agent_id: str) -> str:
            """The marking of the one crate an operator works when it has one."""
            return self._crates[self._world.crates_of(agent_id=agent_id)[0]].crate_id

        async def haul_plain(
            agent_id: str, crate: str, method: HaulMethod, direction: Direction
        ) -> str:
            return await haul(
                agent_id=agent_id, crate=crate, method=method, direction=direction, reasoning="."
            )

        async def stand_by_plain(agent_id: str, crate: str) -> str:
            return await stand_by(agent_id=agent_id, crate=crate, reasoning=".")

        async def pack_ice_plain(agent_id: str, crate: str) -> str:
            return await pack_ice(agent_id=agent_id, crate=crate, reasoning=".")

        async def finish_plain(agent_id: str, crate: str) -> str:
            return await finish(agent_id=agent_id, crate=crate, reasoning=".")

        async def haul_solo(
            agent_id: str, method: HaulMethod, direction: Direction, reasoning: str
        ) -> str:
            return await haul(
                agent_id=agent_id,
                crate=only(agent_id),
                method=method,
                direction=direction,
                reasoning=reasoning,
            )

        async def stand_by_solo(agent_id: str, reasoning: str) -> str:
            return await stand_by(agent_id=agent_id, crate=only(agent_id), reasoning=reasoning)

        async def pack_ice_solo(agent_id: str, reasoning: str) -> str:
            return await pack_ice(agent_id=agent_id, crate=only(agent_id), reasoning=reasoning)

        async def finish_solo(agent_id: str, reasoning: str) -> str:
            return await finish(agent_id=agent_id, crate=only(agent_id), reasoning=reasoning)

        async def haul_solo_plain(agent_id: str, method: HaulMethod, direction: Direction) -> str:
            return await haul(
                agent_id=agent_id,
                crate=only(agent_id),
                method=method,
                direction=direction,
                reasoning=".",
            )

        async def stand_by_solo_plain(agent_id: str) -> str:
            return await stand_by(agent_id=agent_id, crate=only(agent_id), reasoning=".")

        async def pack_ice_solo_plain(agent_id: str) -> str:
            return await pack_ice(agent_id=agent_id, crate=only(agent_id), reasoning=".")

        async def finish_solo_plain(agent_id: str) -> str:
            return await finish(agent_id=agent_id, crate=only(agent_id), reasoning=".")

        many = self._knobs.crates_each > 1
        if self._knobs.action_reasoning:
            chosen = (
                (haul, stand_by, pack_ice, finish)
                if many
                else (
                    haul_solo,
                    stand_by_solo,
                    pack_ice_solo,
                    finish_solo,
                )
            )
            suffix = REASONING_SUFFIX
        else:
            chosen = (
                (haul_plain, stand_by_plain, pack_ice_plain, finish_plain)
                if many
                else (
                    haul_solo_plain,
                    stand_by_solo_plain,
                    pack_ice_solo_plain,
                    finish_solo_plain,
                )
            )
            suffix = ""
        crate_suffix = CRATE_SUFFIX if many else ""
        finish_description = FINISH_DESCRIPTION
        if self._knobs.targets_per_round > 1:
            finish_description = FINISH_TARGET_DESCRIPTION
        timing = _timed_action_note(
            step_time=self._step_time(),
            partner_disclosed=self._knobs.partner_disclosed,
            other_count=self._knobs.operator_count - 1,
        )
        return [
            ScenarioTool(
                name=name,
                description=description + crate_suffix + suffix,
                executor=executor,
            )
            for name, description, executor in zip(
                (HAUL_TOOL, STAND_BY_TOOL, PACK_ICE_TOOL, FINISH_TOOL),
                (
                    HAUL_DESCRIPTION + timing,
                    STAND_BY_DESCRIPTION + timing,
                    PACK_ICE_DESCRIPTION + timing,
                    finish_description,
                ),
                chosen,
                strict=True,
            )
        ]

    def _act_tool(self) -> ScenarioTool:
        """``act``, which takes a list of actions and applies them in order.

        ``reasoning`` is offered only under ``action_reasoning``, one sentence
        for the whole list, and a step names its ``crate`` only when an operator
        works more than one.
        """

        async def act(agent_id: str, steps: list[PlannedCrateStep], reasoning: str) -> str:
            return await self._act(agent_id=agent_id, steps=steps, reasoning=reasoning)

        async def act_plain(agent_id: str, steps: list[PlannedCrateStep]) -> str:
            return await self._act(agent_id=agent_id, steps=steps, reasoning=".")

        async def act_solo(agent_id: str, steps: list[PlannedStep], reasoning: str) -> str:
            return await self._act(agent_id=agent_id, steps=steps, reasoning=reasoning)

        async def act_solo_plain(agent_id: str, steps: list[PlannedStep]) -> str:
            return await self._act(agent_id=agent_id, steps=steps, reasoning=".")

        many = self._knobs.crates_each > 1
        description = _act_description(
            targets_per_round=self._knobs.targets_per_round,
            partner_disclosed=self._knobs.partner_disclosed,
            other_count=self._knobs.operator_count - 1,
            step_time=self._step_time(),
        )
        if many:
            description += CRATE_SUFFIX
        executor: Callable[..., Awaitable[str]]
        if self._knobs.action_reasoning:
            description += REASONING_SUFFIX
            if many:
                executor = act
            else:
                executor = act_solo
        elif many:
            executor = act_plain
        else:
            executor = act_solo_plain
        return ScenarioTool(name=ACT_TOOL, description=description, executor=executor)

    def _notepad_tool(self) -> ScenarioTool:
        """``notepad``: a private note the operator writes and reads back, at no step's cost."""

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

        return ScenarioTool(name=NOTEPAD_TOOL, description=NOTEPAD_DESCRIPTION, executor=notepad)

    async def _act(self, agent_id: str, steps: Sequence[PlannedStep], reasoning: str) -> str:
        """Put ``steps`` on the floor in order, then wake the others and hold once.

        Every action the floor takes lands before any of it is logged, and
        logging is the first thing that awaits, so nothing that reads the floor
        sees part of the list. An operator the list left with nothing to act on
        gets its readout under the same lock, before the next target can open or
        the round can end, as a single ``finish`` does. Otherwise the operator is
        held until another operator acts, as after a single ``haul``.

        A list that waited on the lock past the end of its round lands nothing
        and says so.

        Under ``step_duration_s`` the list lands one action at a time instead,
        in ``_act_over_time``.
        """
        checked = self._checked_reasoning(reasoning=reasoning, subject="this list")
        resolved = self._resolve_steps(agent_id=agent_id, steps=steps)
        round_number = self._open_round_for(agent_id=agent_id)
        if self._knobs.step_duration_s:
            async with self._timed_calls[agent_id]:
                return await self._act_over_time(
                    agent_id=agent_id, round_number=round_number, steps=resolved, reasoning=checked
                )
        async with self._lock:
            if not self._round_still_open(round_number=round_number):
                return _ended_before_landing(
                    round_number=round_number, landed=0, requested=len(resolved)
                )
            outcome = self._apply_steps(steps=resolved)
            if outcome.stopped is not None and not outcome.applied:
                raise ValueError(outcome.stopped)
            for applied in outcome.applied:
                await self._log_step(round_number=round_number, applied=applied, reasoning=checked)
            result = self._act_result(
                agent_id=agent_id,
                round_number=round_number,
                outcome=outcome,
                requested=len(resolved),
            )
            closing: str | None = None
            if self._world.is_done(agent_id=agent_id):
                closing = self._readout(agent_id=agent_id, result=result)
            await self._open_next_target_if_done(round_number=round_number)
        if closing is not None:
            self._wake_others(agent_id=agent_id)
            return closing
        return await self._after_action(
            agent_id=agent_id,
            round_number=round_number,
            result=result,
            ended=f"{result}\nRound {round_number} {ROUND_ENDED_DURING_HOLD}",
        )

    async def _land_finish(
        self, agent_id: str, round_number: int, crate_id: str, reasoning: str | None
    ) -> str:
        """Leave ``crate_id`` where it stands and return the readout, rendered under the lock.

        The readout is rendered before the next target can open or the round can
        end. A finish takes no time and holds nobody.
        """
        async with self._lock:
            if not self._round_still_open(round_number=round_number):
                return _ended_before_landing(round_number=round_number, landed=0, requested=1)
            applied = self._take_step(
                step=ResolvedStep(crate_id=crate_id, action=CrateAction.FINISH, direction=None)
            )
            await self._log_step(round_number=round_number, applied=applied, reasoning=reasoning)
            view = self._readout(
                agent_id=agent_id,
                result=self._action_result(
                    agent_id=agent_id,
                    round_number=round_number,
                    entry=applied.entry,
                    bay=self._bay_name(number=applied.bay, agent_id=agent_id),
                ),
            )
            await self._open_next_target_if_done(round_number=round_number)
        self._wake_others(agent_id=agent_id)
        return view

    async def _land_single_step(
        self, agent_id: str, round_number: int, step: ResolvedStep, reasoning: str | None
    ) -> str:
        """Put one ``haul``, ``stand_by`` or ``pack_ice`` on the floor, then wake the others.

        Under ``step_duration_s`` the action lands once its time has passed. The
        operator is then held as ``_after_action`` holds it.
        """
        refusal = await self._wait_for_step(agent_id=agent_id, round_number=round_number, step=step)
        if refusal is not None:
            raise ValueError(refusal)
        async with self._lock:
            if not self._round_still_open(round_number=round_number):
                return _ended_before_landing(round_number=round_number, landed=0, requested=1)
            applied = self._take_step(step=step)
            await self._log_step(round_number=round_number, applied=applied, reasoning=reasoning)
            result = self._action_result(
                agent_id=agent_id, round_number=round_number, entry=applied.entry, bay=None
            )
            await self._open_next_target_if_done(round_number=round_number)
        return await self._after_action(
            agent_id=agent_id,
            round_number=round_number,
            result=result,
            ended=(
                f"Your {applied.entry.action} stood, and round {round_number} "
                f"{ROUND_ENDED_DURING_HOLD}"
            ),
        )

    async def _act_over_time(
        self,
        agent_id: str,
        round_number: int,
        steps: Sequence[ResolvedStep],
        reasoning: str | None,
    ) -> str:
        """Land ``steps`` one at a time, each once its ``step_duration_s`` has passed.

        The others act and read the readout while the list runs, and each
        landing wakes an operator parked on the readout. An action the floor
        refuses stops the list before any of its time passes, and refuses the
        whole call when it is the first. When the round ends partway, the call
        says how many actions landed.
        """
        applied: list[AppliedStep] = []
        for step in steps:
            stopped = await self._wait_for_step(
                agent_id=agent_id, round_number=round_number, step=step
            )
            if stopped is not None and not applied:
                raise ValueError(stopped)
            if stopped is not None:
                return await self._list_readout(
                    agent_id=agent_id,
                    round_number=round_number,
                    outcome=AppliedList(applied=applied, stopped=stopped),
                    requested=len(steps),
                )
            final = await self._land_listed_step(
                agent_id=agent_id,
                round_number=round_number,
                step=step,
                steps=steps,
                applied=applied,
                reasoning=reasoning,
            )
            if final is not None:
                return final
        return await self._list_readout(
            agent_id=agent_id,
            round_number=round_number,
            outcome=AppliedList(applied=applied, stopped=None),
            requested=len(steps),
        )

    async def _wait_for_step(
        self, agent_id: str, round_number: int, step: ResolvedStep
    ) -> str | None:
        """Keep ``agent_id`` busy for ``step_duration_s`` of virtual time before ``step`` lands.

        Returns why the step cannot land, before any time passes: the floor's
        refusal, or the round having ended. A finish takes no time. Returns None
        at once for every step when actions take no time.
        """
        clock = self._clock
        if clock is None or not self._knobs.step_duration_s:
            return None
        async with self._lock:
            if not self._round_still_open(round_number=round_number):
                return _round_has_ended(round_number=round_number)
            refusal = self._step_refusal(step=step)
        if refusal is not None:
            return refusal
        if step.action is not CrateAction.FINISH:
            await clock.occupy(agent_id=agent_id, duration_s=self._knobs.step_duration_s)
        return None

    async def _land_listed_step(
        self,
        agent_id: str,
        round_number: int,
        step: ResolvedStep,
        steps: Sequence[ResolvedStep],
        applied: list[AppliedStep],
        reasoning: str | None,
    ) -> str | None:
        """Land ``step`` of a timed list and append it to ``applied``; the call's result if it ends.

        The list ends here when the round ended before ``step`` could land, or
        when ``step`` left the operator with nothing to act on. That operator's
        readout is rendered under the same lock, before the next target can open
        or the round can end, as ``_act`` does, and reports the action after
        ``step`` as refused. Otherwise the others are woken and None returned.
        """
        closing: str | None = None
        async with self._lock:
            if not self._round_still_open(round_number=round_number):
                return _ended_before_landing(
                    round_number=round_number, landed=len(applied), requested=len(steps)
                )
            landed = self._take_step(step=step)
            applied.append(landed)
            await self._log_step(round_number=round_number, applied=landed, reasoning=reasoning)
            if self._world.is_done(agent_id=agent_id):
                stopped: str | None = None
                if len(applied) < len(steps):
                    stopped = self._step_refusal(step=steps[len(applied)])
                closing = self._readout(
                    agent_id=agent_id,
                    result=self._act_result(
                        agent_id=agent_id,
                        round_number=round_number,
                        outcome=AppliedList(applied=applied, stopped=stopped),
                        requested=len(steps),
                    ),
                )
                await self._open_next_target_if_done(round_number=round_number)
        self._wake_others(agent_id=agent_id)
        return closing

    async def _list_readout(
        self, agent_id: str, round_number: int, outcome: AppliedList, requested: int
    ) -> str:
        """The readout a timed list returns once it has run out or was stopped."""
        async with self._lock:
            if not self._round_still_open(round_number=round_number):
                return _ended_before_landing(
                    round_number=round_number, landed=len(outcome.applied), requested=requested
                )
            return self._readout(
                agent_id=agent_id,
                result=self._act_result(
                    agent_id=agent_id,
                    round_number=round_number,
                    outcome=outcome,
                    requested=requested,
                ),
            )

    def _round_still_open(self, round_number: int) -> bool:
        """Whether round ``round_number`` is still the one being played."""
        return self._world.round_open and self.runtime.current_round == round_number

    def _resolve_steps(self, agent_id: str, steps: Sequence[PlannedStep]) -> list[ResolvedStep]:
        """Read a whole list against ``agent_id``'s crates before any of it is applied.

        An empty list, a step naming a crate the operator does not work, a
        carrying action with no direction, or an action in place with one,
        refuses the call and leaves the floor as it was. What the floor itself
        refuses stops the list where it happens instead.
        """
        if not steps:
            raise ValueError("Give at least one action. Nothing happened.")
        return [
            self._resolve_step(agent_id=agent_id, position=position, step=step)
            for position, step in enumerate(steps, start=1)
        ]

    def _resolve_step(self, agent_id: str, position: int, step: PlannedStep) -> ResolvedStep:
        """One step of a list, its crate found and its direction checked against its action."""
        crate_id = self._world.crates_of(agent_id=agent_id)[0]
        if isinstance(step, PlannedCrateStep):
            named = self._crate_id_of(agent_id=agent_id, crate=step.crate)
            if named is None:
                raise ValueError(
                    f"Action {position} names {step.crate!r}, which is not a crate you are "
                    f"working. Yours are: {self._markings_of(agent_id=agent_id)}. Nothing happened."
                )
            crate_id = named
        carries = haul_method_of(action=step.action) is not None
        if carries and step.direction is None:
            raise ValueError(
                f"Action {position} is {step.action.value}, which carries the crate one square "
                "and needs a direction. Nothing happened."
            )
        if not carries and step.direction is not None:
            raise ValueError(
                f"Action {position} is {step.action.value}, which does not move the crate, so "
                "it takes no direction. Nothing happened."
            )
        return ResolvedStep(crate_id=crate_id, action=step.action, direction=step.direction)

    def _apply_steps(self, steps: Sequence[ResolvedStep]) -> AppliedList:
        """Put a read list on the floor in order, stopping at the first action it refuses."""
        applied: list[AppliedStep] = []
        for step in steps:
            refusal = self._step_refusal(step=step)
            if refusal is not None:
                return AppliedList(applied=applied, stopped=refusal)
            applied.append(self._take_step(step=step))
        return AppliedList(applied=applied, stopped=None)

    def _step_refusal(self, step: ResolvedStep) -> str | None:
        """Why the floor will not take ``step`` now, or None when it will."""
        if step.action is CrateAction.FINISH:
            return self._world.finish_refusal(crate_id=step.crate_id)
        if step.direction is not None:
            return self._world.haul_refusal(crate_id=step.crate_id, direction=step.direction)
        return self._world.action_refusal(crate_id=step.crate_id)

    def _take_step(self, step: ResolvedStep) -> AppliedStep:
        """Apply one action to the floor; raises ``ValueError`` on anything the floor refuses.

        Logs nothing: the caller logs the step once every action it is applying
        has landed.
        """
        bay: int | None = None
        method = haul_method_of(action=step.action)
        if step.action is CrateAction.FINISH:
            entry = self._world.finish(crate_id=step.crate_id)
            bay = self._world.scored_bay_of(crate_id=step.crate_id, cell=entry.cell)
        elif method is None:
            entry = self._world.cool(crate_id=step.crate_id, action=step.action.value)
        else:
            assert step.direction is not None
            entry = self._world.haul(
                crate_id=step.crate_id, method=method, direction=step.direction
            )
        return AppliedStep(
            entry=entry, steps_used=self._world.steps_used(agent_id=entry.agent_id), bay=bay
        )

    def _bay_name(self, number: int | None, agent_id: str) -> str | None:
        """What ``agent_id`` calls bay ``number`` on the target in play, or None for no bay."""
        if number is None:
            return None
        return self._world.target.bay_name(number=number, agent_id=agent_id)

    def _action_result(
        self, agent_id: str, round_number: int, entry: LoggedAction, bay: str | None
    ) -> str:
        """What one single-action tool did, as its result opens."""
        return self._renderer.render(
            template_name=ACTION_RESULT_TEMPLATE,
            template_variables={
                "floor_now": self._floor_now(agent_id=agent_id),
                "action": entry.action,
                "direction": entry.direction,
                "round_number": round_number,
                "target_number": self._world.target_number,
                "targets_per_round": self._knobs.targets_per_round,
                "bay": bay,
                "bay_identity": self._world.target.bay_identity,
                "crate": self._crates[entry.crate_id].crate_id,
            },
        )

    def _act_result(
        self, agent_id: str, round_number: int, outcome: AppliedList, requested: int
    ) -> str:
        """What an ``act`` list did, action by action, as the call's result opens."""
        return self._renderer.render(
            template_name=ACT_RESULT_TEMPLATE,
            template_variables={
                "floor_now": self._floor_now(agent_id=agent_id),
                "steps": [self._step_report(applied=applied) for applied in outcome.applied],
                "stopped": outcome.stopped,
                "requested": requested,
                "round_number": round_number,
                "target_number": self._world.target_number,
                "targets_per_round": self._knobs.targets_per_round,
                "bay_identity": self._world.target.bay_identity,
            },
        )

    def _step_report(self, applied: AppliedStep) -> StepReport:
        """One applied action of a list, as the call's result names it back."""
        entry = applied.entry
        return StepReport(
            crate=self._crates[entry.crate_id].crate_id,
            action=entry.action,
            direction=entry.direction,
            temperature=entry.temperature,
            bay=self._bay_name(number=applied.bay, agent_id=entry.agent_id),
        )

    def _crate_for(self, agent_id: str, crate: str) -> str:
        """The crate id ``agent_id`` means by the marking ``crate``; raises when it works none.

        An operator can only act on its own crates, so a marking belonging to
        another operator reads the same as one that does not exist.
        """
        crate_id = self._crate_id_of(agent_id=agent_id, crate=crate)
        if crate_id is None:
            raise ValueError(
                f"{crate!r} is not a crate you are working. Yours are: "
                f"{self._markings_of(agent_id=agent_id)}."
            )
        return crate_id

    def _crate_id_of(self, agent_id: str, crate: str) -> str | None:
        """The crate id of ``agent_id``'s crate marked ``crate``, or None when it works none."""
        wanted = crate.strip().upper()
        for crate_id in self._world.crates_of(agent_id=agent_id):
            if self._crates[crate_id].crate_id.upper() == wanted:
                return crate_id
        return None

    def _markings_of(self, agent_id: str) -> str:
        """The markings of every crate ``agent_id`` works, as a refusal lists them."""
        return ", ".join(
            self._crates[crate_id].crate_id for crate_id in self._world.crates_of(agent_id=agent_id)
        )

    def _checked_reasoning(self, reasoning: str, subject: str) -> str | None:
        """The sentence to log with ``subject``, or None when the run does not ask for one."""
        if not self._knobs.action_reasoning:
            return None
        if not reasoning.strip():
            raise ValueError(f"Give one sentence of reasoning for {subject}. Nothing happened.")
        return reasoning.strip()

    async def _after_action(self, agent_id: str, round_number: int, result: str, ended: str) -> str:
        """Wake the other operators, hold this one until one acts, then render the readout.

        ``result`` opens the readout. The hold can outlive the round it belongs
        to, so the readout is rendered only while that round is still the open
        one. Past it there is no state to show, and the call returns ``ended``,
        which sends the operator to its next briefing.
        """
        self._wake_others(agent_id=agent_id)
        await self._hold_for_partner(agent_id=agent_id)
        async with self._lock:
            if not self._round_still_open(round_number=round_number):
                return ended
            return self._readout(agent_id=agent_id, result=result)

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
        """The depot readout from ``agent_id``'s side, marking the other crates' lines shown.

        In a round of several targets it also lists the operator's bays for the
        target in play, so an operator that lost a briefing finds them again on
        its next action.
        """
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
                "target_number": self._world.target_number,
                "targets_per_round": self._knobs.targets_per_round,
                "steps_used": self._world.steps_used(agent_id=agent_id),
                "crates": rows,
                "allowed_bays": _bay_listings(target=self._world.target, agent_id=agent_id),
                "bay_identity": self._world.target.bay_identity,
                "decoy_readings": self._knobs.decoy_readings,
                "readout_history": self._knobs.readout_history,
                "humidity": self._humidity_for(agent_id=agent_id),
                "clock_seconds": self._clock_seconds(),
            },
        )
        self._world.mark_shown(agent_id=agent_id)
        return view

    def _clock_seconds(self) -> int | None:
        """Whole virtual seconds since the round started, or None off the virtual clock."""
        if self._clock is None:
            return None
        return round(self._clock.round_elapsed_s())

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
        bay: str | None = None
        number = self._world.bay_of(agent_id=owner_of(crate_id), cell=cell)
        if own and number is not None:
            bay = self._world.target.bay_name(number=number, agent_id=owner_of(crate_id))
        return CrateRow(
            crate_id=tag.crate_id,
            mass_kg=tag.mass_kg,
            temperature=self._world.temperature_of(crate_id=crate_id),
            readings=" ".join(str(value) for value in self._world.readings_of(crate_id=crate_id)),
            status=status,
            own=own,
            cell=cell.label() if own else None,
            bay=bay,
            bay_is_yours=(
                self._world.scored_bay_of(crate_id=crate_id, cell=cell) is not None
                if own
                else False
            ),
            finished=finished if own else False,
        )

    def _played_target(self, round_number: int) -> PlayedTarget:
        """The latest target round ``round_number`` played: its first, unless a later one began."""
        played = self._played_targets.get(round_number)
        if played is None:
            return PlayedTarget(target_number=1, layout=self._depots[round_number - 1].first_target)
        return played

    async def _open_next_target_if_done(self, round_number: int) -> None:
        """Score the target in play once no operator can act on it, and hand out the next one.

        Called under the lock after every action. Does nothing on the round's
        last target, which the round's end scores. Operators with no steps left
        are done the moment a target opens, so the loop runs on through every
        target they cannot work.
        """
        while self._world.all_done() and not self._world.on_last_target():
            scored_layout = self._world.target
            outcome = self._world.resolve_target()
            await self._log_target_resolved(round_number=round_number, outcome=outcome)
            crates = {
                agent_id: self._world.cell_of(crate_id=self._world.crates_of(agent_id=agent_id)[0])
                for agent_id in self._agent_ids
            }
            layout = draw_next_target(
                seed=self._knobs.seed,
                round_number=round_number,
                target_number=outcome.target_number + 1,
                agent_ids=self._agent_ids,
                crates=crates,
                pallets=self._world.depot.pallets,
                grid_size=self._knobs.grid_size,
                bay_count=self._knobs.bay_count,
                bays_allowed_each=self._knobs.bays_allowed_each,
                bays_differ=self._knobs.bays_differ,
                bay_identity=scored_layout.bay_identity,
            )
            self._world.start_target(layout=layout)
            self._played_targets[round_number] = PlayedTarget(
                target_number=outcome.target_number + 1, layout=layout
            )
            await self._log_event(
                event=MoveABoxTargetStarted(
                    round_number=round_number,
                    target_number=outcome.target_number + 1,
                    bay_identity=layout.bay_identity.value,
                    floor_bays=_logged_bays(target=layout),
                    allowed_bays={
                        agent_id: list(bays) for agent_id, bays in layout.allowed_bays.items()
                    },
                )
            )
            for agent_id in self._agent_ids:
                self._pending_target[agent_id] = self._briefing(
                    agent_id=agent_id,
                    round_number=round_number,
                    target_number=outcome.target_number + 1,
                    target=layout,
                    crate=crates[agent_id],
                    previous=self._previous_result(
                        agent_id=agent_id,
                        round_number=round_number,
                        target_number=outcome.target_number,
                        closes_round=False,
                        layout=scored_layout,
                        final_bays=outcome.final_bays,
                        matched=outcome.matched,
                        own_points=outcome.points[agent_id],
                    ),
                    identity_switch=None,
                )
            for agent_id in self._agent_ids:
                self._release[agent_id].set()
                self.runtime.release_wait(agent_id=agent_id, detail=TARGET_STARTED)

    async def _log_target_resolved(self, round_number: int, outcome: TargetOutcome) -> None:
        """Log one scored target, when the round holds more than one."""
        if self._knobs.targets_per_round == 1:
            return
        await self._log_event(
            event=MoveABoxTargetResolved(
                round_number=round_number,
                target_number=outcome.target_number,
                final_cells={
                    crate_id: (cell.row, cell.col) for crate_id, cell in outcome.final_cells.items()
                },
                final_bays=dict(outcome.final_bays),
                matched_slots=outcome.matched_slots,
                matched=outcome.matched,
                points=dict(outcome.points),
            )
        )

    def _humidity_for(self, agent_id: str) -> int:
        """The floor humidity at ``agent_id``'s own action count, so neither operator moves it."""
        if not self._humidity:
            return 0
        return self._humidity[
            min(self._world.steps_used(agent_id=agent_id), len(self._humidity) - 1)
        ]

    async def _log_step(
        self, round_number: int, applied: AppliedStep, reasoning: str | None
    ) -> None:
        """Log one applied action: a finish as the operator finishing, any other as taken."""
        entry = applied.entry
        if entry.action == FINISH_TOOL:
            await self._log_event(
                event=MoveABoxOperatorFinished(
                    round_number=round_number,
                    agent_id=entry.agent_id,
                    crate_id=entry.crate_id,
                    crate_marking=self._crates[entry.crate_id].crate_id,
                    cell=(entry.cell.row, entry.cell.col),
                    bay=applied.bay,
                    temperature=entry.temperature,
                    steps_used=applied.steps_used,
                    reasoning=reasoning,
                    virtual_time_s=self._virtual_now(),
                )
            )
            return
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
                steps_used=applied.steps_used,
                reasoning=reasoning,
                virtual_time_s=self._virtual_now(),
            )
        )

    def _open_round_for(self, agent_id: str) -> int:
        """The round ``agent_id``'s call belongs to.

        Refuses a call from a round that ended, and one from an operator that
        has not read the briefing of the round or of the target in play.
        """
        current = self.runtime.current_round
        if not self._world.round_open:
            raise ValueError(_round_has_ended(round_number=current))
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
        target = self._world.target_number
        if self._briefed_target.get(agent_id) != (current, target):
            raise ValueError(
                f"Target {target} of round {current} has started and you have not read its "
                "briefing. Call read_notifications() first."
            )
        return current

    async def _log_event(self, event: EventBase) -> None:
        await self.runtime.event_logger.log(event=event)


def _bay_listings(target: TargetLayout, agent_id: str) -> list[BayListing]:
    """The bays ``target`` assigns ``agent_id``, in reading order, as briefings list them."""
    return [
        BayListing(
            name=target.bay_name(number=bay.number, agent_id=agent_id),
            mark=target.bay_mark(number=bay.number),
            square=bay.cell.label(),
        )
        for bay in target.bays[agent_id]
        if bay.number in target.allowed_bays[agent_id]
    ]


def _logged_views(depot: RoundDepot, over_a_yard: bool) -> dict[str, MoveABoxFloorView]:
    """Where each floor of ``depot`` sat in the yard; empty unless the floors are its windows."""
    if not over_a_yard:
        return {}
    return {
        agent_id: MoveABoxFloorView(
            row_offset=view.row_offset, col_offset=view.col_offset, mirrored=view.mirrored
        )
        for agent_id, view in depot.views.items()
    }


def _logged_bays(target: TargetLayout) -> dict[str, list[MoveABoxBay]]:
    """Every floor's bays of ``target``, as the round and target events record them."""
    return {
        agent_id: [
            MoveABoxBay(
                number=bay.number,
                name=target.bay_name(number=bay.number, agent_id=agent_id),
                mark=target.bay_mark(number=bay.number),
                cell=(bay.cell.row, bay.cell.col),
            )
            for bay in bays
        ]
        for agent_id, bays in target.bays.items()
    }


def _latest_virtual_time(events: list[Any]) -> float | None:
    """The latest virtual instant a log records, or None when it was not played on the clock."""
    times: list[float] = []
    for event in events:
        if isinstance(event, MoveABoxRequestReleased):
            times.append(event.completed_at_s)
        elif (
            isinstance(event, (MoveABoxActionTaken, MoveABoxOperatorFinished, MoveABoxRoundStarted))
            and event.virtual_time_s is not None
        ):
            times.append(event.virtual_time_s)
    return max(times, default=None)


def _layout_from_event(event: MoveABoxTargetStarted) -> TargetLayout:
    """The target a ``move_a_box_target_started`` event recorded."""
    return TargetLayout(
        bay_identity=BayIdentity(event.bay_identity),
        bays={
            agent_id: tuple(Bay(number=bay.number, cell=_cell(pair=bay.cell)) for bay in bays)
            for agent_id, bays in event.floor_bays.items()
        },
        allowed_bays={agent_id: tuple(bays) for agent_id, bays in event.allowed_bays.items()},
    )
