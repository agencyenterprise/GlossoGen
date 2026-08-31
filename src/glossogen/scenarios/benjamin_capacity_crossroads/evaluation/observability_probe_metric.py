"""Held-out K1 probe for represented external focal-status reachability."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from glossogen.evaluation.metric_core.measurement import AgentObservation, Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metrics.protocol_probe.probe_agent import run_structured_probe
from glossogen.evaluation.reports.evaluation_cost import EvaluationTokenUsage
from glossogen.llm.provider import LLMProvider
from glossogen.message_history_builder import build_message_history, resolve_history_timestamp
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEnded, SimulationEvent
from glossogen.runners.communication_protocol import build_full_system_prompt, continue_prompt_for
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.benjamin_atomic_inventory.evaluation.observability_probe_metric import (
    WorkItemDestinationInventoryOutput,
    classify_destination_scope,
    identifies_exact_destination,
    work_item_order_for_seed,
)
from glossogen.scenarios.benjamin_capacity_crossroads.evaluation.metric_names import (
    BENJAMIN_CAPACITY_CROSSROADS_OBSERVABILITY_PROBE,
)
from glossogen.scenarios.benjamin_capacity_crossroads.knobs import (
    BenjaminCapacityCrossroadsKnobs,
    ObservationMode,
    RunMode,
)
from glossogen.scenarios.benjamin_capacity_crossroads.world import TARGET_STATUS_ID
from glossogen.scenarios.benjamin_release_pipeline.ids import DEVELOPER_ID
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parents[1] / "prompts"
RESPONSES_FILE_NAME = "benjamin_capacity_crossroads_probe_response.json"
USAGE_FILE_NAME = "benjamin_capacity_crossroads_probe_usage.json"


class ObservabilityProbeResponse(BaseModel):
    """Auditable sidecar for one post-decision K1 call."""

    timestamp: datetime
    agent_id: str
    model: str
    provider: str
    observation: str
    work_item_order: list[str]
    output: WorkItemDestinationInventoryOutput


class ObservabilityProbeUsage(BaseModel):
    """Token usage sidecar for one post-decision K1 call."""

    model: str
    provider: str
    usage: EvaluationTokenUsage


class BenjaminCapacityCrossroadsObservabilityProbeMetric(Metric):
    """Probe whether the focal status is represented as externally observable."""

    name = BENJAMIN_CAPACITY_CROSSROADS_OBSERVABILITY_PROBE

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Run one source-aligned K1 probe against the Developer's final history."""
        _ = llm_provider, options
        if scenario.name() != "benjamin_capacity_crossroads":
            return []
        knobs = BenjaminCapacityCrossroadsKnobs.model_validate(
            scenario.get_scenario_config()
        )
        if knobs.run_mode != RunMode.VISIBILITY_PROBE:
            logger.info("%s: skipping non-held-out behavioral run", self.name)
            return []
        if not any(isinstance(event, SimulationEnded) for event in events):
            logger.warning("%s: run has no simulation_ended event; skipping", self.name)
            return []
        developer = next(
            (config for config in reversed(agent_configs) if config.agent_id == DEVELOPER_ID),
            None,
        )
        if developer is None:
            logger.warning("%s: no developer agent config; skipping", self.name)
            return []
        full_system_prompt = build_full_system_prompt(
            base_prompt=developer.system_prompt,
            role_name=developer.role_name,
            communication_enabled=developer.communication_enabled,
            communication_required=developer.communication_required,
        )
        history = build_message_history(
            events=events,
            agent_id=developer.agent_id,
            system_prompt=full_system_prompt,
            target_timestamp=resolve_history_timestamp(events=events),
            cutoff_round=None,
            tool_calls_only=False,
            channel_visibility={},
            split_parallel_tool_calls=False,
            continue_prompt=continue_prompt_for(
                communication_enabled=developer.communication_enabled,
                communication_required=developer.communication_required,
            ),
        )
        if not history:
            logger.warning("%s: reconstructed history is empty; skipping", self.name)
            return []
        work_item_order = work_item_order_for_seed(seed=knobs.seed)
        renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        probe_prompt = renderer.render(
            template_name="observability_probe.jinja",
            template_variables={"work_item_order": work_item_order},
        )
        call = await run_structured_probe(
            agent_id=developer.agent_id,
            role_name=developer.role_name,
            full_system_prompt=full_system_prompt,
            model=developer.model,
            provider=developer.provider,
            message_history=history,
            user_prompt_parts=[probe_prompt],
            output_type=WorkItemDestinationInventoryOutput,
        )
        response = ObservabilityProbeResponse(
            timestamp=datetime.now(tz=timezone.utc),
            agent_id=developer.agent_id,
            model=developer.model,
            provider=developer.provider,
            observation=knobs.observation.value,
            work_item_order=work_item_order,
            output=call.output,
        )
        (run_dir / RESPONSES_FILE_NAME).write_text(
            response.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        usage = ObservabilityProbeUsage(
            model=developer.model,
            provider=developer.provider,
            usage=call.usage,
        )
        (run_dir / USAGE_FILE_NAME).write_text(
            usage.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        target = next(
            answer for answer in call.output.records if answer.work_item_id == TARGET_STATUS_ID
        )
        represented_scope = classify_destination_scope(answer=target)
        expected_scope = "local"
        if knobs.observation == ObservationMode.OBSERVED:
            expected_scope = "external"
        correct = represented_scope == expected_scope
        exact_destination = identifies_exact_destination(
            answer=target,
            observation=knobs.observation,
        )
        scope_value = -1.0
        if represented_scope == "local":
            scope_value = 0.0
        if represented_scope == "external":
            scope_value = 1.0
        return [
            Measurement(
                metric_name=self.name,
                score=float(correct),
                score_unit="binary correct external-observability class",
                summary=(
                    f"represented_scope={represented_scope}; "
                    f"expected_scope={expected_scope}; "
                    f"exact_destination_secondary={exact_destination}; "
                    f"correct={correct}"
                ),
                per_round=[],
                per_agent=[
                    AgentObservation(
                        agent_id=developer.agent_id,
                        value=scope_value,
                        note=(
                            f"destinations={target.destinations}; "
                            f"exact_destination_secondary={exact_destination}"
                        ),
                    )
                ],
            )
        ]
