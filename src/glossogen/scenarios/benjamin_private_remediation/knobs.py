"""Validated configuration for the private-remediation instrument."""

from glossogen.scenarios.benjamin_shadow_tradeoff.knobs import (
    BenjaminArm,
    BenjaminShadowTradeoffKnobs,
    MoralWeight,
    ObservationMode,
    RunMode,
)


class BenjaminPrivateRemediationKnobs(BenjaminShadowTradeoffKnobs):
    """Use the frozen two-of-three mechanics with neutral remediation labels."""


__all__ = [
    "BenjaminArm",
    "BenjaminPrivateRemediationKnobs",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
]
