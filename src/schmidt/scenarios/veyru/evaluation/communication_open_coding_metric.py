"""Pass 1 of the communication-feature analysis pipeline.

Feeds the LLM judge the run's link-channel messages and the per-round
``motif → treatment_motif`` ground truth, then asks for free-form
short labels naming the communication-pattern features the team
exhibits. Persists the result as ``communication_open_coding.json`` in
the run directory; the consolidation script under
``scripts/consolidate_communication_ontology.py`` reads those sidecars
across many runs to produce the shared taxonomy used by pass 3.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from schmidt.evaluation.log_reader import extract_simulation_id
from schmidt.evaluation.measurement import Measurement
from schmidt.evaluation.metric_protocol import Metric
from schmidt.evaluation.metric_run_options import MetricRunOptions
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.communication_label_models import (
    CommunicationOpenCodingOutput,
    CommunicationOpenCodingSidecar,
)
from schmidt.scenarios.veyru.evaluation.communication_transcript_builder import build_link_rounds
from schmidt.scenarios.veyru.evaluation.prompt_renderer import render_veyru_prompt

logger = logging.getLogger(__name__)

_SIDECAR_FILENAME = "communication_open_coding.json"


class CommunicationOpenCodingMetric(Metric):
    """Runs the open-coding judge call and writes per-run free-form labels."""

    name = "communication_open_coding"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score one run's link-channel + ground-truth with the open-coding judge."""
        _ = agent_configs, scenario, options
        rounds = build_link_rounds(events=events)
        if not rounds:
            logger.info(
                "%s: skipping — no link-channel messages or case data in the run",
                self.name,
            )
            return []

        judge_prompt = render_veyru_prompt(
            template_name="communication_open_coding_user.jinja",
            template_variables={"rounds": rounds},
        )
        system_prompt = render_evaluator_prompt(
            template_name="evaluator_system.jinja",
            template_variables={},
        )

        logger.debug(
            "communication_open_coding LLM input system_prompt=%s user_prompt=%s",
            system_prompt,
            judge_prompt,
        )
        result = await llm_provider.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=CommunicationOpenCodingOutput,
        )
        logger.debug(
            "communication_open_coding LLM output=%s",
            result.model_dump_json(),
        )

        run_id = _run_id_from_events(events=events, run_dir=run_dir)
        sidecar = CommunicationOpenCodingSidecar(
            run_id=run_id,
            generated_at=datetime.now(tz=timezone.utc),
            labels=result.labels,
            explanation=result.explanation,
        )
        sidecar_path = run_dir / _SIDECAR_FILENAME
        sidecar_path.write_text(sidecar.model_dump_json(indent=2) + "\n")

        label_preview = "; ".join(label.text for label in result.labels[:5])
        summary = (
            f"Open-coded {len(result.labels)} free-form label(s) across "
            f"{len(rounds)} round(s); written to {sidecar_path.name}. "
            f"Top labels: {label_preview if label_preview else '(none)'}."
        )
        return [
            Measurement(
                metric_name=self.name,
                score=float(len(result.labels)),
                score_unit="free-form labels",
                summary=summary,
                per_round=[],
                per_agent=[],
            )
        ]


def _run_id_from_events(events: list[SimulationEvent], run_dir: Path) -> str:
    """Return the canonical ``{scenario}/{timestamp}`` run id.

    Prefers the SimulationStarted event's id; falls back to the run dir's
    ``{parent.name}/{name}`` shape when the log lacks that event.
    """
    try:
        return extract_simulation_id(events=events)
    except ValueError:
        return f"{run_dir.parent.name}/{run_dir.name}"
