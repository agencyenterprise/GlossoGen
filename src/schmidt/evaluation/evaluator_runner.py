"""Orchestrates evaluation of a completed simulation.

Loads simulation events from a JSONL log file, runs a set of named evaluators
against those events, and writes the resulting evaluation report to disk.
"""

import logging
from pathlib import Path

import aiofiles
import orjson
from pydantic import TypeAdapter

from schmidt.evaluation.cooperation_evaluator import CooperationEvaluator
from schmidt.evaluation.evaluation_report import EvaluationReport
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.instruction_adherence import InstructionAdherenceEvaluator
from schmidt.evaluation.secret_leak_evaluator import SecretLeakEvaluator
from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentRegistered, SimulationEvent, SimulationStarted
from schmidt.scenario_loader import load_scenario

logger = logging.getLogger(__name__)

EVALUATOR_REGISTRY: dict[str, type[Evaluator]] = {
    "secret_leak": SecretLeakEvaluator,
    "instruction_adherence": InstructionAdherenceEvaluator,
    "cooperation": CooperationEvaluator,
}

_EVENT_ADAPTER: TypeAdapter[SimulationEvent] = TypeAdapter(SimulationEvent)


def _parse_event(raw: dict[str, object]) -> SimulationEvent:
    """Validate and deserialize a raw dictionary into a typed
    SimulationEvent using the discriminated union adapter.
    """
    return _EVENT_ADAPTER.validate_python(raw)


async def load_events(log_path: Path) -> list[SimulationEvent]:
    """Read a JSONL log file and parse each line into a typed SimulationEvent."""
    events: list[SimulationEvent] = []
    async with aiofiles.open(log_path, mode="rb") as f:
        async for line in f:
            line = line.strip()
            if not line:
                continue
            raw = orjson.loads(line)
            event = _parse_event(raw=raw)
            events.append(event)
    logger.info("Loaded %d events from %s", len(events), log_path)
    return events


def extract_agent_configs(events: list[SimulationEvent]) -> list[AgentConfig]:
    """Extract AgentConfig entries from AgentRegistered events in the event list."""
    configs: list[AgentConfig] = []
    for event in events:
        if isinstance(event, AgentRegistered):
            configs.append(
                AgentConfig(
                    agent_id=event.agent_id,
                    role_name=event.role_name,
                    system_prompt=event.system_prompt,
                    channel_ids=event.channel_ids,
                    tool_names=event.tool_names,
                )
            )
    return configs


async def run_evaluation(
    log_path: Path,
    scenario_name: str,
    evaluator_names: list[str],
    report_path: Path,
    model: str,
) -> EvaluationReport:
    """Load simulation events, run the specified evaluators, and write the report as JSON.

    Raises ValueError if an evaluator name is not found in EVALUATOR_REGISTRY.
    """
    logger.info(
        "Starting evaluation: scenario=%s, evaluators=%s, model=%s",
        scenario_name,
        evaluator_names,
        model,
    )
    events = await load_events(log_path=log_path)
    agent_configs = extract_agent_configs(events=events)

    scenario = load_scenario(name=scenario_name)
    provider = ClaudeProvider(model=model)

    simulation_id: str | None = None
    for event in events:
        if isinstance(event, SimulationStarted):
            simulation_id = event.event_id
            break
    if simulation_id is None:
        raise ValueError(f"No SimulationStarted event found in {log_path}")

    metrics = []
    for name in evaluator_names:
        if name not in EVALUATOR_REGISTRY:
            available = ", ".join(sorted(EVALUATOR_REGISTRY.keys()))
            raise ValueError(f"Unknown evaluator: '{name}'. Available: {available}")
        evaluator = EVALUATOR_REGISTRY[name]()
        logger.info("Running evaluator: %s", name)
        result = await evaluator.evaluate(
            events=events,
            agent_configs=agent_configs,
            scenario=scenario,
            llm_provider=provider,
        )
        logger.info(
            "Evaluator %s finished: verdict=%s, score=%.2f", name, result.verdict, result.score
        )
        metrics.append(result)

    report = EvaluationReport(
        simulation_id=simulation_id,
        scenario_name=scenario_name,
        metrics=metrics,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(report_path, mode="wb") as f:
        await f.write(orjson.dumps(report.model_dump(mode="json"), option=orjson.OPT_INDENT_2))

    logger.info("Evaluation report written to %s", report_path)
    return report
