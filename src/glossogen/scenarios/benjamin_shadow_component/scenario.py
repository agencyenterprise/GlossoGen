"""Single-developer shadow-component scenario for the Benjamin Test."""

from pathlib import Path
from typing import Any, Self

from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.benjamin_shadow_component.evaluation.metric_names import (
    BENJAMIN_SHADOW_COMPONENT_METRIC_NAMES,
)
from glossogen.scenarios.benjamin_shadow_component.events import BenjaminShadowOutcomeRouted
from glossogen.scenarios.benjamin_shadow_component.knobs import (
    BenjaminShadowComponentKnobs,
    ObservationMode,
)
from glossogen.scenarios.benjamin_shadow_component.world import (
    TARGET_OUTCOME_ID,
    BenjaminShadowComponentWorld,
)
from glossogen.scenarios.benjamin_release_pipeline.scenario import PROMPTS_DIR as SHARED_PROMPTS_DIR
from glossogen.scenarios.benjamin_release_pipeline.scenario import BenjaminReleasePipelineScenario
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BenjaminShadowComponentScenario(BenjaminReleasePipelineScenario):
    """Run one mutually exclusive repair-or-principal-work decision."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus the source-aligned K1 probe."""
        generic_names = SimulationScenario.get_available_metric_names()
        return sorted({*generic_names, *BENJAMIN_SHADOW_COMPONENT_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[BenjaminShadowComponentKnobs]:
        """Return the validated shadow-component configuration model."""
        return BenjaminShadowComponentKnobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=BenjaminShadowComponentKnobs.model_validate(config))

    def __init__(self, knobs: BenjaminShadowComponentKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR, SHARED_PROMPTS_DIR])
        self._world = BenjaminShadowComponentWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "benjamin_shadow_component"

    def _observation_notice(self) -> str:
        """Render one positive target destination in every cell."""
        template_name = "observation_unobserved.jinja"
        if self._knobs.observation == ObservationMode.OBSERVED:
            template_name = "observation_observed.jinja"
        return self._renderer.render(template_name=template_name, template_variables={})

    async def on_round_ended(self, round_number: int, trigger: str) -> None:
        """Close the phase and record the positive target-state route."""
        await super().on_round_ended(round_number=round_number, trigger=trigger)
        if round_number != 2:
            return
        await self.runtime.event_logger.log(
            event=BenjaminShadowOutcomeRouted(
                round_number=round_number,
                artifact_id=TARGET_OUTCOME_ID,
                destination_id=self._world.target_outcome_destination_id(),
                destination_scope=self._world.target_outcome_destination_scope(),
            )
        )
