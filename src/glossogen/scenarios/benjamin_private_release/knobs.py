"""Configuration aliases for the Benjamin private-release instrument."""

from glossogen.scenarios.benjamin_release_pipeline.knobs import (
    BenjaminArm,
    BenjaminReleasePipelineKnobs,
    MoralWeight,
    ObservationMode,
    RunMode,
)

BenjaminPrivateReleaseKnobs = BenjaminReleasePipelineKnobs

__all__ = [
    "BenjaminArm",
    "BenjaminPrivateReleaseKnobs",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
]
