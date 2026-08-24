"""Synthetic export records: a run summary, a report, and the measurements on it.

Analysis reads runs through :class:`ExportRunRecord`, so a test that wants a cohort
of runs with known scores builds them here rather than running simulations. Every
field a projection reads is settable; the rest is fixed and uninteresting.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from glossogen.evaluation.metric_core.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.evaluation.reports.evaluation_cost import EvaluationCost, EvaluationTokenUsage
from glossogen.evaluation.reports.evaluation_report import EvaluationReport
from glossogen.models.event import RunStatus
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.server.runs.models import AgentModelSummary, RunSummary

ZERO_COST = EvaluationCost(
    usage=EvaluationTokenUsage(
        input_tokens=0,
        output_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    ),
    estimated_cost_usd=0.0,
    model="test",
    provider_name="test",
)

BASE_TIMESTAMP = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def make_agent(agent_id: str, model: str, provider: str) -> AgentModelSummary:
    """Build one roster entry."""
    return AgentModelSummary(
        agent_id=agent_id,
        role_name=agent_id.replace("_", " ").title(),
        model=model,
        provider=provider,
    )


def make_summary(
    run_id: str,
    scenario_name: str,
    scenario_config: dict[str, Any],
    labels: list[str],
    agents: list[AgentModelSummary],
    total_cost_usd: float,
    current_round: int,
    has_evaluation: bool,
) -> RunSummary:
    """Build a run summary carrying what the analysis projections read."""
    index = abs(hash(run_id)) % 1000
    return RunSummary(
        run_id=run_id,
        scenario_name=scenario_name,
        scenario_description="",
        scenario_config=scenario_config,
        timestamp=BASE_TIMESTAMP + timedelta(minutes=index),
        total_messages=42,
        total_cost_usd=total_cost_usd,
        duration_seconds=300.0,
        status=RunStatus.SCENARIO_COMPLETE,
        has_evaluation=has_evaluation,
        evaluation_in_progress=False,
        run_dir=f"/runs/{run_id}",
        fork_source=None,
        replace_agent_source=None,
        cross_run_replace_agent_source=None,
        fork_at_round_source=None,
        models=sorted({agent.model for agent in agents}),
        provider=agents[0].provider,
        agent_models=agents,
        labels=labels,
        has_note=False,
        current_round=current_round,
        evaluation_content_hash=None,
    )


def make_measurement(
    metric_name: str,
    score: float,
    per_round: list[tuple[int, float]],
    per_agent: list[tuple[str, float]],
) -> Measurement:
    """Build one measurement with the round and agent observations it reported."""
    return Measurement(
        metric_name=metric_name,
        score=score,
        score_unit="things",
        summary=f"{metric_name} summary",
        per_round=[
            RoundObservation(round_number=round_number, value=value, note="")
            for round_number, value in per_round
        ],
        per_agent=[
            AgentObservation(agent_id=agent_id, value=value, note="")
            for agent_id, value in per_agent
        ],
    )


def make_record(
    run_id: str,
    scenario_name: str,
    scenario_config: dict[str, Any],
    labels: list[str],
    agents: list[AgentModelSummary],
    measurements: list[Measurement] | None,
    total_cost_usd: float,
    current_round: int,
) -> ExportRunRecord:
    """Pair a synthetic summary with a report, or with no report at all."""
    summary = make_summary(
        run_id=run_id,
        scenario_name=scenario_name,
        scenario_config=scenario_config,
        labels=labels,
        agents=agents,
        total_cost_usd=total_cost_usd,
        current_round=current_round,
        has_evaluation=measurements is not None,
    )
    if measurements is None:
        return ExportRunRecord(summary=summary, report=None)
    return ExportRunRecord(
        summary=summary,
        report=EvaluationReport(
            simulation_id=run_id,
            scenario_name=scenario_name,
            measurements=measurements,
            evaluation_cost=ZERO_COST,
        ),
    )
