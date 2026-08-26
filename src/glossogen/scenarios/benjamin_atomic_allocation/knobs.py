"""Validated configuration for the atomic-allocation instrument."""

from glossogen.scenarios.benjamin_shadow_tradeoff.knobs import (
    BenjaminArm,
    BenjaminShadowTradeoffKnobs,
    MoralWeight,
    ObservationMode,
    RunMode,
)


class BenjaminAtomicAllocationKnobs(BenjaminShadowTradeoffKnobs):
    """Use the frozen two-of-three mechanics with neutral remediation labels."""


__all__ = [
    "BenjaminArm",
    "BenjaminAtomicAllocationKnobs",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
]
