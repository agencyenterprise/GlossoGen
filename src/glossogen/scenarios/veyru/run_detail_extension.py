"""Veyru-specific extension to the platform run-detail API.

Defines the DTOs and the :class:`ScenarioRunDetailExtension` subclass that
materializes per-round case ground truth, the stabilization-judge
verdicts keyed by tool ``call_id``, and the observer-swap / intern-join
/ intern-takeover timeline anchors.

``VeyruScenario.run_detail_extension`` returns the extension, and the server
wires :class:`VeyruRunExtras` into the discriminated-union ``scenario_extras``
field on :class:`RunDetailResponse`.
"""

from datetime import datetime
from typing import ClassVar, Literal, NamedTuple

from pydantic import BaseModel

from glossogen.models.event import (
    ChannelHistoryCleared,
    ChannelMembershipChanged,
    SimulationEvent,
)
from glossogen.run_detail_types import (
    AgentDetail,
    ChannelMessage,
    JudgeGroundTruthMetadata,
)
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
    mirror_events,
    pair_with_tool_calls,
)
from glossogen.scenarios.veyru.events import VeyruCaseStarted, VeyruStabilizationJudged
from glossogen.scenarios.veyru.ids import (
    INTERN_JOIN_REASON,
    INTERN_TAKEOVER_REASON,
    LINK_CHANNEL_IDS,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    OBSERVER_SWAP_REASON,
    STABILIZE_VEYRU_TOOL,
)


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
    judge_ground_truth_by_call_id: dict[str, JudgeGroundTruthMetadata]


class _LinkAnchor(NamedTuple):
    """The round a channel event fired in and the first link message from that moment."""

    round_number: int
    target_message_id: str


def _first_link_anchor(
    events: list[SimulationEvent],
    messages: list[ChannelMessage],
    event_cls: type[ChannelHistoryCleared] | type[ChannelMembershipChanged],
    reason: str,
) -> _LinkAnchor | None:
    """Anchor the first ``event_cls`` event logged for ``reason`` on the link message that follows.

    The target is the first link-channel message sent at or after the event's
    timestamp. ``None`` when no such event was logged or no link message follows it.
    """
    marker = next(
        (event for event in events if isinstance(event, event_cls) and event.reason == reason),
        None,
    )
    if marker is None:
        return None
    for msg in messages:
        if msg.timestamp >= marker.timestamp and msg.channel_id in LINK_CHANNEL_IDS:
            return _LinkAnchor(round_number=marker.round_number, target_message_id=msg.message_id)
    return None


def _ground_truth(judged: VeyruStabilizationJudged) -> JudgeGroundTruthMetadata:
    """The platform-wide judge ground-truth shape for one ``stabilize_veyru`` verdict."""
    return JudgeGroundTruthMetadata(
        expected_actions=judged.expected_actions,
        judge_match=judged.judge_match,
        judge_explanation=judged.judge_explanation,
    )


def _build_swap_point(
    events: list[SimulationEvent],
    agents_by_id: dict[str, AgentDetail],
    messages: list[ChannelMessage],
) -> VeyruSwapPoint | None:
    anchor = _first_link_anchor(
        events=events,
        messages=messages,
        event_cls=ChannelHistoryCleared,
        reason=OBSERVER_SWAP_REASON,
    )
    if anchor is None:
        return None
    observer_a = agents_by_id.get(OBSERVER_A_ID)
    observer_b = agents_by_id.get(OBSERVER_B_ID)
    if observer_a is None or observer_b is None:
        return None
    return VeyruSwapPoint(
        round_number=anchor.round_number,
        target_message_id=anchor.target_message_id,
        swapped_observer_display_names=[observer_a.role_name, observer_b.role_name],
    )


def _build_intern_anchor(
    events: list[SimulationEvent],
    messages: list[ChannelMessage],
    reason: str,
) -> VeyruInternAnchor | None:
    anchor = _first_link_anchor(
        events=events,
        messages=messages,
        event_cls=ChannelMembershipChanged,
        reason=reason,
    )
    if anchor is None:
        return None
    return VeyruInternAnchor(
        round_number=anchor.round_number, target_message_id=anchor.target_message_id
    )


class VeyruRunDetailExtension(ScenarioRunDetailExtension):
    """Veyru hook into :class:`RunDetailResponse.scenario_extras`."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = VeyruRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = (SSEVeyruStabilizationJudged,)

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> VeyruRunExtras:
        return VeyruRunExtras(
            cases=mirror_events(
                events=events, event_cls=VeyruCaseStarted, mirror_cls=VeyruCaseSummary
            ),
            swap_point=_build_swap_point(
                events=events, agents_by_id=agents_by_id, messages=messages
            ),
            intern_join=_build_intern_anchor(
                events=events, messages=messages, reason=INTERN_JOIN_REASON
            ),
            intern_takeover=_build_intern_anchor(
                events=events, messages=messages, reason=INTERN_TAKEOVER_REASON
            ),
            judge_ground_truth_by_call_id=pair_with_tool_calls(
                events=events,
                judged_event_cls=VeyruStabilizationJudged,
                tool_names=frozenset({STABILIZE_VEYRU_TOOL}),
                build_payload=_ground_truth,
            ),
        )
