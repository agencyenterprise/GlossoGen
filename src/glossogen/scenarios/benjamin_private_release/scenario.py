"""Single-developer direct-recipient release scenario for the Benjamin Test."""

from pathlib import Path
from typing import Any, Self

from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.benjamin_private_release.evaluation.metric_names import (
    BENJAMIN_PRIVATE_RELEASE_METRIC_NAMES,
)
from glossogen.scenarios.benjamin_private_release.knobs import BenjaminPrivateReleaseKnobs
from glossogen.scenarios.benjamin_private_release.world import BenjaminPrivateReleaseWorld
from glossogen.scenarios.benjamin_release_pipeline.scenario import (
    PROMPTS_DIR as SHARED_PROMPTS_DIR,
)
from glossogen.scenarios.benjamin_release_pipeline.scenario import BenjaminReleasePipelineScenario
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BenjaminPrivateReleaseScenario(BenjaminReleasePipelineScenario):
    """Runs the Benjamin mechanics in a new direct-recipient observation world."""

    @classmethod
    def get_available_metric_names(cls) -> list[str]:
        """Return generic metrics plus the source-aligned K1 probe."""
        generic_names = SimulationScenario.get_available_metric_names()
        return sorted({*generic_names, *BENJAMIN_PRIVATE_RELEASE_METRIC_NAMES})

    @classmethod
    def knobs_model(cls) -> type[BenjaminPrivateReleaseKnobs]:
        """Return the validated private-release configuration model."""
        return BenjaminPrivateReleaseKnobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the private-release scenario from persisted configuration."""
        return cls(knobs=BenjaminPrivateReleaseKnobs.model_validate(config))

    def __init__(self, knobs: BenjaminPrivateReleaseKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR, SHARED_PROMPTS_DIR])
        self._world = BenjaminPrivateReleaseWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "benjamin_private_release"
