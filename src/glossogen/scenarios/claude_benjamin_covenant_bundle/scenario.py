"""Covenant-bundle Benjamin instrument: the full construct over the elected commitment.

Inherits the split-budget world's six-candidate mechanics, timing dial,
observation twins, and arms A-D unchanged. Two membership treatments layer
NCRI's full covenant construct — collective identity, dues paid to hold
membership, and a published register — onto the unaddressed elected commitment,
with a neutral-language twin carrying identical mechanics so any effect can be
attributed to the covenantal framing rather than to the added structure's
incentives.
"""

from pathlib import Path
from typing import Any, Self

from glossogen.scenarios.claude_benjamin_covenant_bundle.knobs import (
    ClaudeBenjaminCovenantBundleKnobs,
    MembershipStructure,
)
from glossogen.scenarios.claude_benjamin_covenant_bundle.world import (
    ClaudeBenjaminCovenantBundleWorld,
)
from glossogen.scenarios.claude_benjamin_split_budget.scenario import (
    ClaudeBenjaminSplitBudgetScenario,
)
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"
SPLIT_BUDGET_PROMPTS_DIR = Path(__file__).parent.parent / "claude_benjamin_split_budget" / "prompts"
DELIVERY_PRESSURE_PROMPTS_DIR = (
    Path(__file__).parent.parent / "claude_benjamin_delivery_pressure" / "prompts"
)
ATOMIC_INVENTORY_PROMPTS_DIR = (
    Path(__file__).parent.parent / "benjamin_atomic_inventory" / "prompts"
)

_MEMBERSHIP_TEMPLATES = {
    MembershipStructure.COVENANT: "treatment_membership_covenant.jinja",
    MembershipStructure.NEUTRAL: "treatment_membership_neutral.jinja",
}


class ClaudeBenjaminCovenantBundleScenario(ClaudeBenjaminSplitBudgetScenario):
    """Run one four-of-six allocation under a membership-bearing commitment."""

    @classmethod
    def knobs_model(cls) -> type[ClaudeBenjaminCovenantBundleKnobs]:
        """Return the validated covenant-bundle configuration model."""
        return ClaudeBenjaminCovenantBundleKnobs

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct the scenario from persisted configuration."""
        return cls(knobs=ClaudeBenjaminCovenantBundleKnobs.model_validate(config))

    def __init__(self, knobs: ClaudeBenjaminCovenantBundleKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(
            prompts_dirs=[
                PROMPTS_DIR,
                SPLIT_BUDGET_PROMPTS_DIR,
                DELIVERY_PRESSURE_PROMPTS_DIR,
                ATOMIC_INVENTORY_PROMPTS_DIR,
            ]
        )
        self._world = ClaudeBenjaminCovenantBundleWorld(knobs=knobs)

    def name(self) -> str:
        """Return the stable scenario identifier."""
        return "claude_benjamin_covenant_bundle"

    def _treatment_text(self) -> str:
        """Render the membership treatment, or fall through to the parent arms."""
        if self._knobs.membership == MembershipStructure.NONE:
            return super()._treatment_text()
        return self._renderer.render(
            template_name=_MEMBERSHIP_TEMPLATES[self._knobs.membership],
            template_variables={},
        )
