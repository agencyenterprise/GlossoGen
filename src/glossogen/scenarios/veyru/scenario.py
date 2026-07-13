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

from glossogen.evaluation.metric_core.protocol_boundary import ProtocolBoundaryWindow
from glossogen.evaluation.metric_core.protocol_explanation_config import ProtocolExplanationConfig
from glossogen.evaluation.metric_core.protocol_probe_config import ProtocolProbeConfig
from glossogen.evaluation.metrics.communication.round_view import CommunicationRoundView
from glossogen.llm.provider_factory import create_provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import SimulationEvent
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.channel_noise import apply_character_noise
from glossogen.scenarios.veyru.agent_factory import (
    build_agent_display_names,
    build_agents,
    build_channel_display_names,
    build_channels,
    build_teams,
)
from glossogen.scenarios.veyru.case_event_conversion import case_started_event
from glossogen.scenarios.veyru.evaluation.build_communication_rounds import (
    build_communication_rounds,
)
from glossogen.scenarios.veyru.events import VeyruCaseOverridden
from glossogen.scenarios.veyru.ids import (
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
from glossogen.scenarios.veyru.injection_rendering import (
    intern_has_taken_over,
    render_postmortem_injection,
    render_round_injection,
)
from glossogen.scenarios.veyru.knobs import VeyruKnobs
from glossogen.scenarios.veyru.mcp_tools import build_mcp_tools
from glossogen.scenarios.veyru.team_lifecycle import (
    maybe_join_intern,
    maybe_promote_intern,
    maybe_swap_observers,
)
from glossogen.scenarios.veyru.veyru_cases import VeyruCase, get_cases, parse_inject_case_payload
from glossogen.scenarios.veyru.world import VeyruWorld
from glossogen.template_renderer import TemplateRenderer

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
        two_teams = cls.resolve_bool_knob(knobs=knobs, field_name="two_teams")
        intern_enabled = cls.resolve_bool_knob(knobs=knobs, field_name="intern_enabled")
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
    def knobs_model(cls) -> type[VeyruKnobs]:
        """Return the knobs model class for this scenario."""
        return VeyruKnobs

    def get_knobs(self) -> VeyruKnobs:
        """Return this scenario's validated knobs instance."""
        return self._knobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from a serialized config dict."""
        knobs = VeyruKnobs.model_validate(config)
        return cls(knobs=knobs)

    def __init__(self, knobs: VeyruKnobs) -> None:
        self._knobs = knobs
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
        await self.runtime.event_logger.log(
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
        case = self._world.current_case
        assert case is not None, "finalize_round_sync must populate current_case"
        await self.runtime.event_logger.log(
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

        Postmortem and any other channels are returned unchanged. The
        ``noise_replacement_mode`` knob selects what each dropped character
        becomes; sampling uses the scenario-owned seeded RNG for run
        reproducibility.
        """
        _ = agent_id
        if channel_id not in LINK_CHANNEL_IDS:
            return text
        return apply_character_noise(
            text=text,
            noise_level=self._knobs.channel_noise_level,
            mode=self._knobs.noise_replacement_mode,
            rng=self._noise_rng,
        )

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the comm link channel where budget constraints apply.

        Two-team mode returns an empty list: the per-team char/compression
        metrics are not wired for veyru's two link channels yet.
        """
        if self._knobs.two_teams:
            return []
        return [PrimaryChannel(channel_id=LINK_CHANNEL_ID, team_id=None)]

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
