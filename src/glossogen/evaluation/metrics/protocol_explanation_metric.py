"""Generic metric that asks each agent to describe its communication protocol.

For every agent in the run, reconstructs that agent's end-of-run pydantic-ai
message history (applying the replace-agent channel-visibility filter when the
agent was the one swapped in via ``replace-agent``) and runs one structured
``run_structured_probe`` call (``output_type=ProtocolExplanationOutput``) asking
the agent to explain the protocol it actually remembers using. Each agent is
probed under its own original model/provider, so the answer is the agent's own
account of the protocol — not a third party's.

When the scenario implements ``get_protocol_explanation_config``, the metric
renders that scenario's per-role prose template (grounded in the scenario's
communication setup) for each matching agent; otherwise it falls back to a
generic prompt, so the metric runs on any scenario where agents communicate.

Each agent's free-text answer is written to ``per_agent[i].note`` and to one row
of ``protocol_explanation_responses.jsonl`` in the run directory; per-(model,
provider) token cost goes to ``protocol_explanation_usage.json``. The overall
``score`` is the number of agents probed. Returns an empty list when no agent
has any reconstructable history (e.g. a run that crashed before the first turn).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from glossogen.evaluation.metric_core.measurement import AgentObservation, Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.protocol_explanation_config import ProtocolExplanationConfig
from glossogen.evaluation.metrics.probe_usage_report import (
    accumulate_probe_usage,
    build_probe_usage_report,
)
from glossogen.evaluation.metrics.protocol_probe.probe_agent import run_structured_probe
from glossogen.evaluation.reports.evaluation_cost import EvaluationTokenUsage
from glossogen.llm.provider import LLMProvider
from glossogen.message_history_builder import build_message_history
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.replace_manifest import ReplaceManifest, read_replace_manifest
from glossogen.runners.communication_protocol import build_full_system_prompt
from glossogen.runtime.scheduled_events import (
    ChannelVisibility,
    ChannelVisibilityFromRound,
    ChannelVisibilityFull,
    ChannelVisibilityNone,
)
from glossogen.scenario_protocol import SimulationScenario
from glossogen.template_renderer import TemplateRenderer
from glossogen.token_pricing import SELF_HOSTED_PROVIDER

logger = logging.getLogger(__name__)

_RESPONSES_FILE_NAME = "protocol_explanation_responses.jsonl"
_USAGE_FILE_NAME = "protocol_explanation_usage.json"

_GENERIC_PROBE_PROMPT = (
    "Explain in detail the communication protocol your team has been using "
    "throughout this simulation. Cover the formats and conventions for the "
    "messages you exchange, any abbreviations or codes you've agreed on, the "
    "meta-agreements about how to communicate, and any edge-case rules. Quote "
    "specific examples if you remember them. Be concrete — describe the "
    "protocol as it actually is, not as it could be. If your team did not "
    "develop any meaningful protocol, say so explicitly."
)


class ProtocolExplanationOutput(BaseModel):
    """Structured output the probed agent must emit: a prose protocol description."""

    description: str = Field(
        description=(
            "A thorough, concrete prose description of the communication protocol "
            "your team actually developed: the abbreviations, codes, or symbols you "
            "use and exactly what each means; how you structure a typical message; "
            "how you signal failure or retry; and any conventions you negotiated. "
            "Quote specific examples you remember. If your team did not develop any "
            "meaningful protocol, say so explicitly."
        )
    )


class ProtocolExplanationResponse(BaseModel):
    """One row in ``protocol_explanation_responses.jsonl``.

    ``template_name`` records which scenario template produced the prompt, or
    ``None`` when the agent's role was not covered by the scenario config and
    the generic prompt was used.
    """

    timestamp: datetime
    agent_id: str
    role_name: str
    model: str
    provider: str
    template_name: str | None
    description_text: str


class _ResolvedPrompt(NamedTuple):
    """The probe prompt for one agent plus the template that produced it."""

    prompt_text: str
    template_name: str | None


class ProtocolExplanationMetric(Metric):
    """Probe each agent to describe the communication protocol it remembers."""

    name = "protocol_explanation"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Probe every agent under its original model for a protocol explanation."""
        _ = llm_provider, options
        if not events:
            return []

        manifest = read_replace_manifest(run_dir=run_dir)
        target_timestamp = _last_event_timestamp(events=events)
        latest_per_agent = _dedupe_latest_registration(agent_configs=agent_configs)

        config = scenario.get_protocol_explanation_config()
        renderer = _build_renderer(config=config)
        role_to_template = _build_role_template_map(config=config)

        observations: list[AgentObservation] = []
        rows: list[ProtocolExplanationResponse] = []
        usage_by_model: dict[tuple[str, str], EvaluationTokenUsage] = {}
        for agent in latest_per_agent:
            channel_visibility = _resolve_channel_visibility(
                manifest=manifest,
                agent_id=agent.agent_id,
            )
            full_system_prompt = build_full_system_prompt(
                base_prompt=agent.system_prompt,
                role_name=agent.role_name,
            )
            history = build_message_history(
                events=events,
                agent_id=agent.agent_id,
                system_prompt=full_system_prompt,
                target_timestamp=target_timestamp,
                cutoff_round=None,
                tool_calls_only=False,
                channel_visibility=channel_visibility,
                split_parallel_tool_calls=agent.provider == SELF_HOSTED_PROVIDER,
            )
            if not history:
                logger.info(
                    "%s: skipping %s — empty reconstructed history",
                    self.name,
                    agent.agent_id,
                )
                continue
            resolved = _resolve_probe_prompt(
                renderer=renderer,
                role_to_template=role_to_template,
                role_name=agent.role_name,
            )
            try:
                probe = await run_structured_probe(
                    agent_id=agent.agent_id,
                    role_name=agent.role_name,
                    full_system_prompt=full_system_prompt,
                    model=agent.model,
                    provider=agent.provider,
                    message_history=history,
                    user_prompt_parts=[resolved.prompt_text],
                    output_type=ProtocolExplanationOutput,
                )
            except Exception:
                logger.exception(
                    "%s: probe failed for agent=%s (model=%s provider=%s); skipping",
                    self.name,
                    agent.agent_id,
                    agent.model,
                    agent.provider,
                )
                continue
            accumulate_probe_usage(
                usage_by_model=usage_by_model,
                model=agent.model,
                provider=agent.provider,
                call_usage=probe.usage,
            )
            rows.append(
                ProtocolExplanationResponse(
                    timestamp=datetime.now(tz=timezone.utc),
                    agent_id=agent.agent_id,
                    role_name=agent.role_name,
                    model=agent.model,
                    provider=agent.provider,
                    template_name=resolved.template_name,
                    description_text=probe.output.description,
                )
            )
            observations.append(
                AgentObservation(
                    agent_id=agent.agent_id,
                    value=float(len(history)),
                    note=probe.output.description,
                )
            )

        if not observations:
            return []

        _write_responses(run_dir=run_dir, rows=rows)
        usage_report = build_probe_usage_report(usage_by_model=usage_by_model)
        (run_dir / _USAGE_FILE_NAME).write_text(usage_report.model_dump_json(indent=2) + "\n")

        score = float(len(observations))
        summary = (
            f"Probed {len(observations)} agent(s) for a protocol explanation; "
            f"answers written to {_RESPONSES_FILE_NAME} and per_agent[].note; "
            f"probe LLM cost ${usage_report.total_estimated_cost_usd:.4f}."
        )
        return [
            Measurement(
                metric_name=self.name,
                score=score,
                score_unit="agents probed",
                summary=summary,
                per_round=[],
                per_agent=observations,
            )
        ]


def _build_renderer(config: ProtocolExplanationConfig | None) -> TemplateRenderer | None:
    """Build a renderer over the scenario's template dir, or ``None`` when no config."""
    if config is None:
        return None
    return TemplateRenderer(prompts_dirs=[config.prompts_dir])


def _build_role_template_map(config: ProtocolExplanationConfig | None) -> dict[str, str]:
    """Invert ``role_groups`` + ``role_templates`` into a role-name → template-name lookup.

    Only role names whose role filter has a registered template are included;
    every other agent falls back to the generic prompt.
    """
    if config is None:
        return {}
    mapping: dict[str, str] = {}
    for role_filter, role_names in config.role_groups.items():
        template_name = config.role_templates.get(role_filter)
        if template_name is None:
            continue
        for role_name in role_names:
            mapping[role_name] = template_name
    return mapping


def _resolve_probe_prompt(
    renderer: TemplateRenderer | None,
    role_to_template: dict[str, str],
    role_name: str,
) -> _ResolvedPrompt:
    """Render the scenario template for this role, or fall back to the generic prompt."""
    template_name = role_to_template.get(role_name)
    if renderer is None or template_name is None:
        return _ResolvedPrompt(prompt_text=_GENERIC_PROBE_PROMPT, template_name=None)
    prompt_text = renderer.render(template_name=template_name, template_variables={})
    return _ResolvedPrompt(prompt_text=prompt_text, template_name=template_name)


def _write_responses(run_dir: Path, rows: list[ProtocolExplanationResponse]) -> None:
    """Overwrite the responses JSONL with one line per probed agent."""
    lines = [row.model_dump_json() for row in rows]
    (run_dir / _RESPONSES_FILE_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_channel_visibility(
    manifest: ReplaceManifest | None,
    agent_id: str,
) -> dict[str, ChannelVisibility]:
    """Return the visibility filter to apply to this agent's reconstructed history.

    For the agent that was swapped in via ``replace-agent`` we apply the same
    channel-visibility map the runtime applied at resume time (so postmortem
    reads and out-of-window link sends are stripped). Every other agent gets
    an empty filter — full reconstruction.
    """
    if manifest is None or manifest.replaced_agent_id != agent_id:
        return {}
    visibility: dict[str, ChannelVisibility] = {}
    for channel_id in manifest.channels_with_visible_history:
        floor = manifest.channel_history_floors.get(channel_id)
        if floor is None:
            visibility[channel_id] = ChannelVisibilityFull()
        else:
            visibility[channel_id] = ChannelVisibilityFromRound(round_floor=floor)
    for channel_id in manifest.blocked_tool_call_channels:
        visibility[channel_id] = ChannelVisibilityNone()
    return visibility


def _last_event_timestamp(events: list[SimulationEvent]) -> datetime:
    """Return the timestamp of the latest event, or now() when the log is empty."""
    if not events:
        return datetime.now(tz=timezone.utc)
    return events[-1].timestamp


def _dedupe_latest_registration(agent_configs: list[AgentConfig]) -> list[AgentConfig]:
    """Keep one ``AgentConfig`` per ``agent_id`` — the last one in the input.

    ``extract_agent_configs`` emits one entry per ``AgentRegistered`` event,
    so on a replace-agent / multi-swap run the same ``agent_id`` shows up
    once for every model swap. We want the post-resume / final registration
    because that's the agent whose model+system_prompt is actually active at
    end-of-run and whose probe answer represents the run's final state.
    """
    by_id: dict[str, AgentConfig] = {}
    for agent in agent_configs:
        by_id[agent.agent_id] = agent
    return list(by_id.values())
