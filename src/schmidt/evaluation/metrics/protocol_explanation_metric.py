"""Generic metric that asks each agent to describe its communication protocol.

For every agent in the run, reconstructs that agent's end-of-run pydantic-ai
message history (applying the replace-agent channel-visibility filter when the
agent was the one swapped in via ``replace-agent``) and runs one structured
``run_protocol_probe`` call asking the agent to explain the protocol it
actually remembers using.

The metric is scenario-agnostic — it works on any run where agents communicate.
For scenarios without inter-agent communication, the agent's answer will
typically say so explicitly. The prompt asks for concrete examples and
edge-case rules, so the answer functions as a structured proxy for "what did
this agent take away from the simulation."

Each agent's answer is written to ``per_agent[i].note``; the overall ``score``
is the number of agents probed. Returns an empty list when no agent has any
reconstructable history (e.g. a run that crashed before the first turn).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from schmidt.evaluation.metric_core.measurement import AgentObservation, Measurement
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.metrics.protocol_probe.probe_agent import run_protocol_probe
from schmidt.llm.provider import LLMProvider
from schmidt.message_history_builder import build_message_history
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.replace_manifest import ReplaceManifest, read_replace_manifest
from schmidt.runners.communication_protocol import build_full_system_prompt
from schmidt.runtime.scheduled_events import (
    ChannelVisibility,
    ChannelVisibilityFromRound,
    ChannelVisibilityFull,
    ChannelVisibilityNone,
)
from schmidt.scenario_protocol import SimulationScenario
from schmidt.token_pricing import SELF_HOSTED_PROVIDER

logger = logging.getLogger(__name__)

_PROBE_PROMPT = (
    "Explain in detail the communication protocol your team has been using "
    "throughout this simulation. Cover the formats and conventions for the "
    "messages you exchange, any abbreviations or codes you've agreed on, the "
    "meta-agreements about how to communicate, and any edge-case rules. Quote "
    "specific examples if you remember them. Be concrete — describe the "
    "protocol as it actually is, not as it could be. If your team did not "
    "develop any meaningful protocol, say so explicitly."
)


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
        _ = scenario, llm_provider, options
        if not events:
            return []

        manifest = read_replace_manifest(run_dir=run_dir)
        target_timestamp = _last_event_timestamp(events=events)
        latest_per_agent = _dedupe_latest_registration(agent_configs=agent_configs)

        observations: list[AgentObservation] = []
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
            probe = await run_protocol_probe(
                agent_id=agent.agent_id,
                role_name=agent.role_name,
                full_system_prompt=full_system_prompt,
                model=agent.model,
                provider=agent.provider,
                message_history=history,
                probe_prompt=_PROBE_PROMPT,
            )
            observations.append(
                AgentObservation(
                    agent_id=agent.agent_id,
                    value=float(len(history)),
                    note=probe.output.message,
                )
            )

        if not observations:
            return []

        score = float(len(observations))
        summary = (
            f"Probed {len(observations)} agent(s) for a protocol explanation; "
            "each agent's answer is stored in per_agent[].note."
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
