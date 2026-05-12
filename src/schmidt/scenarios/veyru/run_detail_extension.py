"""Veyru-specific extension to the platform run-detail API.

Defines the DTOs and the :class:`ScenarioRunDetailExtension` subclass that
materializes per-round case ground truth, the stabilization-judge
verdicts keyed by tool ``call_id``, and the observer-swap / intern-join
/ intern-takeover timeline anchors.

The platform discovers this module at startup via
:func:`schmidt.server.runs.scenario_extension.discover_scenario_extensions`
and wires :class:`VeyruRunExtras` into the discriminated-union
``scenario_extras`` field on :class:`RunDetailResponse`.
"""

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel

from schmidt.models.event import (
    ChannelHistoryCleared,
    ChannelMembershipChanged,
    SimulationEvent,
    ToolResultReceived,
)
from schmidt.scenarios.veyru.events import VeyruCaseStarted, VeyruStabilizationJudged
from schmidt.scenarios.veyru.ids import (
    INTERN_JOIN_REASON,
    INTERN_TAKEOVER_REASON,
    OBSERVER_SWAP_REASON,
)
from schmidt.server.runs.run_detail_types import AgentDetail, ChannelMessage
from schmidt.server.runs.scenario_extension import ScenarioRunDetailExtension, ScenarioRunExtrasBase

OBSERVER_A_ID = "observer_a"
OBSERVER_B_ID = "observer_b"
STABILIZE_TOOL_NAME = "stabilize_veyru"


class VeyruStabilizeMetadata(BaseModel):
    """Judge context captured for a single ``stabilize_veyru`` call.

    Attached to the corresponding ``ToolUseEntry`` so the frontend can show
    the expected procedure and the LLM judge's verdict alongside the raw
    tool call.
    """

    expected_actions: str
    judge_match: bool
    judge_explanation: str


class VeyruStellarReadingDTO(BaseModel):
    """Per-round stellar parameters shaping the Veyru procedure mapping."""

    offset: int
    hold_duration: int
    starting_face: str
    intensity_level: str


class VeyruCaseStageDTO(BaseModel):
    """One stage of a Veyru case with symptoms and the expected procedure."""

    motif_name: str
    observable_symptoms: str
    treatment_motif_name: str
    judge_expected_actions: str


class VeyruCaseSummary(BaseModel):
    """Per-round Veyru case metadata used by the round timeline modal.

    One entry per round. Mirrors the ``VeyruCaseStarted`` event emitted
    at each round start.
    """

    round_number: int
    case_number: int
    failure_name: str
    time_budget_seconds: int
    stages: list[VeyruCaseStageDTO]
    stellar_reading: VeyruStellarReadingDTO


class VeyruSwapPoint(BaseModel):
    """Anchor for the moment agents were swapped between teams.

    ``target_message_id`` is the first ``MessageSent`` on a link channel
    after the swap fired, used by the frontend to scroll the timeline
    to that exact point. ``swapped_observer_display_names`` are the
    two observers who exchanged teams, in stable order.
    """

    round_number: int
    target_message_id: str
    swapped_observer_display_names: list[str]


class VeyruInternAnchor(BaseModel):
    """Anchor for a timeline event in the Veyru intern-mode lifecycle.

    Used for both the intern-join moment and the intern-takeover moment.
    ``target_message_id`` is the first ``MessageSent`` on the link channel
    after the anchor fired, so the frontend can scroll to that point.
    """

    round_number: int
    target_message_id: str


class SSEVeyruStabilizationJudged(BaseModel):
    """SSE event carrying the veyru stabilization judge's verdict for a stabilize_veyru call."""

    event_type: Literal["veyru_stabilization_judged"]
    event_id: str
    timestamp: datetime
    agent_id: str
    round_number: int
    expected_actions: str
    judge_match: bool
    judge_explanation: str


class VeyruRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for Veyru runs."""

    scenario_name: Literal["veyru"] = "veyru"
    cases: list[VeyruCaseSummary]
    swap_point: VeyruSwapPoint | None
    intern_join: VeyruInternAnchor | None
    intern_takeover: VeyruInternAnchor | None
    stabilize_metadata_by_call_id: dict[str, VeyruStabilizeMetadata]


def _first_link_message_id_after(
    messages: list[ChannelMessage],
    after_timestamp: datetime,
) -> str | None:
    """Return the first link-channel ``message_id`` at or after ``after_timestamp``."""
    for msg in messages:
        if msg.timestamp < after_timestamp:
            continue
        if not msg.channel_id.startswith("link"):
            continue
        return msg.message_id
    return None


def _build_cases(events: list[SimulationEvent]) -> list[VeyruCaseSummary]:
    cases: list[VeyruCaseSummary] = []
    for event in events:
        if not isinstance(event, VeyruCaseStarted):
            continue
        cases.append(
            VeyruCaseSummary(
                round_number=event.round_number,
                case_number=event.case_number,
                failure_name=event.failure_name,
                time_budget_seconds=event.time_budget_seconds,
                stages=[
                    VeyruCaseStageDTO(
                        motif_name=stage.motif_name,
                        observable_symptoms=stage.observable_symptoms,
                        treatment_motif_name=stage.treatment_motif_name,
                        judge_expected_actions=stage.judge_expected_actions,
                    )
                    for stage in event.stages
                ],
                stellar_reading=VeyruStellarReadingDTO(
                    offset=event.stellar_reading.offset,
                    hold_duration=event.stellar_reading.hold_duration,
                    starting_face=event.stellar_reading.starting_face,
                    intensity_level=event.stellar_reading.intensity_level,
                ),
            )
        )
    return cases


def _build_stabilize_metadata_by_call_id(
    events: list[SimulationEvent],
) -> dict[str, VeyruStabilizeMetadata]:
    """Match each ``VeyruStabilizationJudged`` to its ``stabilize_veyru`` tool call.

    The Veyru world emits judged events in the same FIFO order as the
    corresponding tool results, scoped per agent. Walks both event types
    in chronological order and pairs them by (agent_id, FIFO position).
    """
    pending_by_agent: dict[str, list[VeyruStabilizeMetadata]] = {}
    metadata_by_call_id: dict[str, VeyruStabilizeMetadata] = {}
    for event in events:
        if isinstance(event, VeyruStabilizationJudged):
            pending_by_agent.setdefault(event.agent_id, []).append(
                VeyruStabilizeMetadata(
                    expected_actions=event.expected_actions,
                    judge_match=event.judge_match,
                    judge_explanation=event.judge_explanation,
                )
            )
        elif isinstance(event, ToolResultReceived):
            if event.tool_name != STABILIZE_TOOL_NAME:
                continue
            queue = pending_by_agent.get(event.agent_id)
            if not queue:
                continue
            metadata_by_call_id[event.call_id] = queue.pop(0)
    return metadata_by_call_id


def _build_swap_point(
    events: list[SimulationEvent],
    agents_by_id: dict[str, AgentDetail],
    messages: list[ChannelMessage],
) -> VeyruSwapPoint | None:
    swap_round: int | None = None
    swap_timestamp: datetime | None = None
    for event in events:
        if not isinstance(event, ChannelHistoryCleared):
            continue
        if event.reason != OBSERVER_SWAP_REASON:
            continue
        swap_round = event.round_number
        swap_timestamp = event.timestamp
        break
    if swap_round is None or swap_timestamp is None:
        return None
    target_message_id = _first_link_message_id_after(
        messages=messages, after_timestamp=swap_timestamp
    )
    if target_message_id is None:
        return None
    observer_a = agents_by_id.get(OBSERVER_A_ID)
    observer_b = agents_by_id.get(OBSERVER_B_ID)
    if observer_a is None or observer_b is None:
        return None
    return VeyruSwapPoint(
        round_number=swap_round,
        target_message_id=target_message_id,
        swapped_observer_display_names=[observer_a.role_name, observer_b.role_name],
    )


def _build_intern_anchor(
    events: list[SimulationEvent],
    messages: list[ChannelMessage],
    reason: str,
) -> VeyruInternAnchor | None:
    anchor_round: int | None = None
    anchor_timestamp: datetime | None = None
    for event in events:
        if not isinstance(event, ChannelMembershipChanged):
            continue
        if event.reason != reason:
            continue
        anchor_round = event.round_number
        anchor_timestamp = event.timestamp
        break
    if anchor_round is None or anchor_timestamp is None:
        return None
    target_message_id = _first_link_message_id_after(
        messages=messages, after_timestamp=anchor_timestamp
    )
    if target_message_id is None:
        return None
    return VeyruInternAnchor(round_number=anchor_round, target_message_id=target_message_id)


class VeyruRunDetailExtension(ScenarioRunDetailExtension):
    """Veyru hook into :class:`RunDetailResponse.scenario_extras`."""

    scenario_name: ClassVar[str] = "veyru"
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = VeyruRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = (SSEVeyruStabilizationJudged,)

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> VeyruRunExtras:
        return VeyruRunExtras(
            cases=_build_cases(events=events),
            swap_point=_build_swap_point(
                events=events, agents_by_id=agents_by_id, messages=messages
            ),
            intern_join=_build_intern_anchor(
                events=events, messages=messages, reason=INTERN_JOIN_REASON
            ),
            intern_takeover=_build_intern_anchor(
                events=events, messages=messages, reason=INTERN_TAKEOVER_REASON
            ),
            stabilize_metadata_by_call_id=_build_stabilize_metadata_by_call_id(events=events),
        )
