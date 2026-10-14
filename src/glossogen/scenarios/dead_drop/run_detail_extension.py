"""dead_drop's extension to the platform run-detail API: the server's files, round by round.

Each round gets the tree as the round ended, rebuilt from the log by
``filesystem_snapshot``: every file's content, authors, who can read it, and the
last change made to it. Each ``run_command`` call gets the filesystem effects it
had, the changes and reads its command line made, keyed by the call's
``call_id``. One agent's commands run one at a time, so an effect belongs to the
call the agent had open when the effect was logged.
"""

from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import (
    SimulationEvent,
    SimulationStarted,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.scenarios.dead_drop.events import DeadDropFsChanged, DeadDropFsRead
from glossogen.scenarios.dead_drop.filesystem_snapshot import RoundSnapshot, round_snapshots
from glossogen.scenarios.dead_drop.ids import PROMPTS_DIR, RUN_COMMAND_TOOL, CaseDelivery
from glossogen.server.runs.run_detail_types import AgentDetail, ChannelMessage
from glossogen.server.runs.scenario_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.template_renderer import TemplateRenderer


class DeadDropFile(BaseModel):
    """One file as a round ended.

    ``tmp_of`` names the agent whose private ``/tmp`` holds it under
    ``fs_isolated``; it is null for a file both agents name by the same path.
    ``readers`` are the agents who can read it.
    """

    path: str
    tmp_of: str | None
    content: str
    authors: list[str]
    readers: list[str]
    last_changed_by: str
    last_changed_round: int


class DeadDropDirectory(BaseModel):
    """One directory as a round ended."""

    path: str
    tmp_of: str | None


class DeadDropRoundFiles(BaseModel):
    """Every file and directory on the server at the end of one round."""

    round_number: int
    files: list[DeadDropFile]
    directories: list[DeadDropDirectory]


class DeadDropFsEffectKind(StrEnum):
    """What a command line did to a file: one of the logged changes, or a read."""

    WRITE = "write"
    APPEND = "append"
    MKDIR = "mkdir"
    REMOVE = "remove"
    COPY = "copy"
    MOVE = "move"
    TOUCH = "touch"
    READ = "read"


class DeadDropFsEffect(BaseModel):
    """One change or read a ``run_command`` call made, repeated ``count`` times in a row.

    ``authors`` are the file's authors when it was read, and empty for a change.
    ``shared`` is whether the other agent can read the path the effect landed on.
    """

    kind: DeadDropFsEffectKind
    path: str
    destination: str | None
    authors: list[str]
    shared: bool
    count: int


class DeadDropRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for dead_drop runs."""

    scenario_name: Literal["dead_drop"] = "dead_drop"
    rounds: list[DeadDropRoundFiles]
    effects_by_call_id: dict[str, list[DeadDropFsEffect]]


def _case_in_file(scenario_config: dict[str, Any]) -> bool:
    """Whether the run wrote case files. A run recorded before ``case_delivery`` existed
    always did, and its config does not name the knob."""
    if "case_delivery" not in scenario_config:
        return True
    return scenario_config["case_delivery"] == CaseDelivery.FILE.value


def _scenario_config(events: list[SimulationEvent]) -> dict[str, Any]:
    for event in events:
        if isinstance(event, SimulationStarted):
            return event.scenario_config
    raise ValueError("a dead_drop run log has no simulation_started event")


def _round_files(snapshot: RoundSnapshot) -> DeadDropRoundFiles:
    return DeadDropRoundFiles(
        round_number=snapshot.round_number,
        files=[DeadDropFile(**file._asdict()) for file in snapshot.files],
        directories=[
            DeadDropDirectory(**directory._asdict()) for directory in snapshot.directories
        ],
    )


def _effect(event: DeadDropFsChanged | DeadDropFsRead) -> DeadDropFsEffect:
    if isinstance(event, DeadDropFsRead):
        return DeadDropFsEffect(
            kind=DeadDropFsEffectKind.READ,
            path=event.path,
            destination=None,
            authors=list(event.authors),
            shared=event.shared,
            count=1,
        )
    return DeadDropFsEffect(
        kind=DeadDropFsEffectKind(event.operation.value),
        path=event.path,
        destination=event.destination,
        authors=[],
        shared=event.shared,
        count=1,
    )


def _append_effect(effects: list[DeadDropFsEffect], effect: DeadDropFsEffect) -> None:
    """Add ``effect``, or count it on the last one when it repeats it."""
    if effects and effects[-1].model_copy(update={"count": 1}) == effect:
        effects[-1].count += 1
        return
    effects.append(effect)


def effects_by_call_id(events: list[SimulationEvent]) -> dict[str, list[DeadDropFsEffect]]:
    """Each ``run_command`` call's changes and reads, in the order it made them."""
    open_call: dict[str, str] = {}
    effects: dict[str, list[DeadDropFsEffect]] = {}
    for event in events:
        if isinstance(event, ToolCallInvoked) and event.tool_name == RUN_COMMAND_TOOL:
            open_call[event.agent_id] = event.call_id
        elif isinstance(event, ToolResultReceived) and event.tool_name == RUN_COMMAND_TOOL:
            open_call.pop(event.agent_id, None)
        elif isinstance(event, DeadDropFsChanged | DeadDropFsRead) and event.agent_id in open_call:
            _append_effect(
                effects=effects.setdefault(open_call[event.agent_id], []),
                effect=_effect(event=event),
            )
    return effects


class DeadDropRunDetailExtension(ScenarioRunDetailExtension):
    """dead_drop's hook into :class:`RunDetailResponse.scenario_extras`."""

    scenario_name: ClassVar[str] = "dead_drop"
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = DeadDropRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],  # noqa: ARG002 — protocol-required
        messages: list[ChannelMessage],  # noqa: ARG002 — protocol-required
    ) -> DeadDropRunExtras:
        """The files as each round ended, and each command's effects."""
        scenario_config = _scenario_config(events=events)
        snapshots = round_snapshots(
            events=events,
            fs_isolated=scenario_config["fs_isolated"],
            case_in_file=_case_in_file(scenario_config=scenario_config),
            renderer=TemplateRenderer(prompts_dirs=[PROMPTS_DIR]),
        )
        return DeadDropRunExtras(
            rounds=[_round_files(snapshot=snapshot) for snapshot in snapshots],
            effects_by_call_id=effects_by_call_id(events=events),
        )
