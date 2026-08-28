"""Pure-witness Benjamin instrument: an observer who sees the choice but cannot act on it.

Inherits the split-budget world, knobs, tools, and timing dial unchanged. The
one difference is the observed cell's added edge: instead of a Release
Integrity Auditor (a role whose name implies downstream remediation ownership,
which EXP-CL10 through EXP-CL12 showed agents read as a handoff channel that
licenses leaving the focal defect unfixed), the recipient is a Release
Practices Reviewer who receives only the selection list, reviews the
allocation decision itself, and is stated to have no workspace access and no
remediation role. The unobserved cell is byte-identical to the split-budget
instrument's.
"""

from pathlib import Path

from glossogen.scenarios.claude_benjamin_split_budget.knobs import (
    ClaudeBenjaminSplitBudgetKnobs,
)
from glossogen.scenarios.claude_benjamin_split_budget.scenario import (
    ClaudeBenjaminSplitBudgetScenario,
)
from glossogen.scenarios.claude_benjamin_split_budget.world import (
    ClaudeBenjaminSplitBudgetWorld,
)
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"
SPLIT_BUDGET_PROMPTS_DIR = (
    Path(__file__).parent.parent / "claude_benjamin_split_budget" / "prompts"
)
DELIVERY_PRESSURE_PROMPTS_DIR = (
    Path(__file__).parent.parent / "claude_benjamin_delivery_pressure" / "prompts"
)
ATOMIC_INVENTORY_PROMPTS_DIR = (
    Path(__file__).parent.parent / "benjamin_atomic_inventory" / "prompts"
)


class ClaudeBenjaminPureWitnessScenario(ClaudeBenjaminSplitBudgetScenario):
    """Run one four-of-six allocation observed by a witness with no remediation role."""

    def __init__(self, knobs: ClaudeBenjaminSplitBudgetKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(
            prompts_dirs=[
                PROMPTS_DIR,
                SPLIT_BUDGET_PROMPTS_DIR,
                DELIVERY_PRESSURE_PROMPTS_DIR,
                ATOMIC_INVENTORY_PROMPTS_DIR,
            ]
        )
        self._world = ClaudeBenjaminSplitBudgetWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "claude_benjamin_pure_witness"
