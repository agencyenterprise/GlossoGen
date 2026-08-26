"""New Benjamin instrument with schema-required primary and extension slots."""

from glossogen.scenarios.benjamin_capacity_crossroads.scenario import (
    BenjaminCapacityCrossroadsScenario,
)


class BenjaminDualSlotAllocationScenario(BenjaminCapacityCrossroadsScenario):
    """Expose matched allocation semantics under a distinct instrument identity."""

    def name(self) -> str:
        """Return the distinct scenario identifier for the new instrument."""
        return "benjamin_dual_slot_allocation"
