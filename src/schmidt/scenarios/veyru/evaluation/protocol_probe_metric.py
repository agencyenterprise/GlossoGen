"""Probes each agent's communication protocol with a fixed bank of hypothetical inputs.

For every probe question matching an agent's role, reconstructs that agent's
pydantic-ai message history from the run's JSONL log (optionally cut at a
specific round), then runs ``probe_replicas`` independent ``agent.run(...)``
calls under the agent's original model. Each call uses
``ProtocolProbeOutput`` as its structured output schema and contributes one
row to ``protocol_probe_responses.jsonl`` inside the run directory. Each
replica is independent — the same reconstructed history is reused, giving
the natural "rollback before next question" semantics.

Returns a single ``Measurement`` whose ``score`` is the count of probes
written. Distance / similarity computation across the resulting JSONL is
out of scope for this metric and lives in downstream analysis.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage

from schmidt.evaluation.evaluation_cost import EvaluationTokenUsage, compute_evaluation_cost
from schmidt.evaluation.measurement import Measurement
from schmidt.evaluation.metric_protocol import Metric
from schmidt.evaluation.metric_run_options import MetricRunOptions
from schmidt.evaluation.protocol_probe_response import (
    ProtocolProbeResponse,
    ProtocolProbeUsageReport,
)
from schmidt.llm.provider import LLMProvider
from schmidt.message_history_builder import build_message_history
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.runners.communication_protocol import build_full_system_prompt
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.probe_agent import run_protocol_probe
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_A_ROLE,
    FIELD_OBSERVER_B_ROLE,
    FIELD_OBSERVER_ROLE,
    STABILIZATION_ENGINEER_A_ROLE,
    STABILIZATION_ENGINEER_B_ROLE,
    STABILIZATION_ENGINEER_ROLE,
)
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

_PROBE_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "probe"
_TEST_BANK_PATH = Path(__file__).resolve().parent.parent / "protocol_probe_questions.json"
_RESPONSES_FILE_NAME = "protocol_probe_responses.jsonl"
_USAGE_FILE_NAME = "protocol_probe_usage.json"

_ROLE_FILTER_TO_ROLE_NAMES: dict[str, frozenset[str]] = {
    "field_observer": frozenset(
        {FIELD_OBSERVER_ROLE, FIELD_OBSERVER_A_ROLE, FIELD_OBSERVER_B_ROLE}
    ),
    "stabilization_engineer": frozenset(
        {
            STABILIZATION_ENGINEER_ROLE,
            STABILIZATION_ENGINEER_A_ROLE,
            STABILIZATION_ENGINEER_B_ROLE,
        }
    ),
}

_ROLE_FILTER_TO_TEMPLATE: dict[str, str] = {
    "field_observer": "field_observer_probe.jinja",
    "stabilization_engineer": "engineer_probe.jinja",
}


class ProbeQuestion(BaseModel):
    """One entry in the frozen test bank file."""

    id: str
    agent_role_filter: str
    inputs: dict[str, str]


class ProtocolProbeMetric(Metric):
    """Probes each agent with a fixed test bank, optionally cut at a round.

    ``options.probe_round=None`` reconstructs the full end-of-run history.
    Setting ``options.probe_round=R`` drops every tool call whose
    ``round_number >= R``, so the reconstructed history covers rounds
    ``1..R-1`` (inclusive). To probe the agent at the END of round R,
    pass ``options.probe_round=R+1``. Common pitfall: ``probe_round=15``
    captures the state through round 14, NOT through round 15.

    Each replica runs the same reconstructed history through one
    ``agent.run(...)`` call — independent of every other replica — and
    appends one row to ``protocol_probe_responses.jsonl``.
    """

    name = "protocol_probe"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Probe matching agents on the test bank and stream rows to the JSONL."""
        _ = scenario, llm_provider
        if options.probe_replicas is None or options.probe_replicas < 1:
            raise ValueError("protocol_probe requires --probe-replicas N with N >= 1")
        probe_round = options.probe_round
        probe_replicas = options.probe_replicas
        renderer = TemplateRenderer(prompts_dirs=[_PROBE_PROMPTS_DIR])
        questions = _load_test_bank()
        responses_path = run_dir / _RESPONSES_FILE_NAME
        target_timestamp = _resolve_history_timestamp(events=events)

        rows_written = 0
        usage_by_model: dict[tuple[str, str], EvaluationTokenUsage] = {}
        with responses_path.open("a", encoding="utf-8") as responses_file:
            for question in questions:
                matching_agents = _match_agents(
                    agent_configs=agent_configs,
                    role_filter=question.agent_role_filter,
                )
                if not matching_agents:
                    logger.info(
                        "Skipping question %s: no agents match role filter %r",
                        question.id,
                        question.agent_role_filter,
                    )
                    continue
                template_name = _ROLE_FILTER_TO_TEMPLATE[question.agent_role_filter]
                probe_prompt = renderer.render(
                    template_name=template_name,
                    template_variables=dict(question.inputs),
                )
                for agent_config in matching_agents:
                    full_system_prompt = build_full_system_prompt(
                        base_prompt=agent_config.system_prompt,
                        role_name=agent_config.role_name,
                    )
                    history = build_message_history(
                        events=events,
                        agent_id=agent_config.agent_id,
                        system_prompt=full_system_prompt,
                        target_timestamp=target_timestamp,
                        cutoff_round=probe_round,
                        tool_calls_only=False,
                        channel_visibility={},
                    )
                    if not history:
                        logger.warning(
                            "Skipping question %s for agent %s: empty reconstructed history",
                            question.id,
                            agent_config.agent_id,
                        )
                        continue
                    rows_written += await self._run_replicas_for_agent(
                        agent_config=agent_config,
                        full_system_prompt=full_system_prompt,
                        history=history,
                        probe_prompt=probe_prompt,
                        question=question,
                        probe_round=probe_round,
                        probe_replicas=probe_replicas,
                        responses_file=responses_file,
                        usage_by_model=usage_by_model,
                    )

        usage_report = _build_usage_report(usage_by_model=usage_by_model)
        usage_path = run_dir / _USAGE_FILE_NAME
        usage_path.write_text(usage_report.model_dump_json(indent=2) + "\n")
        summary = (
            f"Collected {rows_written} probe responses across "
            f"{len(questions)} questions × {probe_replicas} replica(s); "
            f"written to {responses_path.name}; "
            f"probe LLM cost ${usage_report.total_estimated_cost_usd:.4f} "
            f"(see {usage_path.name})"
        )
        return [
            Measurement(
                metric_name=self.name,
                score=float(rows_written),
                score_unit="probe responses",
                summary=summary,
                per_round=[],
                per_agent=[],
            )
        ]

    async def _run_replicas_for_agent(
        self,
        agent_config: AgentConfig,
        full_system_prompt: str,
        history: list[ModelMessage],
        probe_prompt: str,
        question: ProbeQuestion,
        probe_round: int | None,
        probe_replicas: int,
        responses_file: TextIO,
        usage_by_model: dict[tuple[str, str], EvaluationTokenUsage],
    ) -> int:
        """Run the configured number of replicas for one (agent, question) pair."""
        rows_written = 0
        for replica_index in range(1, probe_replicas + 1):
            try:
                call_result = await run_protocol_probe(
                    agent_id=agent_config.agent_id,
                    role_name=agent_config.role_name,
                    full_system_prompt=full_system_prompt,
                    model=agent_config.model,
                    provider=agent_config.provider,
                    message_history=history,
                    probe_prompt=probe_prompt,
                )
            except Exception:
                logger.exception(
                    "Probe failed for agent=%s question=%s replica=%d",
                    agent_config.agent_id,
                    question.id,
                    replica_index,
                )
                continue
            _accumulate_usage(
                usage_by_model=usage_by_model,
                model=agent_config.model,
                provider=agent_config.provider,
                call_usage=call_result.usage,
            )
            row = ProtocolProbeResponse(
                timestamp=datetime.now(tz=timezone.utc),
                replica_index=replica_index,
                agent_id=agent_config.agent_id,
                role_name=agent_config.role_name,
                model=agent_config.model,
                provider=agent_config.provider,
                question_id=question.id,
                question_role_filter=question.agent_role_filter,
                cutoff_round=probe_round,
                reasoning_text=call_result.output.reasoning,
                response_text=call_result.output.message,
            )
            responses_file.write(row.model_dump_json() + "\n")
            responses_file.flush()
            rows_written += 1
        return rows_written


def _load_test_bank() -> list[ProbeQuestion]:
    """Read the frozen test bank JSON and validate each entry."""
    raw = json.loads(_TEST_BANK_PATH.read_text(encoding="utf-8"))
    return [ProbeQuestion.model_validate(entry) for entry in raw]


def _match_agents(
    agent_configs: list[AgentConfig],
    role_filter: str,
) -> list[AgentConfig]:
    """Return one matching ``AgentConfig`` per distinct ``agent_id``.

    Cross-run replace-agent runs emit multiple ``AgentRegistered`` events
    for the same ``agent_id`` (one for the original agent, one for the
    imported agent at the swap point). Without dedup the metric would
    probe each ``agent_id`` once per registration, inflating the replica
    count. The latest registration wins (it carries the post-swap system
    prompt the probe should be reasoning under).
    """
    role_names = _ROLE_FILTER_TO_ROLE_NAMES.get(role_filter)
    if role_names is None:
        return []
    by_agent_id: dict[str, AgentConfig] = {}
    for config in agent_configs:
        if config.role_name in role_names:
            by_agent_id[config.agent_id] = config
    return list(by_agent_id.values())


def _resolve_history_timestamp(events: list[SimulationEvent]) -> datetime:
    """Pick a ``target_timestamp`` for ``build_message_history`` that keeps every event.

    When ``cutoff_round`` is set, ``target_timestamp`` is ignored. When it is
    ``None`` (end-of-run probe), ``target_timestamp`` is the latest event's
    timestamp so no calls are dropped by timestamp filtering.
    """
    if not events:
        return datetime.now(tz=timezone.utc)
    return events[-1].timestamp


def _accumulate_usage(
    usage_by_model: dict[tuple[str, str], EvaluationTokenUsage],
    model: str,
    provider: str,
    call_usage: EvaluationTokenUsage,
) -> None:
    """Increment the per-(model, provider) running totals by one probe call's usage."""
    key = (model, provider)
    existing = usage_by_model.get(key)
    if existing is None:
        usage_by_model[key] = call_usage
        return
    usage_by_model[key] = EvaluationTokenUsage(
        input_tokens=existing.input_tokens + call_usage.input_tokens,
        output_tokens=existing.output_tokens + call_usage.output_tokens,
        cache_read_input_tokens=existing.cache_read_input_tokens
        + call_usage.cache_read_input_tokens,
        cache_creation_input_tokens=existing.cache_creation_input_tokens
        + call_usage.cache_creation_input_tokens,
    )


def _build_usage_report(
    usage_by_model: dict[tuple[str, str], EvaluationTokenUsage],
) -> ProtocolProbeUsageReport:
    """Compute per-model cost and aggregate the run total."""
    per_model = [
        compute_evaluation_cost(usage=usage, model=model, provider_name=provider)
        for (model, provider), usage in usage_by_model.items()
    ]
    total = sum(entry.estimated_cost_usd for entry in per_model)
    return ProtocolProbeUsageReport(
        total_estimated_cost_usd=total,
        per_model=per_model,
    )
