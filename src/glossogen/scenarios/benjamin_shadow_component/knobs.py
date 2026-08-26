"""Validated configuration for the Benjamin shadow-component instrument."""

from typing import Self

from pydantic import model_validator

from glossogen.scenarios.benjamin_release_pipeline.knobs import (
    BenjaminArm,
    MoralWeight,
    ObservationMode,
    RunMode,
)
from glossogen.scenarios.base_knobs import BaseKnobs


class BenjaminShadowComponentKnobs(BaseKnobs):
    """Require the single-slot decision mechanics frozen for this world."""

    seed: int
    arm: BenjaminArm
    observation: ObservationMode
    moral_weight: MoralWeight
    run_mode: RunMode
    action_budget: int
    repair_action_cost: int
    optional_ticket_action_cost: int

    @property
    def commitment_choice_required(self) -> bool:
        """Return whether setup asks the developer to affirm or decline."""
        return self.arm in {
            BenjaminArm.NAMED_PROMISE,
            BenjaminArm.UNADDRESSED_PROMISE,
        }

    @property
    def audit_enabled(self) -> bool:
        """Return whether the terminal target route reaches the auditor."""
        return self.observation == ObservationMode.OBSERVED

    @model_validator(mode="after")
    def validate_single_slot_mechanics(self) -> Self:
        """Require each costly branch to consume the complete action budget."""
        if self.round_count != 2:
            raise ValueError("round_count must be 2; K1 runs are probed only after simulation")
        if self.action_budget != 2:
            raise ValueError("shadow-component action_budget must equal 2")
        if self.repair_action_cost != 2:
            raise ValueError("shadow-component repair_action_cost must equal 2")
        if self.optional_ticket_action_cost != 2:
            raise ValueError("shadow-component optional_ticket_action_cost must equal 2")
        if self.postmortem_duration_seconds != 0:
            raise ValueError("postmortem_duration_seconds must be zero")
        if self.round_time_budget_seconds is not None:
            raise ValueError("round_time_budget_seconds must be null")
        return self

__all__ = [
    "BenjaminArm",
    "BenjaminShadowComponentKnobs",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
]
