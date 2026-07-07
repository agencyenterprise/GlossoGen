"""Pass 3 of the communication-feature analysis pipeline.

Reads a consolidated ontology JSON file (produced by
``scripts/consolidate_communication_ontology.py``) and asks the LLM
judge to score each ontology category on this run's primary-channel
messages. The result is a per-run feature-presence vector written to
``communication_feature_presence.json`` alongside the run's other
sidecars, and one ``Measurement`` whose ``score`` is the number of
categories above the 0.5 confidence threshold.

The ontology path defaults to the most recently modified JSON under
``<runs_dir>/<scenario>/_ontology/`` (derived from ``run_dir``);
``--ontology-path`` only needs to be passed to pin to a specific
version.

Scenario-agnostic: the metric calls
``scenario.build_communication_rounds(events)`` and only sees
``CommunicationRoundView`` rows. Scenarios that do not implement the
hook return ``[]`` and the metric quietly skips with no Measurement.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from glossogen.evaluation.log_reader import extract_simulation_id
from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metrics.communication.label_models import (
    CommunicationFeaturePresenceOutput,
    CommunicationFeaturePresenceSidecar,
    CommunicationOntology,
    ontology_dir_for_scenario,
)
from glossogen.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from glossogen.llm.provider import LLMMessage, LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_SIDECAR_FILENAME = "communication_feature_presence.json"
_PRESENCE_THRESHOLD = 0.5


class CommunicationFeaturePresenceMetric(Metric):
    """Scores each ontology category's presence on one run's primary-channel messages."""

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
        _ = agent_configs
        if options.ontology_path is None:
            ontology_path = _resolve_latest_ontology_path(
                run_dir=run_dir, scenario_name=scenario.name()
            )
            logger.info(
                "communication_feature_presence: auto-resolved ontology to %s",
                ontology_path,
            )
        else:
            ontology_path = options.ontology_path
            if not ontology_path.exists():
                raise FileNotFoundError(f"Ontology file not found: {ontology_path}")
        ontology = CommunicationOntology.model_validate_json(
            ontology_path.read_text(encoding="utf-8")
        )
        if not ontology.categories:
            raise ValueError(f"Ontology at {ontology_path} has no categories")

        rounds = scenario.build_communication_rounds(events=events)
        if not rounds:
            logger.info(
                "%s: skipping — scenario %s produced no communication rounds",
                self.name,
                scenario.name(),
            )
            return []

        judge_prompt = render_evaluator_prompt(
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


def _resolve_latest_ontology_path(run_dir: Path, scenario_name: str) -> Path:
    """Return the most recently modified ontology JSON for ``scenario_name``.

    ``run_dir`` is ``<runs_dir>/<scenario_name>/<timestamp>``, so the
    scenario's ontology directory is ``run_dir.parent / _ontology``.
    Raises :class:`FileNotFoundError` when the directory is missing or
    contains no JSON files.
    """
    scenario_ontology_dir = ontology_dir_for_scenario(
        runs_dir=run_dir.parent.parent, scenario_name=scenario_name
    )
    candidates = sorted(
        scenario_ontology_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No --ontology-path supplied and no ontology JSON found under "
            f"{scenario_ontology_dir}. Run "
            f"`scripts/consolidate_communication_ontology.py` first."
        )
    return candidates[0]
