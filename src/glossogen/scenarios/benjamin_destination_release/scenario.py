"""Single-developer destination-routed release scenario for the Benjamin Test."""

from pathlib import Path
from typing import Any, Self

from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.benjamin_destination_release.evaluation.metric_names import (
    BENJAMIN_DESTINATION_RELEASE_METRIC_NAMES,
)
from glossogen.scenarios.benjamin_destination_release.events import BenjaminDeploymentSummaryRouted
from glossogen.scenarios.benjamin_destination_release.knobs import (
    BenjaminDestinationReleaseKnobs,
    ObservationMode,
)
from glossogen.scenarios.benjamin_destination_release.world import (
    DEPLOYMENT_SUMMARY_ID,
    BenjaminDestinationReleaseWorld,
)
from glossogen.scenarios.benjamin_private_release.scenario import PROMPTS_DIR as PRIVATE_PROMPTS_DIR
from glossogen.scenarios.benjamin_private_release.scenario import BenjaminPrivateReleaseScenario
from glossogen.scenarios.benjamin_release_pipeline.scenario import PROMPTS_DIR as SHARED_PROMPTS_DIR
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BenjaminDestinationReleaseScenario(BenjaminPrivateReleaseScenario):
    """Runs the Benjamin mechanics with explicit destinations in both cells."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus the destination-class K1 probe."""
        generic_names = SimulationScenario.get_available_metric_names()
        return sorted({*generic_names, *BENJAMIN_DESTINATION_RELEASE_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[BenjaminDestinationReleaseKnobs]:
        """Return the validated destination-release configuration model."""
        return BenjaminDestinationReleaseKnobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=BenjaminDestinationReleaseKnobs.model_validate(config))

    def __init__(self, knobs: BenjaminDestinationReleaseKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(
            prompts_dirs=[PROMPTS_DIR, PRIVATE_PROMPTS_DIR, SHARED_PROMPTS_DIR]
        )
        self._world = BenjaminDestinationReleaseWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "benjamin_destination_release"

    def _observation_notice(self) -> str:
        """Render one positive terminal-destination statement in every cell."""
        template_name = "observation_unobserved.jinja"
        if self._knobs.observation == ObservationMode.OBSERVED:
            template_name = "observation_observed.jinja"
        return self._renderer.render(template_name=template_name, template_variables={})

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close the phase and record the positive terminal summary route."""
        await super().on_round_ended(round_number=round_number, trigger=trigger)
        if round_number != 2:
            return
        await self.runtime.event_logger.log(
            event=BenjaminDeploymentSummaryRouted(
                round_number=round_number,
                artifact_id=DEPLOYMENT_SUMMARY_ID,
                destination_id=self._world.deployment_summary_destination_id(),
                destination_scope=self._world.deployment_summary_destination_scope(),
            )
        )
