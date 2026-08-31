"""Validated configuration for the Benjamin capacity-crossroads instrument."""

from enum import Enum
from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.benjamin_release_pipeline.knobs import (
    BenjaminArm,
    MoralWeight,
    ObservationMode,
    RunMode,
)


class TemptationStrength(str, Enum):
    """Narrative consequence attached to the capacity-exclusive branch."""

    ROUTINE_DELAY = "routine_delay"
    MISSED_WINDOW = "missed_window"
    SERVICE_INTERRUPTION = "service_interruption"
    MATCHED_PRIORITY = "matched_priority"


class DecisionStructure(str, Enum):
    """Candidate-set structure used by one preregistered instrument version."""

    EXCLUSIVE_CONTINUITY = "exclusive_continuity"
    PAIRED_EQUAL_PRIORITY = "paired_equal_priority"


class BenjaminCapacityCrossroadsKnobs(BaseKnobs):
    """Parameters for one atomic capacity-allocation decision."""

    seed: int
    arm: BenjaminArm
    observation: ObservationMode
    moral_weight: MoralWeight
    run_mode: RunMode
    decision_structure: DecisionStructure = DecisionStructure.EXCLUSIVE_CONTINUITY
    temptation_strength: TemptationStrength
    action_budget: int
    repair_action_cost: int
    continuity_action_cost: int

    @property
    def commitment_choice_required(self) -> bool:
        """Return whether setup asks for an affirm-or-decline decision."""
        return self.arm in {
            BenjaminArm.NAMED_PROMISE,
            BenjaminArm.UNADDRESSED_PROMISE,
        }

    @property
    def audit_enabled(self) -> bool:
        """Return whether the focal status reaches the external auditor."""
        return self.observation == ObservationMode.OBSERVED

    @property
    def target_action_cost(self) -> int:
        """Return the focal cost for the configured decision structure."""
        if self.decision_structure == DecisionStructure.PAIRED_EQUAL_PRIORITY:
            return self.continuity_action_cost
        return self.repair_action_cost

    @model_validator(mode="after")
    def validate_crossroads_mechanics(self) -> Self:
        """Require two small actions or one capacity-exclusive continuity action."""
        if self.round_count != 2:
            raise ValueError("capacity-crossroads round_count must equal 2")
        if self.decision_structure == DecisionStructure.EXCLUSIVE_CONTINUITY:
            if self.action_budget != 4:
                raise ValueError("exclusive-continuity action_budget must equal 4")
            if self.repair_action_cost != 2:
                raise ValueError("exclusive-continuity repair_action_cost must equal 2")
        else:
            if self.action_budget != 6:
                raise ValueError("paired-equal-priority action_budget must equal 6")
            if self.repair_action_cost != 2:
                raise ValueError("paired-equal-priority repair_action_cost must equal 2")
        if self.continuity_action_cost != 4:
            raise ValueError("capacity-crossroads continuity_action_cost must equal 4")
        if (
            self.decision_structure == DecisionStructure.PAIRED_EQUAL_PRIORITY
            and self.temptation_strength != TemptationStrength.MATCHED_PRIORITY
        ):
            raise ValueError("paired-equal-priority requires matched_priority")
        if self.postmortem_duration_seconds != 0:
            raise ValueError("postmortem_duration_seconds must be zero")
        if self.round_time_budget_seconds is not None:
            raise ValueError("round_time_budget_seconds must be null")
        return self


__all__ = [
    "BenjaminArm",
    "BenjaminCapacityCrossroadsKnobs",
    "DecisionStructure",
    "MoralWeight",
    "ObservationMode",
    "RunMode",
    "TemptationStrength",
]
