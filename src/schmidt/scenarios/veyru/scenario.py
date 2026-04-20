"""Veyru stabilization simulation scenario.

In single-team mode, a field observer and a Veyru specialist communicate
over a single comm link to diagnose and stabilize failing Veyru entities.
In two-team mode, two isolated observer/specialist pairs run in parallel
on identical cases each round. A configurable swap round exchanges the
two teams' field observers mid-simulation, clearing channel histories so
the new pairings must re-establish their working protocol.

Every character sent on a team's comm link costs simulated seconds;
Veyru entities collapse when their team's total communication time
exceeds the case's time budget.
"""

import logging
from pathlib import Path
from typing import Any, NamedTuple, Self

from schmidt.evaluation.evaluation_cost import compute_evaluation_cost
from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_protocol import EvaluatorFactory
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.provider_factory import create_provider
from schmidt.models.agent_config import AgentConfig, AgentRole
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.runtime.scenario_world import ScenarioWorld, WorldContext
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation import (
    LanguageEmergenceEvaluator,
    ProtocolLearnedAfterSwapEvaluator,
    RoundSuccessEvaluator,
)
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_A_ROLE,
    FIELD_OBSERVER_B_ROLE,
    FIELD_OBSERVER_ID,
    FIELD_OBSERVER_INJECTION_TEMPLATE,
    FIELD_OBSERVER_ROLE,
    FIELD_OBSERVER_SYSTEM_TEMPLATE,
    INTERN_ID,
    INTERN_JOIN_REASON,
    INTERN_ROLE,
    INTERN_SYSTEM_TEMPLATE,
    INTERN_TAKEOVER_REASON,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    NEW_SYMPTOMS_MARKER,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    OBSERVER_SWAP_REASON,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    SPECIALIST_A_ID,
    SPECIALIST_A_ROLE,
    SPECIALIST_B_ID,
    SPECIALIST_B_ROLE,
    SPECIALIST_ID,
    SPECIALIST_INJECTION_TEMPLATE,
    SPECIALIST_ROLE,
    SPECIALIST_SYSTEM_TEMPLATE,
    STABILIZATION_SUCCESS_MARKER,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TOOLS_INTERN,
    TOOLS_OBSERVER,
    TOOLS_SPECIALIST,
    TeamId,
)
from schmidt.scenarios.veyru.knobs import VeyruKnobs
from schmidt.scenarios.veyru.stabilization_judge import judge_stabilization
from schmidt.scenarios.veyru.veyru_cases import VeyruCase, get_cases, get_stellar_treatment_mapping
from schmidt.scenarios.veyru.world import TeamState, VeyruOutcome, VeyruWorld
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    system_template: str


PROMPTS_DIR = Path(__file__).parent / "prompts"


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
                AgentRole(agent_id=SPECIALIST_A_ID, role_name=SPECIALIST_A_ROLE),
                AgentRole(agent_id=OBSERVER_B_ID, role_name=FIELD_OBSERVER_B_ROLE),
                AgentRole(agent_id=SPECIALIST_B_ID, role_name=SPECIALIST_B_ROLE),
            ]
        roles = [
            AgentRole(agent_id=FIELD_OBSERVER_ID, role_name=FIELD_OBSERVER_ROLE),
            AgentRole(agent_id=SPECIALIST_ID, role_name=SPECIALIST_ROLE),
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
        self._renderer = TemplateRenderer(prompts_dir=PROMPTS_DIR)
        self._veyru_cases: list[VeyruCase] = get_cases(
            seed=knobs.seed,
            round_count=knobs.round_count,
        )
        self._agent_display_names: dict[str, str] = self._build_agent_display_names(
            two_teams=knobs.two_teams,
            intern_enabled=knobs.intern_enabled,
        )
        self._channel_display_names: dict[str, dict[str, str]] = self._build_channel_display_names(
            two_teams=knobs.two_teams,
            intern_enabled=knobs.intern_enabled,
        )
        self._world = VeyruWorld(
            seconds_per_character=knobs.seconds_per_character,
            veyru_cases=self._veyru_cases,
            teams=self._build_teams(knobs=knobs),
        )
        self._judge_provider = create_provider(
            provider_name=knobs.judge_provider,
            model=knobs.judge_model,
            inference_provider=None,
            reasoning_effort=None,
        )

    @staticmethod
    def _build_agent_display_names(two_teams: bool, intern_enabled: bool) -> dict[str, str]:
        """Return agent display names appropriate for the active mode."""
        if two_teams:
            return {
                OBSERVER_A_ID: FIELD_OBSERVER_A_ROLE,
                SPECIALIST_A_ID: SPECIALIST_A_ROLE,
                OBSERVER_B_ID: FIELD_OBSERVER_B_ROLE,
                SPECIALIST_B_ID: SPECIALIST_B_ROLE,
                "world": "Veyru Monitor",
            }
        names: dict[str, str] = {
            FIELD_OBSERVER_ID: FIELD_OBSERVER_ROLE,
            SPECIALIST_ID: SPECIALIST_ROLE,
            "world": "Veyru Monitor",
        }
        if intern_enabled:
            names[INTERN_ID] = INTERN_ROLE
        return names

    @staticmethod
    def _build_channel_display_names(
        two_teams: bool, intern_enabled: bool
    ) -> dict[str, dict[str, str]]:
        """Return channel display names keyed by channel_id then agent_id."""
        if two_teams:
            return {
                LINK_A_CHANNEL_ID: {
                    OBSERVER_A_ID: "comm link",
                    SPECIALIST_A_ID: "comm link",
                    OBSERVER_B_ID: "comm link",
                    SPECIALIST_B_ID: "comm link",
                },
                LINK_B_CHANNEL_ID: {
                    OBSERVER_A_ID: "comm link",
                    SPECIALIST_A_ID: "comm link",
                    OBSERVER_B_ID: "comm link",
                    SPECIALIST_B_ID: "comm link",
                },
                POSTMORTEM_A_CHANNEL_ID: {
                    OBSERVER_A_ID: "team discussion",
                    SPECIALIST_A_ID: "team discussion",
                    OBSERVER_B_ID: "team discussion",
                    SPECIALIST_B_ID: "team discussion",
                },
                POSTMORTEM_B_CHANNEL_ID: {
                    OBSERVER_A_ID: "team discussion",
                    SPECIALIST_A_ID: "team discussion",
                    OBSERVER_B_ID: "team discussion",
                    SPECIALIST_B_ID: "team discussion",
                },
            }
        link_members = {
            FIELD_OBSERVER_ID: "comm link",
            SPECIALIST_ID: "comm link",
        }
        postmortem_members = {
            FIELD_OBSERVER_ID: "team discussion",
            SPECIALIST_ID: "team discussion",
        }
        if intern_enabled:
            link_members[INTERN_ID] = "comm link"
            postmortem_members[INTERN_ID] = "team discussion"
        return {
            LINK_CHANNEL_ID: link_members,
            POSTMORTEM_CHANNEL_ID: postmortem_members,
        }

    def _build_teams(self, knobs: VeyruKnobs) -> dict[TeamId, TeamState]:
        """Construct the world's initial team state dictionary."""
        if not knobs.two_teams:
            postmortem_id: str | None
            if knobs.postmortem_enabled:
                postmortem_id = POSTMORTEM_CHANNEL_ID
            else:
                postmortem_id = None
            return {
                TEAM_SOLO_ID: TeamState(
                    team_id=TEAM_SOLO_ID,
                    current_observer_id=FIELD_OBSERVER_ID,
                    specialist_id=SPECIALIST_ID,
                    link_channel_id=LINK_CHANNEL_ID,
                    postmortem_channel_id=postmortem_id,
                ),
            }

        postmortem_a: str | None
        postmortem_b: str | None
        if knobs.postmortem_enabled:
            postmortem_a = POSTMORTEM_A_CHANNEL_ID
            postmortem_b = POSTMORTEM_B_CHANNEL_ID
        else:
            postmortem_a = None
            postmortem_b = None
        return {
            TEAM_A_ID: TeamState(
                team_id=TEAM_A_ID,
                current_observer_id=OBSERVER_A_ID,
                specialist_id=SPECIALIST_A_ID,
                link_channel_id=LINK_A_CHANNEL_ID,
                postmortem_channel_id=postmortem_a,
            ),
            TEAM_B_ID: TeamState(
                team_id=TEAM_B_ID,
                current_observer_id=OBSERVER_B_ID,
                specialist_id=SPECIALIST_B_ID,
                link_channel_id=LINK_B_CHANNEL_ID,
                postmortem_channel_id=postmortem_b,
            ),
        }

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
                "seconds_per_character": self._knobs.seconds_per_character,
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

    def _channel_template_data(
        self, agent_id: str, channel_ids: list[str]
    ) -> list[ChannelTemplateEntry]:
        """Build channel entries for Jinja2 system prompt templates."""
        return [
            ChannelTemplateEntry(
                display_name=self.get_channel_display_name(channel_id=cid, agent_id=agent_id),
                channel_id=cid,
            )
            for cid in channel_ids
        ]

    def _agent_defs_single_team(self) -> list[AgentDef]:
        """Return agent definitions for single-team mode."""
        link_channels: list[str] = [LINK_CHANNEL_ID]
        if self._knobs.postmortem_enabled:
            link_channels.append(POSTMORTEM_CHANNEL_ID)
        defs = [
            AgentDef(
                agent_id=FIELD_OBSERVER_ID,
                role_name=FIELD_OBSERVER_ROLE,
                channel_ids=list(link_channels),
                tool_names=list(TOOLS_OBSERVER),
                system_template=FIELD_OBSERVER_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=SPECIALIST_ID,
                role_name=SPECIALIST_ROLE,
                channel_ids=list(link_channels),
                tool_names=list(TOOLS_SPECIALIST),
                system_template=SPECIALIST_SYSTEM_TEMPLATE,
            ),
        ]
        if self._knobs.intern_enabled:
            intern_channels: list[str] = [LINK_CHANNEL_ID]
            if self._knobs.postmortem_enabled and self._knobs.postmortem_after_swap:
                intern_channels.append(POSTMORTEM_CHANNEL_ID)
            defs.append(
                AgentDef(
                    agent_id=INTERN_ID,
                    role_name=INTERN_ROLE,
                    channel_ids=intern_channels,
                    tool_names=list(TOOLS_INTERN),
                    system_template=INTERN_SYSTEM_TEMPLATE,
                )
            )
        return defs

    def _agent_defs_two_teams(self) -> list[AgentDef]:
        """Return agent definitions for two-team mode."""
        team_a_channels: list[str] = [LINK_A_CHANNEL_ID]
        team_b_channels: list[str] = [LINK_B_CHANNEL_ID]
        if self._knobs.postmortem_enabled:
            team_a_channels.append(POSTMORTEM_A_CHANNEL_ID)
            team_b_channels.append(POSTMORTEM_B_CHANNEL_ID)
        return [
            AgentDef(
                agent_id=OBSERVER_A_ID,
                role_name=FIELD_OBSERVER_A_ROLE,
                channel_ids=list(team_a_channels),
                tool_names=list(TOOLS_OBSERVER),
                system_template=FIELD_OBSERVER_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=SPECIALIST_A_ID,
                role_name=SPECIALIST_A_ROLE,
                channel_ids=list(team_a_channels),
                tool_names=list(TOOLS_SPECIALIST),
                system_template=SPECIALIST_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=OBSERVER_B_ID,
                role_name=FIELD_OBSERVER_B_ROLE,
                channel_ids=list(team_b_channels),
                tool_names=list(TOOLS_OBSERVER),
                system_template=FIELD_OBSERVER_SYSTEM_TEMPLATE,
            ),
            AgentDef(
                agent_id=SPECIALIST_B_ID,
                role_name=SPECIALIST_B_ROLE,
                channel_ids=list(team_b_channels),
                tool_names=list(TOOLS_SPECIALIST),
                system_template=SPECIALIST_SYSTEM_TEMPLATE,
            ),
        ]

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return agent configurations for the active single-team or two-team mode."""
        if self._knobs.two_teams:
            agent_defs = self._agent_defs_two_teams()
        else:
            agent_defs = self._agent_defs_single_team()

        agents: list[AgentConfig] = []
        for d in agent_defs:
            agents.append(
                AgentConfig(
                    agent_id=d.agent_id,
                    role_name=d.role_name,
                    system_prompt=self._renderer.render(
                        template_name=d.system_template,
                        template_variables={
                            "channels": self._channel_template_data(
                                agent_id=d.agent_id, channel_ids=d.channel_ids
                            ),
                            "seconds_per_character": self._knobs.seconds_per_character,
                            "postmortem_enabled": self._knobs.postmortem_enabled,
                            "intern_join_round": self._knobs.intern_join_round,
                            "intern_takeover_round": self._knobs.intern_takeover_round,
                        },
                    ),
                    channel_ids=d.channel_ids,
                    tool_names=d.tool_names,
                    model=default_model,
                    provider=default_provider,
                    max_tokens=16384,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return communication channels appropriate for the active mode."""
        if not self._knobs.two_teams:
            channels: list[Channel] = [
                Channel(
                    channel_id=LINK_CHANNEL_ID,
                    name="link",
                    member_agent_ids=[FIELD_OBSERVER_ID, SPECIALIST_ID],
                ),
            ]
            if self._knobs.postmortem_enabled:
                channels.append(
                    Channel(
                        channel_id=POSTMORTEM_CHANNEL_ID,
                        name="postmortem",
                        member_agent_ids=[FIELD_OBSERVER_ID, SPECIALIST_ID],
                    )
                )
            return channels

        two_team_channels: list[Channel] = [
            Channel(
                channel_id=LINK_A_CHANNEL_ID,
                name="link_a",
                member_agent_ids=[OBSERVER_A_ID, SPECIALIST_A_ID],
            ),
            Channel(
                channel_id=LINK_B_CHANNEL_ID,
                name="link_b",
                member_agent_ids=[OBSERVER_B_ID, SPECIALIST_B_ID],
            ),
        ]
        if self._knobs.postmortem_enabled:
            two_team_channels.append(
                Channel(
                    channel_id=POSTMORTEM_A_CHANNEL_ID,
                    name="postmortem_a",
                    member_agent_ids=[OBSERVER_A_ID, SPECIALIST_A_ID],
                )
            )
            two_team_channels.append(
                Channel(
                    channel_id=POSTMORTEM_B_CHANNEL_ID,
                    name="postmortem_b",
                    member_agent_ids=[OBSERVER_B_ID, SPECIALIST_B_ID],
                )
            )
        return two_team_channels

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

    def _get_previous_outcome_for_agent(self, agent_id: str) -> VeyruOutcome | None:
        """Return the most recent outcome for the team the agent belongs to."""
        team_id = self._world.get_team_for_agent(agent_id=agent_id)
        outcomes = self._world.get_outcomes_for_team(team_id=team_id)
        if len(outcomes) == 0:
            return None
        return outcomes[-1]

    def _get_partner_display_name(self, agent_id: str) -> str:
        """Return the display name of the agent's current partner on their team."""
        team_id = self._world.get_team_for_agent(agent_id=agent_id)
        team = self._world.teams[team_id]
        if agent_id == team.current_observer_id:
            partner_id = team.specialist_id
        else:
            partner_id = team.current_observer_id
        return self.get_agent_display_name(agent_id=partner_id)

    def _has_intern_taken_over(self) -> bool:
        """Whether the intern has been promoted to field observer."""
        if not self._knobs.intern_enabled:
            return False
        if TEAM_SOLO_ID not in self._world.teams:
            return False
        return self._world.teams[TEAM_SOLO_ID].current_observer_id == INTERN_ID

    def _is_observer_agent(self, agent_id: str) -> bool:
        """Whether this agent is acting as a field observer in the current round."""
        if agent_id in (OBSERVER_A_ID, OBSERVER_B_ID):
            return True
        if agent_id == FIELD_OBSERVER_ID:
            return not self._has_intern_taken_over()
        if agent_id == INTERN_ID:
            return self._has_intern_taken_over()
        return False

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the injection message for an agent at a given round, or None."""
        if agent_id == INTERN_ID and not self._has_intern_taken_over():
            return None
        if (
            self._knobs.intern_enabled
            and agent_id == FIELD_OBSERVER_ID
            and self._has_intern_taken_over()
        ):
            return None

        template_name: str | None
        if self._is_observer_agent(agent_id=agent_id):
            template_name = FIELD_OBSERVER_INJECTION_TEMPLATE
        elif agent_id in (SPECIALIST_ID, SPECIALIST_A_ID, SPECIALIST_B_ID):
            template_name = SPECIALIST_INJECTION_TEMPLATE
        else:
            template_name = None
        if template_name is None:
            return None

        current_case_index = (round_number - 1) % len(self._veyru_cases)
        current_case = self._veyru_cases[current_case_index]

        previous_outcome = self._get_previous_outcome_for_agent(agent_id=agent_id)

        treatment_mapping = get_stellar_treatment_mapping(
            stellar_offset=current_case.stellar_reading.offset,
        )

        swap_just_happened = self._world.peek_swap_just_happened()
        partner_display_name = self._get_partner_display_name(agent_id=agent_id)
        intern_takeover_just_happened = agent_id == INTERN_ID and self._world.peek_intern_takeover()

        rendered = self._renderer.render(
            template_name=template_name,
            template_variables={
                "round_number": round_number,
                "current_case": current_case,
                "first_stage_symptoms": current_case.stages[0].observable_symptoms,
                "previous_outcome": previous_outcome,
                "knobs": self._knobs,
                "treatment_mapping": treatment_mapping,
                "stellar_reading": current_case.stellar_reading,
                "swap_just_happened": swap_just_happened,
                "announce_swap": self._knobs.announce_swap,
                "partner_display_name": partner_display_name,
                "intern_takeover_just_happened": intern_takeover_just_happened,
                "intern_join_round": self._knobs.intern_join_round,
            },
        )
        if not rendered:
            return None
        logger.debug(
            "Injection for agent %s at round %d: %d chars",
            agent_id,
            round_number,
            len(rendered),
        )
        return rendered

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return postmortem injection when postmortem is enabled, None otherwise."""
        if not self._knobs.postmortem_enabled:
            return None
        if self._world.is_postmortem_disabled:
            return None
        if self._knobs.intern_enabled:
            if agent_id == INTERN_ID and not self._has_intern_taken_over():
                return None
            if agent_id == FIELD_OBSERVER_ID and self._has_intern_taken_over():
                return None

        team_id = self._world.get_team_for_agent(agent_id=agent_id)
        outcome = self._world.compute_outcome_if_needed(
            round_number=round_number,
            team_id=team_id,
        )

        rendered = self._renderer.render(
            template_name="postmortem_injection.jinja",
            template_variables={
                "round_number": round_number,
                "previous_outcome": outcome,
            },
        )
        if not rendered:
            return None
        logger.debug(
            "Postmortem injection for agent %s at round %d: %d chars",
            agent_id,
            round_number,
            len(rendered),
        )
        return rendered

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the configured postmortem duration from knobs, or 0 when disabled."""
        if self._world.is_postmortem_disabled:
            return 0.0
        return self._knobs.postmortem_duration_seconds

    def on_postmortem_started(self, round_number: int) -> None:
        """Unlock the postmortem channel for discussion."""
        _ = round_number
        self._world.enter_postmortem()

    async def on_round_advanced(self, round_number: int) -> None:
        """Finalize previous Veyru outcomes, prepare the next case, handle swap/intern."""
        self._world.consume_swap_just_happened()
        self._world.consume_intern_takeover()
        self._world.exit_postmortem()
        self._world.finalize_round_sync(round_number=round_number)
        await self._maybe_swap_observers(round_number=round_number)
        if self._knobs.intern_enabled:
            await self._maybe_join_intern(round_number=round_number)
            await self._maybe_promote_intern(round_number=round_number)

    async def _maybe_join_intern(self, round_number: int) -> None:
        """At intern_join_round, add the intern to the link channel and announce."""
        if self._knobs.intern_join_round is None:
            return
        if round_number != self._knobs.intern_join_round:
            return

        logger.info("Intern joining link channel at round %d", round_number)
        context = self._world.context
        await context.update_channel_members(
            channel_id=LINK_CHANNEL_ID,
            member_agent_ids=[FIELD_OBSERVER_ID, SPECIALIST_ID, INTERN_ID],
            reason=INTERN_JOIN_REASON,
        )
        await context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
            text=(
                "An intern observer has joined the comm link and will silently "
                "observe your work. They will not speak or act until further notice."
            ),
        )

    async def _maybe_promote_intern(self, round_number: int) -> None:
        """At intern_takeover_round, replace the field observer with the intern."""
        if self._knobs.intern_takeover_round is None:
            return
        if round_number != self._knobs.intern_takeover_round:
            return

        displaced = self._world.promote_intern_to_observer(intern_id=INTERN_ID)
        logger.info(
            "Intern takeover fired at round %d: displaced observer=%s",
            round_number,
            displaced,
        )

        context = self._world.context
        await context.update_channel_members(
            channel_id=LINK_CHANNEL_ID,
            member_agent_ids=[SPECIALIST_ID, INTERN_ID],
            reason=INTERN_TAKEOVER_REASON,
        )
        if self._knobs.postmortem_enabled:
            if self._knobs.postmortem_after_swap:
                await context.update_channel_members(
                    channel_id=POSTMORTEM_CHANNEL_ID,
                    member_agent_ids=[SPECIALIST_ID, INTERN_ID],
                    reason=INTERN_TAKEOVER_REASON,
                )
            else:
                await context.update_channel_members(
                    channel_id=POSTMORTEM_CHANNEL_ID,
                    member_agent_ids=[SPECIALIST_ID],
                    reason=INTERN_TAKEOVER_REASON,
                )

        await context.send_update_to_channel(
            channel_id=LINK_CHANNEL_ID,
            text=(
                "=== FIELD OBSERVER HANDOFF ===\n"
                "The intern has taken over as the active field observer. "
                "The previous field observer has left the comm link. "
                "Continue the protocol with the new pairing."
            ),
        )

    async def _maybe_swap_observers(self, round_number: int) -> None:
        """Swap observers, clear channel histories, announce, and optionally close postmortem."""
        if self._knobs.swap_round is None:
            return
        if round_number != self._knobs.swap_round + 1:
            return

        new_team_a_observer, new_team_b_observer = self._world.swap_observers()
        logger.info(
            "Veyru observer swap fired at round %d: team A observer=%s, team B observer=%s",
            round_number,
            new_team_a_observer,
            new_team_b_observer,
        )

        team_a = self._world.teams[TEAM_A_ID]
        team_b = self._world.teams[TEAM_B_ID]

        context = self._world.context
        await self._apply_swap_to_channel(
            context=context,
            channel_id=team_a.link_channel_id,
            observer_id=team_a.current_observer_id,
            specialist_id=team_a.specialist_id,
        )
        await self._apply_swap_to_channel(
            context=context,
            channel_id=team_b.link_channel_id,
            observer_id=team_b.current_observer_id,
            specialist_id=team_b.specialist_id,
        )
        if team_a.postmortem_channel_id is not None:
            await self._apply_swap_to_channel(
                context=context,
                channel_id=team_a.postmortem_channel_id,
                observer_id=team_a.current_observer_id,
                specialist_id=team_a.specialist_id,
            )
        if team_b.postmortem_channel_id is not None:
            await self._apply_swap_to_channel(
                context=context,
                channel_id=team_b.postmortem_channel_id,
                observer_id=team_b.current_observer_id,
                specialist_id=team_b.specialist_id,
            )

        if self._knobs.announce_swap:
            self._world.mark_swap_just_happened()
            announcement = (
                "=== TEAM RECONFIGURATION ===\n"
                "The field observers between the two teams have been swapped. "
                "The channel history has been cleared."
            )
            await context.send_update_to_channel(
                channel_id=team_a.link_channel_id,
                text=announcement,
            )
            await context.send_update_to_channel(
                channel_id=team_b.link_channel_id,
                text=announcement,
            )

        if self._knobs.postmortem_enabled and not self._knobs.postmortem_after_swap:
            self._world.disable_postmortem_globally()

    @staticmethod
    async def _apply_swap_to_channel(
        context: WorldContext,
        channel_id: str,
        observer_id: str,
        specialist_id: str,
    ) -> None:
        """Apply membership update + history wipe to one channel as part of a swap."""
        await context.update_channel_members(
            channel_id=channel_id,
            member_agent_ids=[observer_id, specialist_id],
            reason=OBSERVER_SWAP_REASON,
        )
        await context.clear_channel_history(
            channel_id=channel_id,
            reason=OBSERVER_SWAP_REASON,
        )

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Block messages to postmortem channels outside the discussion phase."""
        if self._knobs.intern_enabled and agent_id == INTERN_ID:
            if not self._has_intern_taken_over():
                return (
                    "You are observing silently until you take over as the field "
                    "observer. Do not send messages."
                )
        postmortem_channel_ids = {
            POSTMORTEM_CHANNEL_ID,
            POSTMORTEM_A_CHANNEL_ID,
            POSTMORTEM_B_CHANNEL_ID,
        }
        if channel_id in postmortem_channel_ids:
            if self._world.is_postmortem_disabled:
                return "The discussion channel has been closed for the remainder of the simulation."
            if not self._world.in_postmortem:
                return (
                    "The discussion channel is only available during the post-round "
                    "discussion phase. Wait for the discussion phase to begin."
                )
        return None

    # --- World, MCP tools, timing ---

    def get_primary_channel_id(self) -> str | None:
        """Return the comm link channel where budget constraints apply.

        In two-team mode there are two primary channels; returns None since
        evaluators that assume a single primary channel do not apply.
        """
        if self._knobs.two_teams:
            return None
        return LINK_CHANNEL_ID

    def get_world(self) -> ScenarioWorld:
        """Return the Veyru world that monitors entity status."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the stabilize_veyru tool for field observers."""

        async def stabilize_veyru(ctx: ToolContext, action: str) -> str:
            """Apply a stabilization action to the caller's team Veyru."""
            agent_id = resolve_agent_id(ctx=ctx)
            team_id = self._world.get_team_for_agent(agent_id=agent_id)
            team = self._world.teams[team_id]
            if agent_id != team.current_observer_id:
                raise ValueError("Only the field observer can stabilize Veyru entities")

            if not self._world.is_veyru_alive(team_id=team_id):
                result_text = "Cannot stabilize: Veyru has already collapsed."
                await self._maybe_broadcast_stabilize(
                    channel_id=team.link_channel_id,
                    caller_id=agent_id,
                    action=action,
                    result=result_text,
                )
                return result_text
            if self._world.is_veyru_stabilized(team_id=team_id):
                result_text = "Veyru has already been stabilized."
                await self._maybe_broadcast_stabilize(
                    channel_id=team.link_channel_id,
                    caller_id=agent_id,
                    action=action,
                    result=result_text,
                )
                return result_text

            current_stage = self._world.get_current_stage(team_id=team_id)
            if current_stage is None:
                result_text = "No Veyru to stabilize."
                await self._maybe_broadcast_stabilize(
                    channel_id=team.link_channel_id,
                    caller_id=agent_id,
                    action=action,
                    result=result_text,
                )
                return result_text

            judgment = await judge_stabilization(
                provider=self._judge_provider,
                expected_actions=current_stage.judge_expected_actions,
                observer_action=action,
            )

            if judgment.match:
                has_more = await self._world.stabilize_veyru(team_id=team_id)
                if has_more:
                    next_stage = self._world.get_current_stage(team_id=team_id)
                    assert next_stage is not None
                    result_text = (
                        f"{STABILIZATION_SUCCESS_MARKER}, but {NEW_SYMPTOMS_MARKER}. "
                        f"What you now observe: {next_stage.observable_symptoms} "
                        f"Report these to the specialist."
                    )
                    await self._maybe_broadcast_stabilize(
                        channel_id=team.link_channel_id,
                        caller_id=agent_id,
                        action=action,
                        result=result_text,
                    )
                    return result_text
                result_text = f"{STABILIZATION_SUCCESS_MARKER}."
                await self._maybe_broadcast_stabilize(
                    channel_id=team.link_channel_id,
                    caller_id=agent_id,
                    action=action,
                    result=result_text,
                )
                return result_text

            result_text = "Stabilization ineffective. Ask the specialist for guidance."
            await self._maybe_broadcast_stabilize(
                channel_id=team.link_channel_id,
                caller_id=agent_id,
                action=action,
                result=result_text,
            )
            return result_text

        return [
            ScenarioMcpTool(
                name="stabilize_veyru",
                description=(
                    "Apply a stabilization action to the current Veyru. "
                    "Describe exactly what you are doing to stabilize it."
                ),
                executor=stabilize_veyru,
            ),
        ]

    async def _maybe_broadcast_stabilize(
        self,
        channel_id: str,
        caller_id: str,
        action: str,
        result: str,
    ) -> None:
        """Broadcast a stabilize_veyru call + result to the link channel in intern mode.

        Only fires when ``intern_enabled=true`` so non-intern runs keep the
        existing terse world-outcome banner behavior. The intern relies on
        this broadcast to observe the calls and outcomes of the protocol.
        """
        if not self._knobs.intern_enabled:
            return
        context = self._world.context
        caller_display = self.get_agent_display_name(agent_id=caller_id)
        text = f'[stabilize_veyru] {caller_display} action="{action}"\n' f"result: {result}"
        await context.send_update_to_channel(
            channel_id=channel_id,
            text=text,
        )

    def get_round_count(self) -> int:
        """Return the configured number of rounds."""
        return self._knobs.round_count

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last."""
        return self._knobs.max_round_duration_seconds

    # --- Evaluation ---

    @classmethod
    def get_available_evaluator_names(cls) -> list[str]:
        """Return generic and Veyru-specific evaluator names."""
        generic = super().get_available_evaluator_names()
        specific = [
            LanguageEmergenceEvaluator.name,
            ProtocolLearnedAfterSwapEvaluator.name,
            RoundSuccessEvaluator.name,
        ]
        return sorted(set(generic + specific))

    def _get_evaluators(self) -> dict[str, EvaluatorFactory]:
        """Return Veyru-specific evaluators."""
        return {
            LanguageEmergenceEvaluator.name: LanguageEmergenceEvaluator,
            ProtocolLearnedAfterSwapEvaluator.name: ProtocolLearnedAfterSwapEvaluator,
            RoundSuccessEvaluator.name: RoundSuccessEvaluator,
        }

    async def run_evaluation(
        self,
        log_path: Path,
        evaluator_names: list[str],
        report_path: Path,
        model: str,
        provider_name: str,
        inference_provider: str | None,
        reasoning_effort: str | None,
    ) -> EvaluationReport:
        """Run evaluators, merge generic and Veyru-specific registries, and write a report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = create_provider(
            provider_name=provider_name,
            model=model,
            inference_provider=inference_provider,
            reasoning_effort=reasoning_effort,
        )

        registry: dict[str, EvaluatorFactory] = {}
        registry.update(GENERIC_EVALUATOR_REGISTRY)
        registry.update(self._get_evaluators())

        metrics: list[MetricResult] = []
        for eval_name in evaluator_names:
            if eval_name not in registry:
                available = ", ".join(sorted(registry.keys()))
                raise ValueError(f"Unknown evaluator: '{eval_name}'. Available: {available}")
            evaluator = registry[eval_name]()
            logger.info("Running evaluator: %s", eval_name)
            result = await evaluator.evaluate(
                events=events,
                agent_configs=agent_configs,
                scenario=self,
                llm_provider=provider,
            )
            logger.info(
                "Evaluator %s finished: verdict=%s, score=%.2f",
                eval_name,
                result.verdict,
                result.score,
            )
            metrics.append(result)

        evaluation_cost = compute_evaluation_cost(
            usage=provider.get_accumulated_usage(),
            model=model,
            provider_name=provider_name,
        )

        report = EvaluationReport(
            simulation_id=simulation_id,
            scenario_name=self.name(),
            metrics=metrics,
            evaluation_cost=evaluation_cost,
        )
        await write_report(report=report, report_path=report_path)
        return report
