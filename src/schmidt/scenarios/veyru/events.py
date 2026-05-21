"""Pydantic event types specific to the Veyru stabilization scenario."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from schmidt.models.event_base import EventBase


class VeyruStellarReading(BaseModel):
    """Per-round stellar parameters derived from the position of star SAGWE392."""

    offset: int
    hold_duration: int
    starting_face: str
    intensity_level: str = Field(validation_alias=AliasChoices("intensity_level", "pressure_level"))


class VeyruCaseStage(BaseModel):
    """One stage of a Veyru case, with ground-truth symptoms and procedure."""

    motif_name: str
    observable_symptoms: str
    treatment_motif_name: str
    judge_expected_actions: str


class VeyruCaseStarted(EventBase):
    """Emitted once at round start with full ground-truth case data.

    Evaluators read per-stage ``observable_symptoms`` and ``judge_expected_actions``
    directly from this event, decoupling them from the real observer's
    ``stabilize_veyru`` tool calls.
    """

    event_type: Literal["veyru_case_started"] = "veyru_case_started"
    case_number: int
    failure_name: str
    time_budget_seconds: int
    stages: list[VeyruCaseStage]
    stellar_reading: VeyruStellarReading


class VeyruCaseOverridden(EventBase):
    """Emitted when an ``InjectCase`` payload overrides the natural-cycle case at a round.

    Carries the decoded ``case_number`` and ``failure_name`` for FE display +
    metric filtering. The raw scheduled payload also lives in the core
    ``CaseInjectedMidRun`` event the supervisor emits alongside this one.
    """

    event_type: Literal["veyru_case_overridden"] = "veyru_case_overridden"
    case_number: int
    failure_name: str


class VeyruStabilizationJudged(EventBase):
    """Emitted after the stabilization judge rules on a ``stabilize_veyru`` call.

    Captures the expected procedure fed to the LLM judge and the judge's
    verdict + explanation, so the frontend can show ground-truth context
    alongside the corresponding ``ToolResultReceived``. Correlated to the
    tool result by (agent_id, FIFO order) because MCP does not expose the
    pydantic-ai ``tool_call_id`` inside the executor.
    """

    event_type: Literal["veyru_stabilization_judged"] = "veyru_stabilization_judged"
    agent_id: str
    expected_actions: str
    judge_match: bool
    judge_explanation: str
