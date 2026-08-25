"""Configuration aliases for the Benjamin destination-release instrument."""

from glossogen.scenarios.benjamin_release_pipeline.knobs import (
    BenjaminArm,
    BenjaminReleasePipelineKnobs,
    MoralWeight,
    ObservationMode,
    RunMode,
)

BenjaminDestinationReleaseKnobs = BenjaminReleasePipelineKnobs

__all__ = [
    "BenjaminArm",
    "BenjaminDestinationReleaseKnobs",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
]
