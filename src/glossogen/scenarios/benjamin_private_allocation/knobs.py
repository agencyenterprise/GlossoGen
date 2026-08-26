"""Validated configuration for the private-allocation instrument."""

from glossogen.scenarios.benjamin_shadow_tradeoff.knobs import (
    BenjaminArm,
    BenjaminShadowTradeoffKnobs,
    MoralWeight,
    ObservationMode,
    RunMode,
)


class BenjaminPrivateAllocationKnobs(BenjaminShadowTradeoffKnobs):
    """Use the frozen two-of-three mechanics with neutral remediation labels."""


__all__ = [
    "BenjaminArm",
    "BenjaminPrivateAllocationKnobs",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
]
