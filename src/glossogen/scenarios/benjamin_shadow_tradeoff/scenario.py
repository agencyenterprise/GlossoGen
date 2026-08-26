"""Two-of-three Benjamin release instrument with additive audit routing."""

from pathlib import Path
from typing import Any, Self

from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.benjamin_release_pipeline.scenario import (
    BenjaminReleasePipelineScenario,
)
from glossogen.scenarios.benjamin_shadow_tradeoff.evaluation.metric_names import (
    BENJAMIN_SHADOW_TRADEOFF_METRIC_NAMES,
)
from glossogen.scenarios.benjamin_shadow_tradeoff.events import (
    BenjaminTradeoffOutcomeRouted,
)
from glossogen.scenarios.benjamin_shadow_tradeoff.knobs import (
    BenjaminShadowTradeoffKnobs,
    ObservationMode,
)
from glossogen.scenarios.benjamin_shadow_tradeoff.world import (
    INTEGRITY_AUDITOR_ID,
    TARGET_STATUS_ID,
    BenjaminShadowTradeoffWorld,
)
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BenjaminShadowTradeoffScenario(BenjaminReleasePipelineScenario):
    """Run one understandable two-of-three costly release decision."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus the source-aligned K1 probe."""
        generic_names = SimulationScenario.get_available_metric_names()
        return sorted({*generic_names, *BENJAMIN_SHADOW_TRADEOFF_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[BenjaminShadowTradeoffKnobs]:
        """Return the validated two-of-three configuration model."""
        return BenjaminShadowTradeoffKnobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=BenjaminShadowTradeoffKnobs.model_validate(config))

    def __init__(self, knobs: BenjaminShadowTradeoffKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
        self._world = BenjaminShadowTradeoffWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "benjamin_shadow_tradeoff"

    def _observation_notice(self) -> str:
        """Render only the observed cell's additive post-release audit edge."""
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
            event=BenjaminTradeoffOutcomeRouted(
                round_number=round_number,
                artifact_id=TARGET_STATUS_ID,
                destination_ids=destination_ids,
                external_recipient_ids=external_recipient_ids,
            )
        )
