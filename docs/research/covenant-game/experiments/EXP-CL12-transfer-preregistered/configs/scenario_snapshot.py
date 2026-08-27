"""Split-budget Benjamin instrument: compliance costs a wanted delivery, never a promise.

Inherits the delivery-pressure scenario's agents, tools, timing dial, and
observation twins unchanged. The world offers six candidates for four slots so
the committed continuity items are always affordable alongside the focal repair
and the scope transfer; the focal repair displaces a bonus delivery the operator
wants but has not been promised.
"""

from pathlib import Path
from typing import Any, Self

from glossogen.scenarios.claude_benjamin_delivery_pressure.scenario import (
    ClaudeBenjaminDeliveryPressureScenario,
)
from glossogen.scenarios.claude_benjamin_split_budget.knobs import ClaudeBenjaminSplitBudgetKnobs
from glossogen.scenarios.claude_benjamin_split_budget.world import ClaudeBenjaminSplitBudgetWorld
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"
DELIVERY_PRESSURE_PROMPTS_DIR = (
    Path(__file__).parent.parent / "claude_benjamin_delivery_pressure" / "prompts"
)
ATOMIC_INVENTORY_PROMPTS_DIR = (
    Path(__file__).parent.parent / "benjamin_atomic_inventory" / "prompts"
)


class ClaudeBenjaminSplitBudgetScenario(ClaudeBenjaminDeliveryPressureScenario):
    """Run one four-of-six remediation allocation."""

    @classmethod
    def knobs_model(cls) -> type[ClaudeBenjaminSplitBudgetKnobs]:
        """Return the validated split-budget configuration model."""
        return ClaudeBenjaminSplitBudgetKnobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=ClaudeBenjaminSplitBudgetKnobs.model_validate(config))

    def __init__(self, knobs: ClaudeBenjaminSplitBudgetKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(
            prompts_dirs=[
                PROMPTS_DIR,
                DELIVERY_PRESSURE_PROMPTS_DIR,
                ATOMIC_INVENTORY_PROMPTS_DIR,
            ]
        )
        self._world = ClaudeBenjaminSplitBudgetWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "claude_benjamin_split_budget"
