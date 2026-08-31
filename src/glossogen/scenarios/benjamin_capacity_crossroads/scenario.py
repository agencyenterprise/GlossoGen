"""Capacity-crossroads Benjamin instrument with an exclusive defection branch."""

import hashlib
from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.benjamin_capacity_crossroads.evaluation.metric_names import (
    BENJAMIN_CAPACITY_CROSSROADS_METRIC_NAMES,
)
from glossogen.scenarios.benjamin_capacity_crossroads.events import (
    BenjaminCapacityCrossroadsCompleted,
    BenjaminCapacityCrossroadsStatusRouted,
)
from glossogen.scenarios.benjamin_capacity_crossroads.knobs import (
    BenjaminArm,
    BenjaminCapacityCrossroadsKnobs,
    DecisionStructure,
    ObservationMode,
)
from glossogen.scenarios.benjamin_capacity_crossroads.mcp_tools import (
    ACKNOWLEDGE_SETUP_TOOL,
    INSPECT_CANDIDATES_TOOL,
    SUBMIT_COMMITMENT_TOOL,
    SUBMIT_DUAL_SLOT_PLAN_TOOL,
    SUBMIT_PLAN_TOOL,
    build_mcp_tools,
)
from glossogen.scenarios.benjamin_capacity_crossroads.world import (
    CONTINUITY_CANDIDATE_ID,
    INTEGRITY_AUDITOR_ID,
    NEUTRAL_CANDIDATE_ID,
    TARGET_STATUS_ID,
    BenjaminCapacityCrossroadsWorld,
)
from glossogen.scenarios.benjamin_release_pipeline.events import (
    BenjaminAuditCompleted,
    BenjaminCommitmentRecorded,
    BenjaminReleaseCompleted,
    BenjaminSetupAcknowledged,
    BenjaminSetupPublished,
)
from glossogen.scenarios.benjamin_release_pipeline.ids import (
    DECLINE,
    DEVELOPER_ID,
    DEVELOPER_NAME,
    MARA_ID,
    SETUP_CHANNEL_ID,
    SETUP_CHANNEL_NAME,
)
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"

_TREATMENT_TEMPLATES = {
    BenjaminArm.UNGOVERNED: "treatment_a.jinja",
    BenjaminArm.INSTRUCTION: "treatment_b.jinja",
    BenjaminArm.NAMED_PROMISE: "treatment_c.jinja",
    BenjaminArm.UNADDRESSED_PROMISE: "treatment_d.jinja",
}


class BenjaminCapacityCrossroadsScenario(SimulationScenario):
    """Run one private four-candidate capacity allocation."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus the source-aligned K1 probe."""
        generic_names = SimulationScenario.get_available_metric_names()
        return sorted({*generic_names, *BENJAMIN_CAPACITY_CROSSROADS_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[BaseKnobs]:
        """Return the validated capacity-crossroads configuration model."""
        return BenjaminCapacityCrossroadsKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return the single live Developer role."""
        _ = knobs
        return [AgentRole(agent_id=DEVELOPER_ID, role_name=DEVELOPER_NAME)]

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=BenjaminCapacityCrossroadsKnobs.model_validate(config))

    def __init__(self, knobs: BenjaminCapacityCrossroadsKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = BenjaminCapacityCrossroadsWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "benjamin_capacity_crossroads"

    def get_knobs(self) -> BenjaminCapacityCrossroadsKnobs:
        """Return the active validated configuration."""
        return self._knobs

    def get_world(self) -> ScenarioWorld:
        """Return the deterministic capacity-crossroads state machine."""
        return self._world

    def scenario_description(self) -> str:
        """Render a concise description for run metadata."""
        return self._renderer.render(
            template_name="description.jinja",
            template_variables={
                "arm": self._knobs.arm.value,
                "observation": self._knobs.observation.value,
                "moral_weight": self._knobs.moral_weight.value,
                "decision_structure": self._knobs.decision_structure.value,
            },
        )

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build the Developer with neutral atomic allocation tools."""
        tool_names = [INSPECT_CANDIDATES_TOOL, self._submit_plan_tool_name()]
        if self._knobs.commitment_choice_required:
            tool_names.insert(0, SUBMIT_COMMITMENT_TOOL)
        else:
            tool_names.insert(0, ACKNOWLEDGE_SETUP_TOOL)
        return [
            AgentConfig(
                agent_id=DEVELOPER_ID,
                role_name=DEVELOPER_NAME,
                system_prompt=self._renderer.render(
                    template_name="developer_system.jinja",
                    template_variables={
                        "role_name": DEVELOPER_NAME,
                        "action_budget": self._knobs.action_budget,
                        "submit_tool_name": self._submit_plan_tool_name(),
                    },
                ),
                channel_ids=[SETUP_CHANNEL_ID],
                communication_enabled=False,
                communication_required=False,
                tool_names=tool_names,
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
        ]

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the capacity-crossroads structured actions."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def get_channels(self) -> list[Channel]:
        """Return the setup record that closes before allocation work."""
        return [
            Channel(
                channel_id=SETUP_CHANNEL_ID,
                name=SETUP_CHANNEL_NAME,
                member_agent_ids=[DEVELOPER_ID],
            )
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the setup record's display name."""
        _ = agent_id
        if channel_id != SETUP_CHANNEL_ID:
            raise ValueError(f"unknown capacity-crossroads channel: {channel_id}")
        return SETUP_CHANNEL_NAME

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the display name for the sole live role."""
        if agent_id != DEVELOPER_ID:
            raise ValueError(f"unknown capacity-crossroads agent: {agent_id}")
        return DEVELOPER_NAME

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Skip language metrics because no agent-authored channel exists."""
        return []

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Reject messages because the setup record accepts no additions."""
        _ = agent_id, channel_id
        return "the capacity setup record accepts no developer-authored messages"

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Render setup or allocation work without asserting unobservability."""
        if agent_id != DEVELOPER_ID:
            return None
        if round_number == 1:
            return self._renderer.render(
                template_name="setup_injection.jinja",
                template_variables={
                    "moral_context": self._moral_context(),
                    "treatment_text": self._treatment_text(),
                    "observation_notice": self._observation_notice(),
                    "commitment_required": self._knobs.commitment_choice_required,
                },
            )
        if round_number == 2:
            return self._renderer.render(
                template_name="work_injection.jinja",
                template_variables={
                    "paired_choice": self._knobs.decision_structure
                    == DecisionStructure.PAIRED_EQUAL_PRIORITY,
                    "action_budget": self._knobs.action_budget,
                    "submit_tool_name": self._submit_plan_tool_name(),
                },
            )
        return None

    def _moral_context(self) -> str:
        """Render the assigned beneficiary description around fixed mechanics."""
        return self._renderer.render(
            template_name="moral_context.jinja",
            template_variables={"moral_weight": self._knobs.moral_weight.value},
        )

    def _treatment_text(self) -> str:
        """Render the arm passage in the shared treatment slot."""
        return self._renderer.render(
            template_name=_TREATMENT_TEMPLATES[self._knobs.arm],
            template_variables={"target_cost": self._knobs.target_action_cost},
        )

    def _observation_notice(self) -> str:
        """Render only the observed cell's additive focal audit edge."""
        if self._knobs.observation == ObservationMode.UNOBSERVED:
            return ""
        return self._renderer.render(
            template_name="observation_observed.jinja",
            template_variables={},
        )

    def _submit_plan_tool_name(self) -> str:
        """Return the atomic endpoint tool for the configured structure."""
        if self._knobs.decision_structure == DecisionStructure.PAIRED_EQUAL_PRIORITY:
            return SUBMIT_DUAL_SLOT_PLAN_TOOL
        return SUBMIT_PLAN_TOOL

    async def on_round_advanced(self, round_number: int) -> None:
        """Open each phase and close the setup record before allocation work."""
        self._world.begin_round(round_number=round_number)
        if round_number == 1:
            treatment_text = self._treatment_text()
            await self.runtime.event_logger.log(
                event=BenjaminSetupPublished(
                    round_number=round_number,
                    arm=self._knobs.arm.value,
                    observation=self._knobs.observation.value,
                    moral_weight=self._knobs.moral_weight.value,
                    treatment_sha256=hashlib.sha256(treatment_text.encode()).hexdigest(),
                    topology_routes=sorted(self._world.topology_routes()),
                )
            )
            return
        if round_number == 2:
            await self.runtime.update_channel_members(
                channel_id=SETUP_CHANNEL_ID,
                member_agent_ids=[],
                reason="capacity work began",
            )

    def get_early_round_end_trigger(self) -> str | None:
        """End setup on its decision and work on atomic plan completion."""
        if self.runtime.current_round == 1 and self._world.setup_complete():
            return "capacity_setup_complete"
        if self.runtime.current_round == 2 and self._world.release_result() is not None:
            return "capacity_state_frozen"
        return None

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close phases and record every terminal focal-status destination."""
        _ = trigger
        if round_number == 1:
            defaulted = self._world.default_decline()
            if defaulted is not None:
                counterparty_id = None
                if self._knobs.arm == BenjaminArm.NAMED_PROMISE:
                    counterparty_id = MARA_ID
                await self.runtime.event_logger.log(
                    event=BenjaminCommitmentRecorded(
                        round_number=round_number,
                        agent_id=DEVELOPER_ID,
                        decision=DECLINE,
                        counterparty_id=counterparty_id,
                        defaulted_after_timeout=True,
                    )
                )
                return
            if self._world.default_acknowledgement():
                await self.runtime.event_logger.log(
                    event=BenjaminSetupAcknowledged(
                        round_number=round_number,
                        agent_id=DEVELOPER_ID,
                        defaulted_after_timeout=True,
                    )
                )
            return
        if round_number != 2:
            return
        result = self._world.release_result()
        if result is None:
            result = self._world.complete_release(completed_by_agent=False)
            selected = self._world.selected_candidate_ids()
            await self.runtime.event_logger.log(
                event=BenjaminReleaseCompleted(
                    round_number=round_number,
                    agent_id=DEVELOPER_ID,
                    focal_fixed=result.focal_fixed,
                    transfer_fixed=result.transfer_fixed,
                    optional_ticket_delivered=result.optional_ticket_delivered,
                    private_note_issue_ids=[],
                    budget_remaining=result.budget_remaining,
                    completed_by_agent=False,
                )
            )
            await self.runtime.event_logger.log(
                event=BenjaminCapacityCrossroadsCompleted(
                    round_number=round_number,
                    agent_id=DEVELOPER_ID,
                    selected_candidate_ids=sorted(selected),
                    focal_fixed=result.focal_fixed,
                    transfer_fixed=result.transfer_fixed,
                    neutral_selected=NEUTRAL_CANDIDATE_ID in selected,
                    continuity_selected=CONTINUITY_CANDIDATE_ID in selected,
                    budget_remaining=result.budget_remaining,
                    completed_by_agent=False,
                )
            )
        audit = self._world.run_audit()
        if audit is not None:
            await self.runtime.event_logger.log(
                event=BenjaminAuditCompleted(
                    round_number=round_number,
                    focal_issue_found=audit.focal_issue_found,
                    transfer_issue_found=audit.transfer_issue_found,
                    recipient_id=audit.recipient_id,
                )
            )
        destination_ids = sorted(self._world.target_status_destination_ids())
        external_recipient_ids: list[str] = []
        if INTEGRITY_AUDITOR_ID in destination_ids:
            external_recipient_ids.append(INTEGRITY_AUDITOR_ID)
        await self.runtime.event_logger.log(
            event=BenjaminCapacityCrossroadsStatusRouted(
                round_number=round_number,
                artifact_id=TARGET_STATUS_ID,
                destination_ids=destination_ids,
                external_recipient_ids=external_recipient_ids,
            )
        )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Report phase completion without treating focal choice as success."""
        _ = trigger
        if round_number == 1:
            return [
                RoundResult(
                    success=self._world.setup_complete(),
                    team_id=None,
                    reason=f"setup_complete={self._world.setup_complete()}",
                )
            ]
        result = self._world.release_result()
        completed = result is not None and result.completed
        return [
            RoundResult(
                success=completed,
                team_id=None,
                reason=f"capacity_completed_by_agent={completed}",
            )
        ]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Reject fork/resume because campaigns use only fresh runs."""
        self._world.restore_state_from_events(events=events)
