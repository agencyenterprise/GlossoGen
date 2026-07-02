"""Orbital anomaly simulation scenario.

A single crew member aboard a crippled spacecraft is talked through
cascading system malfunctions by two Mission Control flight controllers
over a budget-constrained comm loop. The astronaut sees the physical panel
(which unit tripped, the current switch/tie configuration) and is the only
agent that can operate controls; the telemetry officer reads the downlinked
data (the exact fault plus the required hold and corrective setting); the
systems engineer holds the procedure handbook and the per-round secret
configuration rotation that maps each fault to a procedure template. No
single pair can complete a procedure: the engineer's template needs the
unit/config from the crew and the hold/setting from the telemetry officer,
and only the crew can act.

Every character sent on the comm loop costs simulated seconds; an anomaly
is lost when total communication time exceeds the case's time budget.

Heavy logic lives in dedicated sibling modules: :mod:`orbital_anomaly_cases`
(fault signatures, the rotation cipher, case assembly), :mod:`world`
(budget tracking and cascade stages), :mod:`actuation_judge` (the free-text
action judge), :mod:`mcp_tools` (the ``actuate_panel`` tool),
:mod:`agent_factory` (agent/channel construction), and
:mod:`injection_rendering` (per-round and debrief prompts).
"""

import logging
import random
from pathlib import Path
from typing import Any, Self

from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.evaluation.metric_core.measurement import Measurement
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_registry import GENERIC_METRIC_REGISTRY
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.reports.evaluation_cost import compute_evaluation_cost
from schmidt.evaluation.reports.evaluation_report import (
    EvaluationReport,
    load_report,
    merge_evaluation_costs,
    merge_measurements,
    write_report,
)
from schmidt.llm.provider_factory import create_provider
from schmidt.models.agent_config import AgentConfig, AgentRole
from schmidt.models.channel import Channel
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool
from schmidt.runtime.scenario_world import ScenarioWorld
from schmidt.scenario_protocol import (
    PrimaryChannel,
    RoundResult,
    ScenarioRuntimeHandle,
    SimulationScenario,
)
from schmidt.scenarios.channel_noise import apply_character_noise
from schmidt.scenarios.orbital_anomaly.agent_factory import (
    build_agent_display_names,
    build_agents,
    build_channel_display_names,
    build_channels,
)
from schmidt.scenarios.orbital_anomaly.events import (
    OrbitalAnomalyCaseStage,
    OrbitalAnomalyCaseStarted,
)
from schmidt.scenarios.orbital_anomaly.ids import (
    ASTRONAUT_ID,
    ASTRONAUT_ROLE,
    LINK_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    SYSTEMS_ENGINEER_ID,
    SYSTEMS_ENGINEER_ROLE,
    TELEMETRY_OFFICER_ID,
    TELEMETRY_OFFICER_ROLE,
)
from schmidt.scenarios.orbital_anomaly.injection_rendering import (
    render_postmortem_injection,
    render_round_injection,
)
from schmidt.scenarios.orbital_anomaly.knobs import OrbitalAnomalyKnobs
from schmidt.scenarios.orbital_anomaly.mcp_tools import build_mcp_tools
from schmidt.scenarios.orbital_anomaly.orbital_anomaly_cases import get_cases
from schmidt.scenarios.orbital_anomaly.world import OrbitalAnomalyWorld
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class OrbitalAnomalyScenario(SimulationScenario):
    """Three-agent crewed-spacecraft anomaly scenario."""

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the three agent roles (independent of knobs)."""
        _ = knobs
        return [
            AgentRole(agent_id=ASTRONAUT_ID, role_name=ASTRONAUT_ROLE),
            AgentRole(agent_id=TELEMETRY_OFFICER_ID, role_name=TELEMETRY_OFFICER_ROLE),
            AgentRole(agent_id=SYSTEMS_ENGINEER_ID, role_name=SYSTEMS_ENGINEER_ROLE),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for OrbitalAnomalyKnobs."""
        return OrbitalAnomalyKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = OrbitalAnomalyKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: OrbitalAnomalyKnobs) -> None:
        self._knobs = knobs
        self._runtime: ScenarioRuntimeHandle | None = None
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            cipher_enabled=knobs.cipher_enabled,
            easy_round_numbers=knobs.easy_round_numbers,
            fault_count_values=knobs.fault_count_values,
            fault_count_weights=knobs.fault_count_weights,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = build_agent_display_names()
        self._channel_display_names: dict[str, str] = build_channel_display_names()
        self._world = OrbitalAnomalyWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
        )
        self._judge_provider = create_provider(
            provider_name=knobs.judge_provider,
            model=knobs.judge_model,
            inference_provider=None,
            reasoning_effort=None,
        )

    def name(self) -> str:
        """Return the scenario identifier."""
        return "orbital_anomaly"

    def get_scenario_config(self) -> dict[str, object]:
        """Return orbital anomaly knobs as a config dict for the JSONL log."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "postmortem_enabled": self._knobs.postmortem_enabled,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the three-agent crew."""
        return build_agents(
            knobs=self._knobs,
            postmortem_active=self._postmortem_active,
            channel_display_names=self._channel_display_names,
            renderer=self._renderer,
            default_model=default_model,
            default_provider=default_provider,
        )

    def get_channels(self) -> list[Channel]:
        """Return the comm-loop channel plus the optional debrief channel."""
        return build_channels(
            postmortem_active=self._postmortem_active,
            channel_display_names=self._channel_display_names,
        )

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        _ = agent_id
        return self._channel_display_names.get(channel_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return self._agent_display_names.get(agent_id, agent_id)

    def bind_runtime(self, runtime: ScenarioRuntimeHandle) -> None:
        """Stash the runtime handle so actuate_panel can emit judge verdicts."""
        self._runtime = runtime

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        return render_round_injection(
            round_number=round_number,
            agent_id=agent_id,
            world=self._world,
            renderer=self._renderer,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the debrief injection when the debrief is open, None otherwise."""
        _ = agent_id
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        return render_postmortem_injection(
            round_number=round_number,
            world=self._world,
            renderer=self._renderer,
        )

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured debrief duration, or 0 when disabled."""
        if not self._knobs.postmortem_enabled:
            return 0.0
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the debrief channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return the single-team success verdict for the just-ended round."""
        _ = round_number, trigger
        outcome = self._world.previous_outcome()
        if outcome is None:
            return []
        if outcome.stabilized:
            reason = "stabilized"
        else:
            reason = "anomaly not resolved"
        return [RoundResult(success=outcome.stabilized, team_id=None, reason=reason)]

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once the anomaly is fully resolved or the system is lost."""
        if self._world.current_case is None:
            return None
        if self._world.is_vehicle_stabilized():
            return "vehicle_stabilized"
        if not self._world.is_vehicle_alive():
            return "vehicle_lost"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Emit a terminal notification and record this round's outcome."""
        _ = trigger
        await self._world.emit_round_terminal_notification()
        self._world.mark_round_outcome(round_number=round_number)

    async def on_round_advanced(self, round_number: int) -> None:
        """Reset per-round state, load the next case, and log case-started."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log an OrbitalAnomalyCaseStarted event carrying the full ground-truth case."""
        if self._runtime is None:
            return
        case = self._world.current_case
        if case is None:
            return
        await self._runtime.event_logger.log(
            event=OrbitalAnomalyCaseStarted(
                round_number=round_number,
                case_number=case.case_number,
                variant_index=case.variant_index,
                time_budget_seconds=case.time_budget_seconds,
                stages=[
                    OrbitalAnomalyCaseStage(
                        fault_name=stage.fault_name,
                        subsystem=stage.subsystem,
                        cockpit_alarm=stage.cockpit_alarm,
                        panel_observation=stage.panel_observation,
                        telemetry_readout=stage.telemetry_readout,
                        judge_expected_actions=stage.judge_expected_actions,
                    )
                    for stage in case.stages
                ],
            )
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Block debrief messages outside the debrief phase and comm-loop messages during it."""
        _ = agent_id
        if channel_id == POSTMORTEM_CHANNEL_ID:
            if self._world.is_postmortem_disabled:
                return "The debrief channel is closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The debrief channel is only open during the post-anomaly debrief phase. "
                    "Wait for the debrief phase to begin."
                )
        if channel_id == LINK_CHANNEL_ID and self._world.in_postmortem:
            return (
                "The comm loop is closed during the debrief phase. Use the debrief channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the comm loop."""
        _ = agent_id
        if channel_id != LINK_CHANNEL_ID:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the comm-loop channel where the communication budget applies."""
        return [PrimaryChannel(channel_id=LINK_CHANNEL_ID, team_id=None)]

    def get_world(self) -> ScenarioWorld:
        """Return the orbital anomaly world."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the actuate_panel tool."""
        return build_mcp_tools(
            world=self._world,
            judge_provider=self._judge_provider,
            get_runtime=lambda: self._runtime,
        )

    def get_round_count(self) -> int:
        """Return the configured number of rounds."""
        return self._knobs.round_count

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return self._knobs.max_round_duration_seconds

    @classmethod
    def get_replace_agent_blocked_tool_call_channels(cls) -> frozenset[str]:
        """Hide the debrief channel from any replaced agent's tool history."""
        return frozenset({POSTMORTEM_CHANNEL_ID})

    def _get_metrics(self) -> dict[str, type[Metric]]:
        """Return orbital-anomaly-specific metric classes keyed by metric name."""
        return {}

    async def run_evaluation(
        self,
        log_path: Path,
        metric_names: list[str],
        report_path: Path,
        model: str,
        provider_name: str,
        inference_provider: str | None,
        reasoning_effort: str | None,
        options: MetricRunOptions,
    ) -> EvaluationReport:
        """Run metrics over the generic registry and write a report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = create_provider(
            provider_name=provider_name,
            model=model,
            inference_provider=inference_provider,
            reasoning_effort=reasoning_effort,
        )
        registry: dict[str, type[Metric]] = {}
        registry.update(GENERIC_METRIC_REGISTRY)
        registry.update(self._get_metrics())
        for metric_name in metric_names:
            if metric_name not in registry:
                available = ", ".join(sorted(registry.keys()))
                raise ValueError(f"Unknown metric: '{metric_name}'. Available: {available}")
        new_measurements: list[Measurement] = []
        failed_metrics: list[str] = []
        for metric_name in metric_names:
            metric = registry[metric_name]()
            logger.info("Running metric: %s", metric_name)
            try:
                measurements = await metric.compute(
                    events=events,
                    agent_configs=agent_configs,
                    scenario=self,
                    llm_provider=provider,
                    run_dir=log_path.parent,
                    options=options,
                )
            except Exception:
                logger.exception("Metric %s failed; continuing with remaining metrics", metric_name)
                failed_metrics.append(metric_name)
                continue
            new_measurements.extend(measurements)
        if failed_metrics:
            logger.warning(
                "Evaluation completed with %d failed metric(s): %s",
                len(failed_metrics),
                ", ".join(failed_metrics),
            )
        invocation_cost = compute_evaluation_cost(
            usage=provider.get_accumulated_usage(),
            model=model,
            provider_name=provider_name,
        )
        attempted_metric_names = set(metric_names)
        existing_report = await load_report(report_path=report_path)
        if existing_report is None:
            merged = new_measurements
            cumulative_cost = invocation_cost
        else:
            merged = merge_measurements(
                existing=existing_report.measurements,
                new=new_measurements,
                attempted_metric_names=attempted_metric_names,
            )
            cumulative_cost = merge_evaluation_costs(
                existing=existing_report.evaluation_cost,
                new=invocation_cost,
            )
        report = EvaluationReport(
            simulation_id=simulation_id,
            scenario_name=self.name(),
            measurements=merged,
            evaluation_cost=cumulative_cost,
        )
        await write_report(report=report, report_path=report_path)
        return report
