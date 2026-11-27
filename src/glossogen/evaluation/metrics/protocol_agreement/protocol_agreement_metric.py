"""Metric that finds how the agents came to share each convention, and which messages show it.

One judge call reads the whole run as a cited transcript (see ``cited_transcript``).
Each step the judge returns keeps only the references that exist in the transcript,
and a step left with none is dropped. The result goes to the run's
``protocol_agreement.json`` sidecar, which the run page shows, and to a measurement
whose score counts the conventions that every agent used.
"""

import logging
from pathlib import Path

import aiofiles

from glossogen.evaluation.metrics.protocol_agreement.cited_transcript import (
    CitedEntry,
    build_cited_entries,
    render_cited_rounds,
)
from glossogen.evaluation.metrics.protocol_agreement.judge_output import (
    JudgedConvention,
    JudgedStep,
    ProtocolAgreementJudgeOutput,
)
from glossogen.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from glossogen.llm.provider import LLMMessage, LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.models.protocol_agreement import (
    AgreementStep,
    EvidenceMessage,
    ProtocolAgreementReport,
    ProtocolConvention,
)
from glossogen.run_storage.protocol_agreement_file import (
    PROTOCOL_AGREEMENT_FILE_NAME,
    protocol_agreement_path,
)
from glossogen.scenario_contract.measurement import Measurement, RoundNote, merge_round_notes
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.metric_run_options import MetricRunOptions
from glossogen.scenario_contract.scenario_base import ScenarioBase

logger = logging.getLogger(__name__)


class ProtocolAgreementMetric(Metric):
    """Finds the conventions the agents shared, who first used each, and who understood it."""

    name = "protocol_agreement"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Ask the judge once about the whole run; ``[]`` when the run has nothing to read."""
        _ = scenario, options
        entries = build_cited_entries(events=events)
        if not entries:
            logger.info("%s: skipping, the run has no messages or scenario tool calls", self.name)
            return []

        agent_ids = sorted({config.agent_id for config in agent_configs})
        judge_prompt = render_evaluator_prompt(
            template_name="protocol_agreement_user.jinja",
            template_variables={
                "rounds": render_cited_rounds(entries=entries),
                "agent_ids": agent_ids,
            },
        )
        judged = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja", template_variables={}
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=ProtocolAgreementJudgeOutput,
        )

        report = build_report(judged=judged, entries=entries)
        await write_report(run_dir=run_dir, report=report)
        return [measurement_from_report(metric_name=self.name, report=report)]


def build_report(
    judged: ProtocolAgreementJudgeOutput, entries: list[CitedEntry]
) -> ProtocolAgreementReport:
    """Turn the judge's references into evidence, keeping only those that exist in the run."""
    entry_by_reference = {entry.reference: entry for entry in entries}
    conventions = [
        _convention(judged=convention, entry_by_reference=entry_by_reference)
        for convention in judged.conventions
    ]
    return ProtocolAgreementReport(
        summary=judged.summary,
        conventions=[convention for convention in conventions if convention.steps],
    )


def _convention(
    judged: JudgedConvention, entry_by_reference: dict[str, CitedEntry]
) -> ProtocolConvention:
    """One convention with only the steps that cite at least one real entry."""
    steps: list[AgreementStep] = []
    for judged_step in judged.steps:
        step = _step(judged=judged_step, entry_by_reference=entry_by_reference)
        if step is not None:
            steps.append(step)
    return ProtocolConvention(
        name=judged.name,
        meaning=judged.meaning,
        steps=steps,
        adopted_by_all=judged.adopted_by_all,
        first_shared_round=judged.first_shared_round,
    )


def _step(judged: JudgedStep, entry_by_reference: dict[str, CitedEntry]) -> AgreementStep | None:
    """The step with its cited entries as evidence, or ``None`` when it cites none that exist."""
    evidence: list[EvidenceMessage] = []
    for reference in judged.references:
        entry = entry_by_reference.get(reference.strip().strip("[]"))
        if entry is None:
            logger.warning(
                "protocol_agreement: the judge cited %r, which is not in the run", reference
            )
            continue
        evidence.append(
            EvidenceMessage(
                message_id=entry.message_id,
                round_number=entry.round_number,
                agent_id=entry.agent_id,
                text=entry.text,
            )
        )
    if not evidence:
        return None
    return AgreementStep(
        stage=judged.stage,
        round_number=evidence[0].round_number,
        agent_id=evidence[0].agent_id,
        explanation=judged.explanation,
        evidence=evidence,
    )


async def write_report(run_dir: Path, report: ProtocolAgreementReport) -> None:
    """Overwrite the run's protocol-agreement sidecar with ``report``."""
    async with aiofiles.open(
        protocol_agreement_path(run_dir=run_dir), mode="w", encoding="utf-8"
    ) as handle:
        await handle.write(report.model_dump_json(indent=2) + "\n")


def measurement_from_report(metric_name: str, report: ProtocolAgreementReport) -> Measurement:
    """Score the conventions every agent used; note each step under the round it happened in."""
    notes = [
        RoundNote(
            round_number=step.round_number,
            note=f"{convention.name}, {step.stage.value} by {step.agent_id}: {step.explanation}",
        )
        for convention in report.conventions
        for step in convention.steps
    ]
    shared = [convention for convention in report.conventions if convention.adopted_by_all]
    summary = (
        f"{len(shared)} of {len(report.conventions)} conventions were used by every agent. "
        f"{report.summary} Steps and their messages are in {PROTOCOL_AGREEMENT_FILE_NAME}."
    )
    return Measurement(
        metric_name=metric_name,
        score=float(len(shared)),
        score_unit="conventions used by every agent",
        summary=summary,
        per_round=merge_round_notes(notes=notes),
        per_agent=[],
    )
