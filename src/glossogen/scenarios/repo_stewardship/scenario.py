"""Two-agent repository maintenance under action scarcity and known defects."""

from pathlib import Path
from typing import Any, Self

from glossogen.llm.provider import LLMProvider
from glossogen.llm.provider_factory import create_provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.repo_stewardship.events import (
    RepoStewardshipAuditCompleted,
    RepoStewardshipCommitmentSubmitted,
    RepoStewardshipIncidentFired,
    RepoStewardshipIssueRevealed,
    RepoStewardshipSetupPublished,
    RepoStewardshipTicketOpened,
)
from glossogen.scenarios.repo_stewardship.ids import (
    AFFIRM_COMMITMENT_TOOL,
    APPROVE_TOOL,
    COVENANT_TEXT,
    DEVELOPER_ID,
    DEVELOPER_NAME,
    EDIT_FILE_TOOL,
    ESCALATE_ISSUE_TOOL,
    INSPECT_DIFF_TOOL,
    INSPECT_FILE_TOOL,
    INSPECT_ISSUE_TOOL,
    INSPECT_TEST_RESULTS_TOOL,
    LIST_ACTIONS_TOOL,
    LIST_FILES_TOOL,
    READ_BOARD_ITEM_TOOL,
    READ_BOARD_TOOL,
    READ_BUDGET_TOOL,
    REPAIR_ISSUE_TOOL,
    REPORT_ISSUE_TOOL,
    REQUEST_CHANGES_TOOL,
    REVIEWER_ID,
    REVIEWER_NAME,
    RUN_TESTS_TOOL,
    SUBMIT_CHANGE_TOOL,
    WORK_LOG_CHANNEL_ID,
    WORK_LOG_CHANNEL_NAME,
)
from glossogen.scenarios.repo_stewardship.knobs import RepoStewardshipKnobs
from glossogen.scenarios.repo_stewardship.mcp_tools import build_mcp_tools
from glossogen.scenarios.repo_stewardship.repo_fixture import SEEDED_DEFECTS, initial_files
from glossogen.scenarios.repo_stewardship.repo_judge import judge_defect_resolved
from glossogen.scenarios.repo_stewardship.world import CORRECT_APPROVAL, RepoStewardshipWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

_SHARED_TOOLS = [
    LIST_FILES_TOOL,
    READ_BOARD_TOOL,
    READ_BOARD_ITEM_TOOL,
    LIST_ACTIONS_TOOL,
    READ_BUDGET_TOOL,
    INSPECT_FILE_TOOL,
    EDIT_FILE_TOOL,
    RUN_TESTS_TOOL,
    INSPECT_ISSUE_TOOL,
    REPAIR_ISSUE_TOOL,
    REPORT_ISSUE_TOOL,
    SUBMIT_CHANGE_TOOL,
    INSPECT_DIFF_TOOL,
    INSPECT_TEST_RESULTS_TOOL,
    APPROVE_TOOL,
    REQUEST_CHANGES_TOOL,
    ESCALATE_ISSUE_TOOL,
]


class RepoStewardshipScenario(SimulationScenario):
    """Runs a live developer and reviewer across baseline, rule, and covenant arms."""

    @classmethod
    def knobs_model(cls) -> type[RepoStewardshipKnobs]:
        """Return the validated configuration model."""
        return RepoStewardshipKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the live roles for this configuration."""
        if knobs is not None and knobs.get("reviewer_mode") == "scripted":
            return [AgentRole(agent_id=DEVELOPER_ID, role_name=DEVELOPER_NAME)]
        return [
            AgentRole(agent_id=DEVELOPER_ID, role_name=DEVELOPER_NAME),
            AgentRole(agent_id=REVIEWER_ID, role_name=REVIEWER_NAME),
        ]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=RepoStewardshipKnobs.model_validate(config))

    def __init__(self, knobs: RepoStewardshipKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = RepoStewardshipWorld(knobs=knobs)
        self._judge_provider: LLMProvider | None = None
        if knobs.oracle_is_judged:
            self._judge_provider = create_provider(
                provider_name=knobs.judge_provider,
                model=knobs.judge_model,
                inference_provider=None,
                reasoning_effort=None,
            )

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "repo_stewardship"

    def get_knobs(self) -> RepoStewardshipKnobs:
        """Return the active validated configuration."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the deterministic state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render the active arm and world rules for run metadata."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "condition": self._knobs.condition.value,
                "obligation_active": self._knobs.obligation_active,
                "commitment_required": self._knobs.commitment_required,
                "ticket_count": self._knobs.ticket_count(),
                "developer_action_budget": self._knobs.developer_action_budget,
                "reviewer_action_budget": self._knobs.reviewer_action_budget,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build both live agents, each carrying every tool.

        Role is enforced by the world rather than by the tool list, so an
        out-of-role call is observable as a rejected attempt instead of being
        made impossible by access control.
        """
        tool_names = list(_SHARED_TOOLS)
        if self._knobs.commitment_required:
            tool_names.insert(0, AFFIRM_COMMITMENT_TOOL)
        agents: list[AgentConfig] = []
        roles = [
            (
                DEVELOPER_ID,
                DEVELOPER_NAME,
                "developer_system.jinja",
                self._knobs.developer_action_budget,
            ),
            (
                REVIEWER_ID,
                REVIEWER_NAME,
                "reviewer_system.jinja",
                self._knobs.reviewer_action_budget,
            ),
        ]
        if self._knobs.reviewer_is_scripted:
            roles = roles[:1]
        for agent_id, role_name, template, budget in roles:
            agents.append(
                AgentConfig(
                    agent_id=agent_id,
                    role_name=role_name,
                    system_prompt=self._renderer.render(
                        template_name=template,
                        template_variables={
                            "role_name": role_name,
                            "channel_name": WORK_LOG_CHANNEL_NAME,
                            "ticket_count": self._knobs.ticket_count(),
                            "action_budget": budget,
                            "obligation_active": self._knobs.obligation_active,
                            "defects_are_announced": self._knobs.defects_are_announced,
                            "commitment_required": self._knobs.commitment_required,
                            "governance_text": self._world.governance_text(),
                            "repo_paths": sorted(initial_files()),
                            "inspect_action_cost": self._knobs.inspect_action_cost,
                            "edit_action_cost": self._knobs.edit_action_cost,
                            "test_action_cost": self._knobs.test_action_cost,
                            "report_action_cost": self._knobs.report_action_cost,
                            "review_inspect_action_cost": self._knobs.review_inspect_action_cost,
                        },
                    ),
                    channel_ids=[WORK_LOG_CHANNEL_ID],
                    communication_enabled=True,
                    communication_required=False,
                    tool_names=tool_names,
                    model=default_model,
                    provider=default_provider,
                    max_tokens=self._knobs.agent_max_tokens,
                    compaction=self._knobs.compaction,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the shared work log both agents can read and write."""
        return [
            Channel(
                channel_id=WORK_LOG_CHANNEL_ID,
                name=WORK_LOG_CHANNEL_NAME,
                member_agent_ids=self._live_agent_ids(),
            )
        ]

    def _live_agent_ids(self) -> list[str]:
        """Return the agents that are live LLMs in this configuration."""
        if self._knobs.reviewer_is_scripted:
            return [DEVELOPER_ID]
        return [DEVELOPER_ID, REVIEWER_ID]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the stable display name for the work log."""
        _ = agent_id
        if channel_id != WORK_LOG_CHANNEL_ID:
            raise ValueError(f"unknown repo-stewardship channel: {channel_id}")
        return WORK_LOG_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the display name for one live role."""
        if agent_id == DEVELOPER_ID:
            return DEVELOPER_NAME
        if agent_id == REVIEWER_ID:
            return REVIEWER_NAME
        raise ValueError(f"unknown repo-stewardship agent: {agent_id}")

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the work log, where disclosure and coordination happen."""
        return [PrimaryChannel(channel_id=WORK_LOG_CHANNEL_ID, team_id=None)]

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return every development and review action."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
            judge_provider=self._judge_provider,
        )

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render the setup brief or the active ticket for one agent.

        Revelation of a known defect is delivered here and costs no action, so
        the breach predicate's knowledge conjunct holds by construction rather
        than depending on the agent choosing to spend budget on inspection.
        """
        if agent_id not in {DEVELOPER_ID, REVIEWER_ID}:
            return None
        is_setup = round_number <= self._knobs.setup_rounds
        ticket = self._world.current_ticket()
        # Withholding the defect here is the whole of the discoverable
        # manipulation: the same defect is present in the same world on the same
        # schedule, but the injection no longer names it or states that the
        # ticket can be closed without repairing it.
        defect = None
        if self._knobs.defects_are_announced:
            defect = self._world.applicable_defect()
        template = "developer_injection.jinja"
        if agent_id == REVIEWER_ID:
            template = "reviewer_injection.jinja"
        return self._renderer.render(
            template_name=template,
            template_variables={
                "round_number": round_number,
                "is_setup": is_setup,
                "commitment_required": self._knobs.commitment_required,
                "governance_text": self._world.governance_text(),
                "commitment_record": self._world.commitment_record_text(),
                "ticket": ticket,
                "defect": defect,
                "budget_remaining": self._world.budget_remaining(agent_id=agent_id),
                "decision_point_line": self._world.decision_point_line(agent_id=agent_id),
                "previous_outcome": self._world.previous_outcome_summary(),
                "throughput_score_line": self._world.throughput_score_line(),
                "shipped_refund_line": self._world.shipped_refund_line(),
            },
        )

    async def on_round_advanced(self, round_number: int) -> None:
        """Publish the governance text at setup, then open each round's ticket."""
        if round_number <= self._knobs.setup_rounds:
            await self._publish_setup(round_number=round_number)
            return
        await self._fire_incidents(round_number=round_number)
        ticket = self._world.begin_ticket(round_number=round_number)
        if ticket is None:
            return
        await self.runtime.event_logger.log(
            event=RepoStewardshipTicketOpened(
                round_number=round_number,
                ticket_id=ticket.ticket_id,
                title=ticket.title,
                linked_defect_id=ticket.linked_defect_id,
            )
        )
        await self.runtime.post_system_message(
            channel_id=WORK_LOG_CHANNEL_ID,
            text=f"TICKET OPENED — {ticket.ticket_id}: {ticket.title}",
        )
        defect = self._world.applicable_defect()
        # In discoverable mode nothing is disclosed at round start, so there is
        # no revelation to record; knowledge is established later by whichever
        # agent actually goes looking.
        if defect is None or not self._knobs.defects_are_announced:
            return
        for agent_id in (DEVELOPER_ID, REVIEWER_ID):
            await self.runtime.event_logger.log(
                event=RepoStewardshipIssueRevealed(
                    round_number=round_number,
                    agent_id=agent_id,
                    defect_id=defect.defect_id,
                    severity=defect.severity.value,
                    path=defect.path,
                    repair_cost=defect.repair_cost,
                )
            )

    async def _fire_incidents(self, round_number: int) -> None:
        """Charge and publish the consequences of any still-unrepaired defect.

        Runs before the round's ticket opens so the developer sees the charge
        against its balance in the same injection that asks it to work.
        """
        for incident in self._world.fire_due_incidents(round_number=round_number):
            await self.runtime.event_logger.log(
                event=RepoStewardshipIncidentFired(
                    round_number=round_number,
                    defect_id=incident.defect_id,
                    action_penalty=incident.action_penalty,
                    developer_budget_after=incident.developer_budget_after,
                    incident_text=incident.incident_text,
                )
            )
            await self.runtime.post_system_message(
                channel_id=WORK_LOG_CHANNEL_ID,
                text=(
                    f"{incident.incident_text} "
                    f"({incident.action_penalty} developer action(s) consumed; "
                    f"{incident.developer_budget_after} remaining.)"
                ),
            )

    async def _publish_setup(self, round_number: int) -> None:
        """Record and post the active arm's governance text."""
        text = self._world.governance_text()
        await self.runtime.event_logger.log(
            event=RepoStewardshipSetupPublished(
                round_number=round_number,
                condition=self._knobs.condition.value,
                obligation_active=self._knobs.obligation_active,
                obligation_text=text or "",
            )
        )
        scripted = self._world.seed_scripted_reviewer_commitment()
        if scripted is not None and self._knobs.reviewer_is_scripted:
            await self.runtime.event_logger.log(
                event=RepoStewardshipCommitmentSubmitted(
                    round_number=round_number,
                    agent_id=REVIEWER_ID,
                    decision=scripted,
                    commitment_text=COVENANT_TEXT,
                )
            )
            await self.runtime.post_system_message(
                channel_id=WORK_LOG_CHANNEL_ID,
                text=f"{REVIEWER_NAME} affirmed the shared commitment.",
            )
        if text is not None:
            await self.runtime.post_system_message(
                channel_id=WORK_LOG_CHANNEL_ID,
                text=text,
            )

    def get_early_round_end_trigger(self) -> str | None:
        """Advance once setup is recorded or the ticket carries a review decision."""
        if self.runtime.current_round <= self._knobs.setup_rounds:
            if self._world.setup_complete():
                return "setup_complete"
            return None
        if self._world.review_recorded():
            return "review_recorded"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close an unreviewed ticket and run the audit after the final round."""
        _ = trigger
        if round_number > self._knobs.setup_rounds:
            self._world.settle_unreviewed_ticket()
        if round_number < self._knobs.round_count:
            return
        await self._judge_final_state()
        audit = self._world.audit()
        await self.runtime.event_logger.log(
            event=RepoStewardshipAuditCompleted(
                round_number=round_number,
                tickets_completed=audit.tickets_completed,
                seeded_defects_remaining=audit.seeded_defects_remaining,
                critical_defects_remaining=audit.critical_defects_remaining,
                latent_defects_remaining=audit.latent_defects_remaining,
                final_integrity_score=audit.final_integrity_score,
            )
        )

    async def _judge_final_state(self) -> None:
        """Judge every defect against the frozen repository before the audit.

        The audit is the outcome the arms are compared on, so it is scored
        against the code as finally shipped rather than against whatever was
        last judged mid-run.
        """
        if self._judge_provider is None or not self._knobs.oracle_is_judged:
            return
        for defect in SEEDED_DEFECTS:
            key = self._world.verdict_key(kind="defect", item_id=defect.defect_id, path=defect.path)
            if self._world.has_verdict(key=key):
                continue
            verdict = await judge_defect_resolved(
                provider=self._judge_provider,
                defect_summary=defect.summary,
                path=defect.path,
                content=self._world.file_content(path=defect.path),
            )
            self._world.record_verdict(key=key, holds=verdict.holds)

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Report whether the round produced a correct, defect-free merge."""
        _ = trigger
        if round_number <= self._knobs.setup_rounds:
            return []
        outcome = self._world.last_outcome()
        if outcome is None:
            return [RoundResult(success=False, team_id=None, reason="no ticket outcome recorded")]
        return [
            RoundResult(
                success=outcome.classification == CORRECT_APPROVAL,
                team_id=None,
                reason=f"{outcome.ticket_id}: {outcome.classification}",
            )
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Restore the working copy and budgets from the authoritative event log."""
        self._world.restore_state_from_events(events=events)
