"""Pydantic event types specific to the orbital_anomaly scenario.

Imports only from ``schmidt.models.event_base`` so the event-discovery
walker can import this module without triggering ``scenario.py``.
"""

from typing import Literal

from pydantic import BaseModel

from schmidt.models.event_base import EventBase


class OrbitalAnomalyCaseStage(BaseModel):
    """One stage of an anomaly, with the three views and the judge ground truth.

    ``cockpit_alarm`` and ``panel_observation`` are what the astronaut sees,
    ``telemetry_readout`` is what the telemetry officer sees, and
    ``judge_expected_actions`` is the fully filled corrective procedure the
    actuation judge scores against.
    """

    fault_name: str
    subsystem: str
    cockpit_alarm: str
    panel_observation: str
    telemetry_readout: str
    judge_expected_actions: str


class OrbitalAnomalyCaseStarted(EventBase):
    """Emitted once at round start with the full ground-truth anomaly case.

    ``variant_index`` is the per-round secret selection that picks which of
    each fault's coherent procedure variants applies; the stages reveal one
    cascading fault at a time, the next appearing only after the current one
    is resolved.
    """

    event_type: Literal["orbital_anomaly_case_started"] = "orbital_anomaly_case_started"
    case_number: int
    variant_index: int
    time_budget_seconds: int
    stages: list[OrbitalAnomalyCaseStage]


class OrbitalAnomalyActuationJudged(EventBase):
    """Emitted after the actuation judge rules on an ``actuate_panel`` call.

    Captures the expected procedure fed to the LLM judge and the judge's
    verdict + explanation so the frontend can show ground-truth context
    alongside the corresponding tool result.
    """

    event_type: Literal["orbital_anomaly_actuation_judged"] = "orbital_anomaly_actuation_judged"
    agent_id: str
    expected_actions: str
    judge_match: bool
    judge_explanation: str
