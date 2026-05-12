"""Pass 3 of the communication-feature analysis pipeline.

Reads a consolidated ontology JSON file (produced by
``src/schmidt/scenarios/veyru/scripts/consolidate_communication_ontology.py``)
and asks the LLM
judge to score each ontology category on this run's link-channel
messages. The result is a per-run feature-presence vector written to
``communication_feature_presence.json`` alongside the run's other
sidecars, and one ``Measurement`` whose ``score`` is the number of
categories above the 0.5 confidence threshold.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from schmidt.evaluation.log_reader import extract_simulation_id
from schmidt.evaluation.metric_core.measurement import Measurement
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.metrics.communication.label_models import (
    CommunicationFeaturePresenceOutput,
    CommunicationFeaturePresenceSidecar,
    CommunicationOntology,
)
from schmidt.scenarios.veyru.evaluation.metrics.communication.transcript_builder import (
    build_link_rounds,
)
from schmidt.scenarios.veyru.evaluation.prompts.prompt_renderer import render_veyru_prompt

logger = logging.getLogger(__name__)

_SIDECAR_FILENAME = "communication_feature_presence.json"
_PRESENCE_THRESHOLD = 0.5


class CommunicationFeaturePresenceMetric(Metric):
    """Scores each ontology category's presence on one run's link messages."""

    name = "communication_feature_presence"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Run the relabel judge against the supplied ontology and persist the vector."""
        _ = agent_configs, scenario
        if options.ontology_path is None:
            raise ValueError("communication_feature_presence requires --ontology-path PATH")
        ontology_path = options.ontology_path
        if not ontology_path.exists():
            raise FileNotFoundError(f"Ontology file not found: {ontology_path}")
        ontology = CommunicationOntology.model_validate_json(
            ontology_path.read_text(encoding="utf-8")
        )
        if not ontology.categories:
            raise ValueError(f"Ontology at {ontology_path} has no categories")

        rounds = build_link_rounds(events=events)
        if not rounds:
            logger.info(
                "%s: skipping — no link-channel messages or case data in the run",
                self.name,
            )
            return []

        judge_prompt = render_veyru_prompt(
            template_name="communication_feature_presence_user.jinja",
            template_variables={
                "rounds": rounds,
                "categories": ontology.categories,
            },
        )
        system_prompt = render_evaluator_prompt(
            template_name="evaluator_system.jinja",
            template_variables={},
        )

        logger.debug(
            "communication_feature_presence LLM input system_prompt=%s user_prompt=%s",
            system_prompt,
            judge_prompt,
        )
        result = await llm_provider.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=CommunicationFeaturePresenceOutput,
        )
        logger.debug(
            "communication_feature_presence LLM output=%s",
            result.model_dump_json(),
        )

        _check_score_coverage(result=result, ontology=ontology)

        run_id = _run_id_from_events(events=events, run_dir=run_dir)
        sidecar = CommunicationFeaturePresenceSidecar(
            run_id=run_id,
            ontology_version=ontology.version,
            ontology_path=str(ontology_path),
            generated_at=datetime.now(tz=timezone.utc),
            scores=result.scores,
            notes=result.notes,
        )
        sidecar_path = run_dir / _SIDECAR_FILENAME
        sidecar_path.write_text(sidecar.model_dump_json(indent=2) + "\n")

        sorted_scores = sorted(result.scores, key=lambda entry: entry.confidence, reverse=True)
        above_threshold = [
            entry for entry in result.scores if entry.confidence >= _PRESENCE_THRESHOLD
        ]
        top_preview = "; ".join(
            f"{entry.category_id}={entry.confidence:.2f}" for entry in sorted_scores[:3]
        )
        summary = (
            f"{len(above_threshold)}/{len(ontology.categories)} categories "
            f"≥ {_PRESENCE_THRESHOLD:.1f} on ontology {ontology.version}; "
            f"written to {sidecar_path.name}. Top: {top_preview if top_preview else '(none)'}."
        )
        return [
            Measurement(
                metric_name=self.name,
                score=float(len(above_threshold)),
                score_unit=(
                    f"categories ≥ {_PRESENCE_THRESHOLD:.1f} (of {len(ontology.categories)})"
                ),
                summary=summary,
                per_round=[],
                per_agent=[],
            )
        ]


def _check_score_coverage(
    result: CommunicationFeaturePresenceOutput,
    ontology: CommunicationOntology,
) -> None:
    """Warn when the judge skipped or invented ontology categories.

    Non-fatal: the sidecar still records exactly what the judge emitted so
    a partial score is recoverable. Missing categories show up as a
    smaller ``Measurement.score`` denominator.
    """
    ontology_ids = {category.id for category in ontology.categories}
    scored_ids = {entry.category_id for entry in result.scores}
    missing = ontology_ids - scored_ids
    invented = scored_ids - ontology_ids
    if missing:
        logger.warning(
            "Judge skipped %d ontology categories: %s",
            len(missing),
            ", ".join(sorted(missing)),
        )
    if invented:
        logger.warning(
            "Judge emitted %d categories not in the ontology: %s",
            len(invented),
            ", ".join(sorted(invented)),
        )


def _run_id_from_events(events: list[SimulationEvent], run_dir: Path) -> str:
    """Return the canonical ``{scenario}/{timestamp}`` run id."""
    try:
        return extract_simulation_id(events=events)
    except ValueError:
        return f"{run_dir.parent.name}/{run_dir.name}"
