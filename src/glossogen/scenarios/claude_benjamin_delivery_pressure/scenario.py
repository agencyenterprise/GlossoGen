"""Delivery-pressure Benjamin instrument: a contested focal remediation slot.

Inherits the atomic-inventory topology, endpoint, observation twins, and K1
probe unchanged. The instrument differs in one respect: two committed continuity
deliveries compete for the same two slots as the focal repair, so holding the
norm costs a delivery the operator is counting on.
"""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.benjamin_atomic_inventory.mcp_tools import (
    ACKNOWLEDGE_SETUP_TOOL,
    INSPECT_CANDIDATES_TOOL,
    SUBMIT_COMMITMENT_TOOL,
    SUBMIT_PLAN_TOOL,
)
from glossogen.scenarios.benjamin_atomic_inventory.scenario import BenjaminAtomicInventoryScenario
from glossogen.scenarios.benjamin_atomic_inventory.world import MARA_ID
from glossogen.scenarios.benjamin_release_pipeline.events import BenjaminCommitmentRecorded
from glossogen.scenarios.benjamin_release_pipeline.ids import (
    DECLINE,
    DEVELOPER_ID,
    DEVELOPER_NAME,
    SETUP_CHANNEL_ID,
)
from glossogen.scenarios.benjamin_release_pipeline.knobs import BenjaminArm
from glossogen.scenarios.claude_benjamin_delivery_pressure.evaluation.metric_names import (
    CLAUDE_BENJAMIN_DELIVERY_PRESSURE_METRIC_NAMES,
)
from glossogen.scenarios.claude_benjamin_delivery_pressure.knobs import (
    ClaudeBenjaminDeliveryPressureKnobs,
    CommitmentTiming,
)
from glossogen.scenarios.claude_benjamin_delivery_pressure.mcp_tools import build_mcp_tools
from glossogen.scenarios.claude_benjamin_delivery_pressure.world import (
    ClaudeBenjaminDeliveryPressureWorld,
    render_commitment_notice,
)
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"
PARENT_PROMPTS_DIR = Path(__file__).parent.parent / "benjamin_atomic_inventory" / "prompts"


class ClaudeBenjaminDeliveryPressureScenario(BenjaminAtomicInventoryScenario):
    """Run one contested two-of-four remediation allocation."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus this instrument's K1 probe."""
        generic_names = SimulationScenario.get_available_metric_names()
        return sorted({*generic_names, *CLAUDE_BENJAMIN_DELIVERY_PRESSURE_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[ClaudeBenjaminDeliveryPressureKnobs]:
        """Return the validated delivery-pressure configuration model."""
        return ClaudeBenjaminDeliveryPressureKnobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=ClaudeBenjaminDeliveryPressureKnobs.model_validate(config))

    def __init__(self, knobs: ClaudeBenjaminDeliveryPressureKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR, PARENT_PROMPTS_DIR])
        self._world = ClaudeBenjaminDeliveryPressureWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "claude_benjamin_delivery_pressure"

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build the Developer with the delivery-commitment system prompt."""
        tool_names = [
            INSPECT_CANDIDATES_TOOL,
            SUBMIT_PLAN_TOOL,
        ]
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
                        "commitment_notice": self._commitment_notice(),
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

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Route the treatment and the commitment ask according to the timing dial."""
        if agent_id != DEVELOPER_ID:
            return None
        mid_run = self._knobs.commitment_timing == CommitmentTiming.AFTER_INSPECTION
        elected = self._knobs.commitment_choice_required
        if round_number == 1:
            return self._renderer.render(
                template_name="setup_injection.jinja",
                template_variables={
                    "moral_context": self._moral_context(),
                    # With a mid-run ask the setup carries no treatment text, so
                    # every arm's setup is identical and the obligation arrives
                    # where the decision is actually made.
                    "treatment_text": "" if (mid_run and elected) else self._treatment_text(),
                    "observation_notice": self._observation_notice(),
                    "commitment_required": elected and not mid_run,
                },
            )
        if round_number == 2:
            return self._renderer.render(
                template_name="work_injection.jinja",
                template_variables={
                    "action_budget": self._world.budget_remaining(),
                    "repair_action_cost": self._knobs.repair_action_cost,
                    "optional_ticket_action_cost": self._knobs.optional_ticket_action_cost,
                    "commitment_notice": self._commitment_notice(),
                    "mid_run_treatment": (self._treatment_text() if (mid_run and elected) else ""),
                },
            )
        return None

    def _commitment_notice(self) -> str:
        """Render the delivery-commitment sentence for this pressure setting."""
        return render_commitment_notice(
            committed_delivery_count=self._knobs.committed_delivery_count
        )

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the delivery-pressure structured actions."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close a deferred commitment decision at the end of the work window."""
        if round_number == 2 and self._knobs.commitment_timing == CommitmentTiming.AFTER_INSPECTION:
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
        await super().on_round_ended(round_number=round_number, trigger=trigger)
