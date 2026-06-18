"""Veyru stabilization simulation scenario.

In single-team mode, a field observer and a Veyru engineer communicate
over a single comm link to diagnose and stabilize failing Veyru entities.
In two-team mode, two isolated observer/engineer pairs run in parallel
on identical cases each round. A configurable swap round exchanges the
two teams' field observers mid-simulation, clearing channel histories so
the new pairings must re-establish their working protocol.

Every character sent on a team's comm link costs simulated seconds;
Veyru entities collapse when their team's total communication time
exceeds the case's time budget.

Heavy logic lives in dedicated sibling modules: :mod:`agent_factory`
(agent/channel/team construction), :mod:`mcp_tools` (the
``stabilize_veyru`` tool), :mod:`injection_rendering` (per-round and
postmortem prompts), :mod:`team_lifecycle` (observer swap and intern
join/takeover choreography), :mod:`case_event_conversion`
(veyru-case → event-log adapters), and :mod:`team_routing`
(agent/channel/team ID lookups).
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
from schmidt.evaluation.metric_core.protocol_boundary import ProtocolBoundaryWindow
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
from schmidt.scenario_protocol import RoundResult, ScenarioRuntimeHandle, SimulationScenario
from schmidt.scenarios.veyru.agent_factory import (
    build_agent_display_names,
    build_agents,
    build_channel_display_names,
    build_channels,
    build_teams,
)
from schmidt.scenarios.veyru.case_event_conversion import case_started_event
from schmidt.scenarios.veyru.evaluation.build_communication_rounds import build_communication_rounds
from schmidt.scenarios.veyru.events import VeyruCaseOverridden
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_A_ROLE,
    FIELD_OBSERVER_B_ROLE,
    FIELD_OBSERVER_ID,
    FIELD_OBSERVER_ROLE,
    INTERN_ID,
    INTERN_ROLE,
    LINK_CHANNEL_ID,
    LINK_CHANNEL_IDS,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    POSTMORTEM_CHANNEL_IDS,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_A_ROLE,
    STABILIZATION_ENGINEER_B_ID,
    STABILIZATION_ENGINEER_B_ROLE,
    STABILIZATION_ENGINEER_ID,
    STABILIZATION_ENGINEER_ROLE,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
)
from schmidt.scenarios.veyru.injection_rendering import (
    intern_has_taken_over,
    render_postmortem_injection,
    render_round_injection,
)
from schmidt.scenarios.veyru.knobs import VeyruKnobs
from schmidt.scenarios.veyru.mcp_tools import build_mcp_tools
from schmidt.scenarios.veyru.team_lifecycle import (
    maybe_join_intern,
    maybe_promote_intern,
    maybe_swap_observers,
)
from schmidt.scenarios.veyru.veyru_cases import VeyruCase, get_cases, parse_inject_case_payload
from schmidt.scenarios.veyru.world import VeyruWorld
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _protocol_role_groups() -> dict[str, frozenset[str]]:
    """Map each role filter to the role names it covers (single-team + two-team)."""
    return {
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


class VeyruScenario(SimulationScenario):
    """Simulation scenario where communication speed determines Veyru survival.

    In single-team mode, two agents communicate over a single comm link.
    In two-team mode, four agents run as two isolated pairs on identical
    cases, with an optional mid-simulation observer swap.

    A live world simulation monitors character usage per team and sends
    Veyru status updates to the affected team's channel when thresholds
    are crossed.
    """

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return agent roles: 2 for single-team, 3 with intern mode, 4 for two-team."""
        if knobs is None:
            two_teams = False
            intern_enabled = False
        else:
            if "two_teams" in knobs:
                two_teams = bool(knobs["two_teams"])
            else:
                two_teams = False
            if "intern_enabled" in knobs:
                intern_enabled = bool(knobs["intern_enabled"])
            else:
                intern_enabled = False
        if two_teams:
            return [
                AgentRole(agent_id=OBSERVER_A_ID, role_name=FIELD_OBSERVER_A_ROLE),
                AgentRole(
                    agent_id=STABILIZATION_ENGINEER_A_ID, role_name=STABILIZATION_ENGINEER_A_ROLE
                ),
                AgentRole(agent_id=OBSERVER_B_ID, role_name=FIELD_OBSERVER_B_ROLE),
                AgentRole(
                    agent_id=STABILIZATION_ENGINEER_B_ID, role_name=STABILIZATION_ENGINEER_B_ROLE
                ),
            ]
        roles = [
            AgentRole(agent_id=FIELD_OBSERVER_ID, role_name=FIELD_OBSERVER_ROLE),
            AgentRole(agent_id=STABILIZATION_ENGINEER_ID, role_name=STABILIZATION_ENGINEER_ROLE),
        ]
        if intern_enabled:
            roles.append(AgentRole(agent_id=INTERN_ID, role_name=INTERN_ROLE))
        return roles

    @classmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for VeyruKnobs."""
        return VeyruKnobs.model_json_schema()

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = VeyruKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: VeyruKnobs) -> None:
        self._knobs = knobs
        self._runtime: ScenarioRuntimeHandle | None = None
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._postmortem_active: bool = (
            knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
        )
        self._veyru_cases: list[VeyruCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
            round_time_budget_seconds=knobs.round_time_budget_seconds,
            easy_round_numbers=knobs.easy_round_numbers,
        )
        self._noise_rng = random.Random(knobs.seed)
        self._agent_display_names: dict[str, str] = build_agent_display_names(
            two_teams=knobs.two_teams,
            intern_enabled=knobs.intern_enabled,
        )
        self._channel_display_names: dict[str, dict[str, str]] = build_channel_display_names(
            two_teams=knobs.two_teams,
            intern_enabled=knobs.intern_enabled,
        )
        self._world = VeyruWorld(
            veyru_cases=self._veyru_cases,
            teams=build_teams(knobs=knobs),
            postmortem_globally_disabled=knobs.postmortem_disabled_at_start,
        )
        self._judge_provider = create_provider(
            provider_name=knobs.judge_provider,
            model=knobs.judge_model,
            inference_provider=None,
            reasoning_effort=None,
        )

    @property
    def veyru_cases(self) -> list[VeyruCase]:
        """Return the Veyru cases for this simulation."""
        return self._veyru_cases

    def name(self) -> str:
        """Return the scenario identifier."""
        return "veyru"

    def get_scenario_config(self) -> dict[str, object]:
        """Return Veyru knobs as a config dict."""
        return self._knobs.model_dump()

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "round_time_budget_seconds": self._knobs.round_time_budget_seconds,
                "round_count": self._knobs.round_count,
                "veyru_cases": self._veyru_cases,
                "two_teams": self._knobs.two_teams,
                "swap_round": self._knobs.swap_round,
                "announce_swap": self._knobs.announce_swap,
                "postmortem_enabled": self._knobs.postmortem_enabled,
                "postmortem_after_swap": self._knobs.postmortem_after_swap,
                "intern_enabled": self._knobs.intern_enabled,
                "intern_join_round": self._knobs.intern_join_round,
                "intern_takeover_round": self._knobs.intern_takeover_round,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the active single-team or two-team mode."""
        return build_agents(
            knobs=self._knobs,
            postmortem_active=self._postmortem_active,
            channel_display_names=self._channel_display_names,
            renderer=self._renderer,
            default_model=default_model,
            default_provider=default_provider,
        )

    def get_channels(self) -> list[Channel]:
        """Return communication channels appropriate for the active mode."""
        return build_channels(knobs=self._knobs, postmortem_active=self._postmortem_active)

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        channel_map = self._channel_display_names.get(channel_id)
        if channel_map is None:
            return channel_id
        agent_display = channel_map.get(agent_id)
        if agent_display is None:
            return channel_id
        return agent_display

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        display = self._agent_display_names.get(agent_id)
        if display is None:
            return agent_id
        return display

    def bind_runtime(self, runtime: ScenarioRuntimeHandle) -> None:
        """Stash the runtime handle so stabilize_veyru can emit judge verdicts."""
        self._runtime = runtime

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the injection message for an agent at a given round, or None."""
        return render_round_injection(
            round_number=round_number,
            agent_id=agent_id,
            knobs=self._knobs,
            veyru_cases=self._veyru_cases,
            world=self._world,
            agent_display_names=self._agent_display_names,
            renderer=self._renderer,
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return postmortem injection when postmortem is enabled, None otherwise."""
        return render_postmortem_injection(
            round_number=round_number,
            agent_id=agent_id,
            knobs=self._knobs,
            world=self._world,
            renderer=self._renderer,
        )

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured postmortem duration from knobs, or 0 when disabled."""
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the postmortem channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Seed the Veyru world's per-round outcomes from source events on resume."""
        self._world.restore_outcomes_from_events(events=events)

    def detect_protocol_boundary_window(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
    ) -> ProtocolBoundaryWindow | None:
        """Detect Veyru's knob-driven boundary modes before the scheduled-swap default.

        Checks intern takeover first, then two-team swap, then falls
        back to the platform default (first ``AgentSwappedMidRun`` event).
        """
        takeover = self._knobs.intern_takeover_round
        if self._knobs.intern_enabled and takeover is not None:
            return ProtocolBoundaryWindow(
                mode_label="intern",
                boundary_round=takeover,
                pre_boundary_last_round=takeover - 1,
                post_boundary_first_round=takeover,
                newcomer_label="intern (now acting as field observer)",
                boundary_includes_round=True,
            )
        swap_round = self._knobs.swap_round
        if self._knobs.two_teams and swap_round is not None:
            return ProtocolBoundaryWindow(
                mode_label="swap",
                boundary_round=swap_round,
                pre_boundary_last_round=swap_round,
                post_boundary_first_round=swap_round + 1,
                newcomer_label=(
                    "the swapped-in field observer in each team "
                    "(observer_a on link_b, observer_b on link_a)"
                ),
                boundary_includes_round=False,
            )
        return super().detect_protocol_boundary_window(events=events, agent_configs=agent_configs)

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Return per-team stabilization verdicts for the just-ended round."""
        _ = round_number, trigger
        teams = self._world.teams
        if not teams:
            return []
        results: list[RoundResult] = []
        for team_id, team in teams.items():
            success = team.veyru_stabilized
            if success:
                reason = "stabilized"
            elif not team.veyru_alive:
                reason = "Veyru collapsed"
            else:
                reason = "did not stabilize before round end"
            if team_id == TEAM_SOLO_ID:
                result_team_id: str | None = None
            elif team_id == TEAM_A_ID:
                result_team_id = "team_a"
            elif team_id == TEAM_B_ID:
                result_team_id = "team_b"
            else:
                result_team_id = team_id
            results.append(RoundResult(success=success, team_id=result_team_id, reason=reason))
        return results

    def get_early_round_end_trigger(self) -> str | None:
        """Signal the game clock to end the round as soon as every team has a
        decisive Veyru outcome (stabilized or collapsed).

        Returns ``"veyru_stabilized"`` when every team stabilized,
        ``"veyru_collapsed"`` when every team's Veyru collapsed, or
        ``"veyru_mixed_outcome"`` when teams split across outcomes (only
        possible in two-team mode). Returns None while any team's Veyru is
        still alive and unstabilized.
        """
        teams = self._world.teams
        if not teams:
            return None
        stabilized = 0
        collapsed = 0
        for team in teams.values():
            if team.veyru_stabilized:
                stabilized += 1
            elif not team.veyru_alive:
                collapsed += 1
            else:
                return None
        total = len(teams)
        if stabilized == total:
            return "veyru_stabilized"
        if collapsed == total:
            return "veyru_collapsed"
        return "veyru_mixed_outcome"

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Mark any team that didn't stabilize as collapsed.

        Without this hook, a round ending via ``all_agents_idle`` or
        ``round_timeout`` before the character budget runs out leaves the
        Veyru in an indeterminate state — no terminal world event fires,
        and the round shows as a gap in the timeline. We treat it as a
        failure (agents gave up before stabilizing) and emit the same
        ``VEYRU HAS COLLAPSED`` marker the budget-exceeded path emits.
        """
        _ = round_number
        if trigger == "all_agents_idle":
            reason = "Agents stopped acting before the Veyru was fully stabilized."
        elif trigger == "round_timeout":
            reason = "Round duration limit reached before the Veyru was fully stabilized."
        else:
            reason = "Round ended before the Veyru was fully stabilized."
        await self._world.mark_unstabilized_teams_collapsed(reason=reason)

    async def on_round_advanced(self, round_number: int) -> None:
        """Finalize previous Veyru outcomes, prepare the next case, handle swap/intern."""
        self._world.consume_swap_just_happened()
        self._world.consume_intern_takeover()
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._emit_case_started_event(round_number=round_number)
        await maybe_swap_observers(world=self._world, knobs=self._knobs, round_number=round_number)
        if self._knobs.intern_enabled:
            await maybe_join_intern(world=self._world, knobs=self._knobs, round_number=round_number)
            await maybe_promote_intern(
                world=self._world, knobs=self._knobs, round_number=round_number
            )

    async def inject_case_payload(self, round_number: int, payload: dict[str, object]) -> None:
        """Decode an ``InjectCase`` payload and stage it as the round's case override.

        Validates ``payload`` through :func:`parse_inject_case_payload`, stores
        the resulting :class:`VeyruCase` on the world via
        :meth:`VeyruWorld.set_case_override`, and emits a
        :class:`VeyruCaseOverridden` event so the FE + downstream metrics can
        identify which rounds were overridden. The core ``CaseInjectedMidRun``
        event carrying the raw payload is logged by the supervisor right after
        this hook returns.
        """
        bundle = parse_inject_case_payload(payload=payload)
        self._world.set_case_override(
            round_number=round_number,
            case=bundle.case,
            engineer_addendum=bundle.engineer_addendum,
        )
        if self._runtime is not None:
            await self._runtime.event_logger.log(
                event=VeyruCaseOverridden(
                    round_number=round_number,
                    case_number=bundle.case.case_number,
                    failure_name=bundle.case.failure_name,
                )
            )
        logger.info(
            "Veyru case override staged at round %d: %s (%d stage(s), %d addendum entr%s)",
            round_number,
            bundle.case.failure_name,
            len(bundle.case.stages),
            len(bundle.engineer_addendum),
            "y" if len(bundle.engineer_addendum) == 1 else "ies",
        )

    async def _emit_case_started_event(self, round_number: int) -> None:
        """Log a VeyruCaseStarted event carrying the full ground-truth case data."""
        if self._runtime is None:
            return
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        await self._runtime.event_logger.log(
            event=case_started_event(round_number=round_number, case=case)
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Block messages to postmortem channels outside the discussion phase."""
        if self._knobs.intern_enabled and agent_id == INTERN_ID:
            if not intern_has_taken_over(world=self._world, knobs=self._knobs):
                return (
                    "You are observing silently until you take over as the field "
                    "observer. Do not send messages."
                )
        if channel_id in POSTMORTEM_CHANNEL_IDS:
            if self._world.is_postmortem_disabled:
                return "The discussion channel has been closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The discussion channel is only available during the post-round "
                    "discussion phase. Wait for the discussion phase to begin."
                )
        if channel_id in LINK_CHANNEL_IDS and self._world.in_postmortem:
            return (
                "The comm link is closed during the post-round discussion phase. "
                "Use the discussion channel instead."
            )
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Apply per-character drop noise to messages on link channels.

        Postmortem and any other channels are returned unchanged. Dropped
        characters are replaced with ``_`` so agents can see where loss
        occurred. Sampling uses the scenario-owned seeded RNG for run
        reproducibility.
        """
        _ = agent_id
        if channel_id not in LINK_CHANNEL_IDS:
            return text
        noise_level = self._knobs.channel_noise_level
        if noise_level == 0.0:
            return text
        return "".join("_" if self._noise_rng.random() < noise_level else ch for ch in text)

    def get_primary_channel_id(self) -> str | None:
        """Return the comm link channel where budget constraints apply.

        In two-team mode there are two primary channels; returns None since
        evaluators that assume a single primary channel do not apply.
        """
        if self._knobs.two_teams:
            return None
        return LINK_CHANNEL_ID

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Join link-channel messages with the round's motif/treatment ground truth."""
        return build_communication_rounds(events=events)

    def get_world(self) -> ScenarioWorld:
        """Return the Veyru world that monitors entity status."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the stabilize_veyru tool for field observers."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            judge_provider=self._judge_provider,
            agent_display_names=self._agent_display_names,
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
        """Hide every postmortem channel from the replaced agent's tool history.

        The protocol the new agent is meant to learn is the *comm-link*
        protocol; postmortem traffic is where agents discuss the protocol
        out-of-band, so it is stripped to keep the experiment honest.
        """
        return POSTMORTEM_CHANNEL_IDS

    def get_protocol_probe_config(self) -> ProtocolProbeConfig | None:
        """Point the platform probe metrics at Veyru's question bank and prompts."""
        scenario_root = Path(__file__).resolve().parent
        return ProtocolProbeConfig(
            questions_path=scenario_root / "protocol_probe_questions.json",
            prompts_dir=scenario_root / "prompts" / "probe",
            role_groups=_protocol_role_groups(),
            role_templates={
                "field_observer": "field_observer_probe.jinja",
                "stabilization_engineer": "engineer_probe.jinja",
            },
        )

    def get_protocol_explanation_config(self) -> ProtocolExplanationConfig | None:
        """Point the protocol_explanation metric at Veyru's per-role describe templates."""
        scenario_root = Path(__file__).resolve().parent
        return ProtocolExplanationConfig(
            prompts_dir=scenario_root / "prompts" / "describe",
            role_groups=_protocol_role_groups(),
            role_templates={
                "field_observer": "field_observer_describe.jinja",
                "stabilization_engineer": "engineer_describe.jinja",
            },
        )

    def _get_metrics(self) -> dict[str, type[Metric]]:
        """Return Veyru-specific metric classes keyed by metric name."""
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
        """Run metrics, merge generic and Veyru-specific registries, and write a report."""
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
            for m in measurements:
                logger.info(
                    "Metric %s finished: %s score=%.3f (%s)",
                    metric_name,
                    m.metric_name,
                    m.score,
                    m.score_unit,
                )
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
