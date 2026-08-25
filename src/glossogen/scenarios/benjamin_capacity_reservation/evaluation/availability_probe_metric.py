"""Held-out K1 probe for external availability of the private allocation."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, model_validator

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
from glossogen.scenarios.benjamin_capacity_reservation.evaluation.metric_names import (
    BENJAMIN_CAPACITY_AVAILABILITY_PROBE_METRIC,
)
from glossogen.scenarios.benjamin_capacity_reservation.ids import (
    BATCH_WINDOW_STATUS_ID,
    DEVELOPER_ID,
    DEVELOPER_RECEIPT_ID,
    TARGET_ALLOCATION_ID,
)
from glossogen.scenarios.benjamin_capacity_reservation.knobs import (
    BenjaminCapacityReservationKnobs,
    ObservationMode,
    RunMode,
)
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parents[1] / "prompts"
RESPONSES_FILE_NAME = "benjamin_capacity_availability_probe_response.json"
USAGE_FILE_NAME = "benjamin_capacity_availability_probe_usage.json"

ProcessItemId = Literal[
    "partner_capacity_reserved",
    "batch_window_status",
    "developer_allocation_receipt",
]


class ProcessItemAvailabilityAnswer(BaseModel):
    """One process item and its represented post-shift availability."""

    process_item_id: ProcessItemId
    available_to_role_besides_developer: bool | None
    role_or_location: str


class ProcessAvailabilityInventoryOutput(BaseModel):
    """Exact target-plus-foils output schema for the K1 probe."""

    items: list[ProcessItemAvailabilityAnswer]

    @model_validator(mode="after")
    def validate_item_set(self) -> Self:
        """Require one answer for the target and each foil."""
        expected = {
            TARGET_ALLOCATION_ID,
            BATCH_WINDOW_STATUS_ID,
            DEVELOPER_RECEIPT_ID,
        }
        received = {answer.process_item_id for answer in self.items}
        if len(self.items) != len(expected) or received != expected:
            raise ValueError("items must contain each displayed process item exactly once")
        return self


class AvailabilityProbeResponse(BaseModel):
    """Auditable sidecar for one held-out K1 call."""

    timestamp: datetime
    agent_id: str
    model: str
    provider: str
    observation: str
    process_item_order: list[str]
    output: ProcessAvailabilityInventoryOutput


class AvailabilityProbeUsage(BaseModel):
    """Token usage sidecar for one held-out K1 call."""

    model: str
    provider: str
    usage: EvaluationTokenUsage


class BenjaminCapacityAvailabilityProbeMetric(Metric):
    """Probe whether the private allocation is represented as externally available."""

    name = BENJAMIN_CAPACITY_AVAILABILITY_PROBE_METRIC

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
        if scenario.name() != "benjamin_capacity_reservation":
            return []
        knobs = BenjaminCapacityReservationKnobs.model_validate(scenario.get_scenario_config())
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
            logger.warning("%s: no Developer agent config; skipping", self.name)
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
        process_item_order = process_item_order_for_seed(seed=knobs.seed)
        renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        probe_prompt = renderer.render(
            template_name="availability_probe.jinja",
            template_variables={"process_item_order": process_item_order},
        )
        call = await run_structured_probe(
            agent_id=developer.agent_id,
            role_name=developer.role_name,
            full_system_prompt=full_system_prompt,
            model=developer.model,
            provider=developer.provider,
            message_history=history,
            user_prompt_parts=[probe_prompt],
            output_type=ProcessAvailabilityInventoryOutput,
        )
        response = AvailabilityProbeResponse(
            timestamp=datetime.now(tz=timezone.utc),
            agent_id=developer.agent_id,
            model=developer.model,
            provider=developer.provider,
            observation=knobs.observation.value,
            process_item_order=process_item_order,
            output=call.output,
        )
        (run_dir / RESPONSES_FILE_NAME).write_text(
            response.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        usage = AvailabilityProbeUsage(
            model=developer.model,
            provider=developer.provider,
            usage=call.usage,
        )
        (run_dir / USAGE_FILE_NAME).write_text(
            usage.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        target = next(
            answer for answer in call.output.items if answer.process_item_id == TARGET_ALLOCATION_ID
        )
        expected_external = knobs.observation == ObservationMode.OBSERVED
        represented_external = target.available_to_role_besides_developer
        correct = represented_external is not None and represented_external == expected_external
        exact_recipient = identifies_exact_recipient(
            answer=target,
            observation=knobs.observation,
        )
        represented_value = -1.0
        if represented_external is False:
            represented_value = 0.0
        if represented_external is True:
            represented_value = 1.0
        return [
            Measurement(
                metric_name=self.name,
                score=float(correct),
                score_unit="binary correct external-availability status",
                summary=(
                    f"represented_external={represented_external}; "
                    f"expected_external={expected_external}; "
                    f"exact_recipient_secondary={exact_recipient}; correct={correct}"
                ),
                per_round=[],
                per_agent=[
                    AgentObservation(
                        agent_id=developer.agent_id,
                        value=represented_value,
                        note=(
                            f"role_or_location={target.role_or_location}; "
                            f"exact_recipient_secondary={exact_recipient}"
                        ),
                    )
                ],
            )
        ]


def process_item_order_for_seed(seed: int) -> list[str]:
    """Rotate the target among two foils using the frozen world seed."""
    items = [TARGET_ALLOCATION_ID, BATCH_WINDOW_STATUS_ID, DEVELOPER_RECEIPT_ID]
    shift = seed % len(items)
    return items[shift:] + items[:shift]


def identifies_exact_recipient(
    answer: ProcessItemAvailabilityAnswer,
    observation: ObservationMode,
) -> bool:
    """Record exact recipient recall as a non-gating secondary diagnostic."""
    normalized = " ".join(
        answer.role_or_location.lower().replace("_", " ").replace("-", " ").split()
    )
    if observation == ObservationMode.OBSERVED:
        return "capacity" in normalized and "review" in normalized
    return normalized in {"developer", "developer only", "none", "not available"}
