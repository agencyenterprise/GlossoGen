"""Spot-the-difference (reconstruction from split data) simulation scenario.

Each round the environment generates a scene of objects on a grid and a
near-identical copy with exactly K planted differences (an attribute changed,
an object moved, an object added, or an object removed). Each team has two
symmetric viewers: the left viewer sees scene A, the right viewer sees scene
B. Neither sees the other scene nor the differences, so a difference is only
discoverable by exchanging descriptions over the link channel.

Two-team mode runs two isolated teams on the identical scene pair each round.
A team is eligible only if it identifies every difference with no incorrect
guesses (the correctness gate); among eligible teams, the one that exchanged
the fewest characters wins, and the winner is announced each round as
in-context reinforcement.

Heavy logic lives in dedicated sibling modules: :mod:`scene_generation`
(seeded scene + difference planting), :mod:`world` (per-team character
accounting and submission locking), :mod:`difference_judge` (the free-text
submission judge), :mod:`mcp_tools` (the ``submit_differences`` tool),
:mod:`agent_factory` (agent/channel construction), and
:mod:`injection_rendering` (per-round and postmortem prompts).
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
from schmidt.evaluation.metric_core.protocol_explanation_config import ProtocolExplanationConfig
from schmidt.evaluation.metric_core.protocol_probe_config import ProtocolProbeConfig
from schmidt.evaluation.metrics.communication.round_view import CommunicationRoundView
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
from schmidt.models.event import SimulationEvent
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool
from schmidt.runtime.scenario_world import ScenarioWorld
from schmidt.scenario_protocol import (
    PrimaryChannel,
    RoundResult,
    ScenarioRuntimeHandle,
    SimulationScenario,
)
from schmidt.scenarios.channel_noise import apply_character_noise
from schmidt.scenarios.spot_the_difference.agent_factory import (
    build_agent_display_names,
    build_agents,
    build_channel_display_names,
    build_channels,
)
from schmidt.scenarios.spot_the_difference.case_event_conversion import case_started_event
from schmidt.scenarios.spot_the_difference.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from schmidt.scenarios.spot_the_difference.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    VIEWER_LEFT_A_ID,
    VIEWER_LEFT_A_ROLE,
    VIEWER_LEFT_B_ID,
    VIEWER_LEFT_B_ROLE,
    VIEWER_LEFT_ID,
    VIEWER_LEFT_ROLE,
    VIEWER_RIGHT_A_ID,
    VIEWER_RIGHT_A_ROLE,
    VIEWER_RIGHT_B_ID,
    VIEWER_RIGHT_B_ROLE,
    VIEWER_RIGHT_ID,
    VIEWER_RIGHT_ROLE,
)
from schmidt.scenarios.spot_the_difference.injection_rendering import (
    render_postmortem_injection,
    render_round_injection,
)
from schmidt.scenarios.spot_the_difference.knobs import SpotTheDifferenceKnobs
from schmidt.scenarios.spot_the_difference.mcp_tools import build_mcp_tools
from schmidt.scenarios.spot_the_difference.scene_generation import get_cases
from schmidt.scenarios.spot_the_difference.team_routing import (
    AGENT_ID_TO_TEAM_ID,
    team_id_for_agent,
)
from schmidt.scenarios.spot_the_difference.world import SpotTheDifferenceWorld
from schmidt.scenarios.spot_the_difference.world_state import DiffOutcome
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

_POSTMORTEM_CHANNELS = frozenset(
    {POSTMORTEM_CHANNEL_ID, POSTMORTEM_A_CHANNEL_ID, POSTMORTEM_B_CHANNEL_ID}
)
_LINK_CHANNELS = frozenset({LINK_CHANNEL_ID, LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID})

_VIEWER_ROLE_NAMES = frozenset(
    {
        VIEWER_LEFT_ROLE,
        VIEWER_RIGHT_ROLE,
        VIEWER_LEFT_A_ROLE,
        VIEWER_RIGHT_A_ROLE,
        VIEWER_LEFT_B_ROLE,
        VIEWER_RIGHT_B_ROLE,
    }
)


class SpotTheDifferenceScenario(SimulationScenario):
    """Two-viewer-per-team spot-the-difference reconstruction scenario."""

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the role list: 2 for single-team, 4 for two-team."""
        two_teams = bool(knobs.get("two_teams", False)) if knobs is not None else False
        if two_teams:
            return [
                AgentRole(agent_id=VIEWER_LEFT_A_ID, role_name=VIEWER_LEFT_A_ROLE),
                AgentRole(agent_id=VIEWER_RIGHT_A_ID, role_name=VIEWER_RIGHT_A_ROLE),
                AgentRole(agent_id=VIEWER_LEFT_B_ID, role_name=VIEWER_LEFT_B_ROLE),
                AgentRole(agent_id=VIEWER_RIGHT_B_ID, role_name=VIEWER_RIGHT_B_ROLE),
            ]
        return [
            AgentRole(agent_id=VIEWER_LEFT_ID, role_name=VIEWER_LEFT_ROLE),
            AgentRole(agent_id=VIEWER_RIGHT_ID, role_name=VIEWER_RIGHT_ROLE),
        ]

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for SpotTheDifferenceKnobs."""
        return SpotTheDifferenceKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = SpotTheDifferenceKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: SpotTheDifferenceKnobs) -> None:
        self._knobs = knobs
        self._runtime: ScenarioRuntimeHandle | None = None
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_initially_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._cases = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            grid_size=knobs.grid_size,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            object_count_values=knobs.object_count_values,
            object_count_weights=knobs.object_count_weights,
            difference_count_values=knobs.difference_count_values,
            difference_count_weights=knobs.difference_count_weights,
            difference_kinds=knobs.difference_kinds,
            easy_round_numbers=knobs.easy_round_numbers,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = build_agent_display_names(
            two_teams=knobs.two_teams
        )
        self._channel_display_names: dict[str, str] = build_channel_display_names(
            two_teams=knobs.two_teams
        )
        self._world = SpotTheDifferenceWorld(
            cases=self._cases,
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
            two_teams=knobs.two_teams,
            all_must_submit=knobs.all_must_submit,
        )
        self._judge_provider = create_provider(
            provider_name=knobs.judge_provider,
            model=knobs.judge_model,
            inference_provider=None,
            reasoning_effort=None,
        )

    def name(self) -> str:
        """Return the scenario identifier."""
        return "spot_the_difference"

    def get_scenario_config(self) -> dict[str, object]:
        """Return spot_the_difference knobs as a config dict for the JSONL log."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_count": self._knobs.round_count,
                "grid_size": self._knobs.grid_size,
                "two_teams": self._knobs.two_teams,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the viewer team(s)."""
        return build_agents(
            knobs=self._knobs,
            postmortem_initially_active=self._postmortem_initially_active,
            agent_display_names=self._agent_display_names,
            channel_display_names=self._channel_display_names,
            renderer=self._renderer,
            default_model=default_model,
            default_provider=default_provider,
        )

    def get_channels(self) -> list[Channel]:
        """Return per-team link + (optional) postmortem channels."""
        return build_channels(
            knobs=self._knobs,
            postmortem_initially_active=self._postmortem_initially_active,
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
        """Stash the runtime handle so submit_differences can emit judge verdicts."""
        self._runtime = runtime

    def _previous_outcome(self, team_id: str) -> DiffOutcome | None:
        """Return the most recent round outcome for ``team_id``, or None on round 1."""
        return self._world.previous_outcome(team_id=team_id)

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the per-round injection for one agent, or None."""
        if agent_id not in AGENT_ID_TO_TEAM_ID:
            return None
        team_id = team_id_for_agent(agent_id=agent_id)
        return render_round_injection(
            round_number=round_number,
            agent_id=agent_id,
            case=self._cases[round_number - 1],
            previous_outcome=self._previous_outcome(team_id=team_id),
            two_teams=self._knobs.two_teams,
            renderer=self._renderer,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the postmortem injection when postmortem is enabled, None otherwise."""
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        if agent_id not in AGENT_ID_TO_TEAM_ID:
            return None
        team_id = team_id_for_agent(agent_id=agent_id)
        return render_postmortem_injection(
            round_number=round_number,
            previous_outcome=self._previous_outcome(team_id=team_id),
            two_teams=self._knobs.two_teams,
            renderer=self._renderer,
        )

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured postmortem duration, or 0 when disabled."""
        if not self._knobs.postmortem_enabled:
            return 0.0
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the postmortem channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed the world's per-round outcomes from source events on resume."""
        self._world.restore_outcomes_from_events(events=events)

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return per-team success verdicts (the correctness gate) from world state."""
        _ = round_number, trigger
        results: list[RoundResult] = []
        for team_id in self._world.team_ids:
            outcome = self._world.previous_outcome(team_id=team_id)
            if outcome is None:
                continue
            if team_id == TEAM_SOLO_ID:
                result_team_id: str | None = None
            else:
                result_team_id = team_id
            results.append(
                RoundResult(
                    success=outcome.eligible,
                    team_id=result_team_id,
                    reason=_outcome_reason(outcome=outcome),
                )
            )
        return results

    def get_early_round_end_trigger(self) -> str | None:
        """End the round once every team has submitted (or exhausted its budget when one is set)."""
        if self._world.current_case is None:
            return None
        if self._world.all_teams_done():
            return "all_teams_done"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Score this round and reveal each team's result on its link channel."""
        _ = trigger
        self._world.mark_round_outcome(round_number=round_number)
        await self._world.emit_round_terminal_notification()

    async def on_round_advanced(self, round_number: int) -> None:
        """Finalize the previous outcome, load the next case, log case-started."""
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log a SpotTheDifferenceCaseStarted event carrying the full ground-truth case."""
        if self._runtime is None:
            return
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        await self._runtime.event_logger.log(
            event=case_started_event(round_number=round_number, case=case)
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Block postmortem messages outside the discussion phase, link messages during it."""
        _ = agent_id
        if channel_id in _POSTMORTEM_CHANNELS:
            if self._world.is_postmortem_disabled:
                return "The discussion channel has been closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The discussion channel is only available during the post-round "
                    "discussion phase. Wait for the discussion phase to begin."
                )
        if channel_id in _LINK_CHANNELS and self._world.in_postmortem:
            return (
                "The link channel is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on the link channels."""
        _ = agent_id
        if channel_id not in _LINK_CHANNELS:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return each team's link channel so char metrics score teams separately."""
        if self._knobs.two_teams:
            return [
                PrimaryChannel(channel_id=LINK_A_CHANNEL_ID, team_id=TEAM_A_ID),
                PrimaryChannel(channel_id=LINK_B_CHANNEL_ID, team_id=TEAM_B_ID),
            ]
        return [PrimaryChannel(channel_id=LINK_CHANNEL_ID, team_id=None)]

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Join link-channel messages with the round's planted-difference ground truth."""
        return build_communication_rounds(events=events)

    def get_protocol_probe_config(self) -> ProtocolProbeConfig | None:
        """Opt into the protocol-probe metric family with one symmetric viewer role group."""
        scenario_root = Path(__file__).resolve().parent
        return ProtocolProbeConfig(
            questions_path=scenario_root / "protocol_probe_questions.json",
            prompts_dir=scenario_root / "prompts" / "probe",
            role_groups={"viewer": _VIEWER_ROLE_NAMES},
            role_templates={"viewer": "viewer_probe.jinja"},
        )

    def get_protocol_explanation_config(self) -> ProtocolExplanationConfig | None:
        """Tailor the protocol-explanation metric with the viewer describe template."""
        scenario_root = Path(__file__).resolve().parent
        return ProtocolExplanationConfig(
            prompts_dir=scenario_root / "prompts" / "describe",
            role_groups={"viewer": _VIEWER_ROLE_NAMES},
            role_templates={"viewer": "viewer_describe.jinja"},
        )

    def get_world(self) -> ScenarioWorld:
        """Return the spot_the_difference world."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the submit_differences tool."""
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
        """Hide the postmortem channels from any replaced agent's tool history."""
        return _POSTMORTEM_CHANNELS

    def _get_metrics(self) -> dict[str, type[Metric]]:
        """Return spot-the-difference-specific metric classes keyed by metric name."""
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


def _outcome_reason(outcome: DiffOutcome) -> str:
    """Human-readable round-result reason for a RoundResult."""
    base = f"found {outcome.found_count}/{outcome.total_differences}"
    if outcome.false_positive_count > 0:
        base = f"{base}, {outcome.false_positive_count} incorrect"
    base = f"{base}, {outcome.characters_used} chars"
    if outcome.members_required > 1 and outcome.members_submitted < outcome.members_required:
        return (
            f"only {outcome.members_submitted}/{outcome.members_required} members submitted "
            f"({base})"
        )
    if not outcome.submitted:
        return f"did not submit ({base})"
    if outcome.competitive and outcome.won:
        return f"won — {base}"
    if outcome.eligible:
        return f"all found — {base}"
    if not outcome.agreed:
        return f"members disagreed — {base}"
    if (
        outcome.budget_exceeded
        and outcome.found_count == outcome.total_differences
        and outcome.false_positive_count == 0
    ):
        return f"over budget — {base}"
    return f"incomplete — {base}"
