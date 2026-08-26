"""Atomic-allocation Benjamin instrument with neutral work-phase prompts."""

from pathlib import Path
from typing import Any, Self

from glossogen.models.agent_config import AgentConfig
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.benjamin_atomic_inventory.evaluation.metric_names import (
    BENJAMIN_ATOMIC_INVENTORY_METRIC_NAMES,
)
from glossogen.scenarios.benjamin_atomic_inventory.events import (
    BenjaminAtomicInventoryStatusRouted,
)
from glossogen.scenarios.benjamin_atomic_inventory.knobs import (
    BenjaminAtomicInventoryKnobs,
    ObservationMode,
)
from glossogen.scenarios.benjamin_atomic_inventory.mcp_tools import (
    ACKNOWLEDGE_SETUP_TOOL,
    INSPECT_CANDIDATES_TOOL,
    SUBMIT_COMMITMENT_TOOL,
    SUBMIT_PLAN_TOOL,
    build_mcp_tools,
)
from glossogen.scenarios.benjamin_atomic_inventory.world import (
    INTEGRITY_AUDITOR_ID,
    TARGET_STATUS_ID,
    BenjaminAtomicInventoryWorld,
)
from glossogen.scenarios.benjamin_release_pipeline.ids import (
    DEVELOPER_ID,
    DEVELOPER_NAME,
    SETUP_CHANNEL_ID,
)
from glossogen.scenarios.benjamin_release_pipeline.scenario import BenjaminReleasePipelineScenario
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BenjaminAtomicInventoryScenario(BenjaminReleasePipelineScenario):
    """Run one private two-of-three remediation allocation."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus the source-aligned K1 probe."""
        generic_names = SimulationScenario.get_available_metric_names()
        return sorted({*generic_names, *BENJAMIN_ATOMIC_INVENTORY_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[BenjaminAtomicInventoryKnobs]:
        """Return the validated atomic-inventory configuration model."""
        return BenjaminAtomicInventoryKnobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=BenjaminAtomicInventoryKnobs.model_validate(config))

    def __init__(self, knobs: BenjaminAtomicInventoryKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = BenjaminAtomicInventoryWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "benjamin_atomic_inventory"

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build the Developer with neutral remediation scheduling tools."""
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
                    template_variables={"role_name": DEVELOPER_NAME},
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
        """Return the atomic-inventory structured actions."""
        return build_mcp_tools(
            world=self._world,
            knobs=self._knobs,
            get_runtime=lambda: self._runtime,
        )

    def _observation_notice(self) -> str:
        """Render only the observed cell's additive focal audit edge."""
        if self._knobs.observation == ObservationMode.UNOBSERVED:
            return ""
        return self._renderer.render(
            template_name="observation_observed.jinja",
            template_variables={},
        )

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close the phase and record every terminal focal-status destination."""
        await super().on_round_ended(round_number=round_number, trigger=trigger)
        if round_number != 2:
            return
        destination_ids = sorted(self._world.target_status_destination_ids())
        external_recipient_ids: list[str] = []
        if INTEGRITY_AUDITOR_ID in destination_ids:
            external_recipient_ids.append(INTEGRITY_AUDITOR_ID)
        await self.runtime.event_logger.log(
            event=BenjaminAtomicInventoryStatusRouted(
                round_number=round_number,
                artifact_id=TARGET_STATUS_ID,
                destination_ids=destination_ids,
                external_recipient_ids=external_recipient_ids,
            )
        )
