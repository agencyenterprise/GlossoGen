"""orbital_anomaly extension to the platform run-detail API.

Surfaces per-round anomaly ground truth (each stage's cockpit alarm,
panel observation, telemetry readout, and expected corrective action) and
the actuation-judge verdict keyed by tool ``call_id``, so the round-timeline
modal can show what the crew observed and what the correct fix was.

The platform discovers this module at startup and wires
:class:`OrbitalAnomalyRunExtras` into the discriminated-union
``scenario_extras`` field on :class:`RunDetailResponse`.
"""

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel

from schmidt.models.event import SimulationEvent, ToolResultReceived
from schmidt.scenarios.orbital_anomaly.events import (
    OrbitalAnomalyActuationJudged,
    OrbitalAnomalyCaseStarted,
)
from schmidt.scenarios.orbital_anomaly.ids import ACTUATE_PANEL_TOOL
from schmidt.server.runs.run_detail_types import (
    AgentDetail,
    ChannelMessage,
    JudgeGroundTruthMetadata,
)
from schmidt.server.runs.scenario_extension import ScenarioRunDetailExtension, ScenarioRunExtrasBase


class OrbitalAnomalyCaseStageDTO(BaseModel):
    """One stage of an anomaly: the three agent views plus the expected fix."""

    fault_name: str
    subsystem: str
    cockpit_alarm: str
    panel_observation: str
    telemetry_readout: str
    judge_expected_actions: str


class OrbitalAnomalyCaseSummary(BaseModel):
    """Per-round anomaly metadata for the round-timeline modal.

    One entry per round, mirroring the ``OrbitalAnomalyCaseStarted`` event.
    ``variant_index`` is the per-round secret variant selection.
    """

    round_number: int
    case_number: int
    variant_index: int
    time_budget_seconds: int
    stages: list[OrbitalAnomalyCaseStageDTO]


class SSEOrbitalAnomalyActuationJudged(BaseModel):
    """SSE event carrying the actuation judge's verdict for an actuate_panel call."""

    event_type: Literal["orbital_anomaly_actuation_judged"]
    event_id: str
    timestamp: datetime
    agent_id: str
    round_number: int
    expected_actions: str
    judge_match: bool
    judge_explanation: str


class OrbitalAnomalyRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for orbital_anomaly runs."""

    scenario_name: Literal["orbital_anomaly"] = "orbital_anomaly"
    cases: list[OrbitalAnomalyCaseSummary]
    judge_ground_truth_by_call_id: dict[str, JudgeGroundTruthMetadata]


def _build_cases(events: list[SimulationEvent]) -> list[OrbitalAnomalyCaseSummary]:
    cases: list[OrbitalAnomalyCaseSummary] = []
    for event in events:
        if not isinstance(event, OrbitalAnomalyCaseStarted):
            continue
        cases.append(
            OrbitalAnomalyCaseSummary(
                round_number=event.round_number,
                case_number=event.case_number,
                variant_index=event.variant_index,
                time_budget_seconds=event.time_budget_seconds,
                stages=[
                    OrbitalAnomalyCaseStageDTO(
                        fault_name=stage.fault_name,
                        subsystem=stage.subsystem,
                        cockpit_alarm=stage.cockpit_alarm,
                        panel_observation=stage.panel_observation,
                        telemetry_readout=stage.telemetry_readout,
                        judge_expected_actions=stage.judge_expected_actions,
                    )
                    for stage in event.stages
                ],
            )
        )
    return cases


def _build_judge_ground_truth_by_call_id(
    events: list[SimulationEvent],
) -> dict[str, JudgeGroundTruthMetadata]:
    """Pair each ``OrbitalAnomalyActuationJudged`` with its ``actuate_panel`` tool result.

    The judged events are emitted in the same FIFO order as the
    corresponding tool results, scoped per agent; walks both event types
    chronologically and pairs them by (agent_id, FIFO position).
    """
    pending_by_agent: dict[str, list[JudgeGroundTruthMetadata]] = {}
    metadata_by_call_id: dict[str, JudgeGroundTruthMetadata] = {}
    for event in events:
        if isinstance(event, OrbitalAnomalyActuationJudged):
            pending_by_agent.setdefault(event.agent_id, []).append(
                JudgeGroundTruthMetadata(
                    expected_actions=event.expected_actions,
                    judge_match=event.judge_match,
                    judge_explanation=event.judge_explanation,
                )
            )
        elif isinstance(event, ToolResultReceived):
            if event.tool_name != ACTUATE_PANEL_TOOL:
                continue
            queue = pending_by_agent.get(event.agent_id)
            if not queue:
                continue
            metadata_by_call_id[event.call_id] = queue.pop(0)
    return metadata_by_call_id


class OrbitalAnomalyRunDetailExtension(ScenarioRunDetailExtension):
    """orbital_anomaly hook into :class:`RunDetailResponse.scenario_extras`."""

    scenario_name: ClassVar[str] = "orbital_anomaly"
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = OrbitalAnomalyRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = (SSEOrbitalAnomalyActuationJudged,)

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> OrbitalAnomalyRunExtras:
        _ = agents_by_id, messages
        return OrbitalAnomalyRunExtras(
            cases=_build_cases(events=events),
            judge_ground_truth_by_call_id=_build_judge_ground_truth_by_call_id(events=events),
        )
