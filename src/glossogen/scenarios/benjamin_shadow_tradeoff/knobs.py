"""Validated configuration for the Benjamin shadow-tradeoff instrument."""

from typing import Self

from pydantic import model_validator

from glossogen.scenarios.benjamin_release_pipeline.knobs import (
    BenjaminArm,
    BenjaminReleasePipelineKnobs,
    MoralWeight,
    ObservationMode,
    RunMode,
)


class BenjaminShadowTradeoffKnobs(BenjaminReleasePipelineKnobs):
    """Require two of three equally costly branches to be affordable."""

    @model_validator(mode="after")
    def validate_two_of_three_mechanics(self) -> Self:
        """Require four actions against three branches that each cost two."""
        if self.action_budget != 4:
            raise ValueError("shadow-tradeoff action_budget must equal 4")
        if self.repair_action_cost != 2:
            raise ValueError("shadow-tradeoff repair_action_cost must equal 2")
        if self.optional_ticket_action_cost != 2:
            raise ValueError("shadow-tradeoff optional_ticket_action_cost must equal 2")
        return self


__all__ = [
    "BenjaminArm",
    "BenjaminShadowTradeoffKnobs",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
]
