"""orbital_anomaly extension to the platform run-detail API.

Surfaces per-round anomaly ground truth (each stage's cockpit alarm,
panel observation, telemetry readout, and expected corrective action) and
the actuation-judge verdict keyed by tool ``call_id``, so the round-timeline
modal can show what the crew observed and what the correct fix was.

``OrbitalAnomalyScenario.run_detail_extension`` returns the extension, and the server wires
:class:`OrbitalAnomalyRunExtras` into the discriminated-union
``scenario_extras`` field on :class:`RunDetailResponse`.
"""

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
    mirror_events,
    pair_with_tool_calls,
)
from glossogen.scenario_contract.run_detail_types import (
    AgentDetail,
    ChannelMessage,
    JudgeGroundTruthMetadata,
)
from glossogen.scenarios.orbital_anomaly.events import (
    OrbitalAnomalyActuationJudged,
    OrbitalAnomalyCaseStarted,
)
from glossogen.scenarios.orbital_anomaly.ids import ACTUATE_PANEL_TOOL


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


def _ground_truth(judged: OrbitalAnomalyActuationJudged) -> JudgeGroundTruthMetadata:
    """The platform-wide judge ground-truth shape for one ``actuate_panel`` verdict."""
    return JudgeGroundTruthMetadata(
        expected_actions=judged.expected_actions,
        judge_match=judged.judge_match,
        judge_explanation=judged.judge_explanation,
    )


class OrbitalAnomalyRunDetailExtension(ScenarioRunDetailExtension):
    """orbital_anomaly hook into :class:`RunDetailResponse.scenario_extras`."""

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
            cases=mirror_events(
                events=events,
                event_cls=OrbitalAnomalyCaseStarted,
                mirror_cls=OrbitalAnomalyCaseSummary,
            ),
            judge_ground_truth_by_call_id=pair_with_tool_calls(
                events=events,
                judged_event_cls=OrbitalAnomalyActuationJudged,
                tool_names=frozenset({ACTUATE_PANEL_TOOL}),
                build_payload=_ground_truth,
            ),
        )
