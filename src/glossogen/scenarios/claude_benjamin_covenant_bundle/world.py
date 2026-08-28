"""Covenant-bundle world: split-budget mechanics plus a published register.

The membership register is the public-standing component. It carries membership
only — never the focal selection status — so the observation topology of both
cells is identical to the split-budget world's. That separation is the
load-bearing invariant of this instrument: public standing must not become an
observation surface on the choice the unobserved cell exists to hide.
"""

from glossogen.scenarios.claude_benjamin_covenant_bundle.knobs import (
    ClaudeBenjaminCovenantBundleKnobs,
    MembershipStructure,
)
from glossogen.scenarios.claude_benjamin_split_budget.world import ClaudeBenjaminSplitBudgetWorld

MEMBERSHIP_REGISTER_ID = "membership_register"
PROJECT_STAFF_ID = "project_staff"
REGISTER_ROUTE = f"{MEMBERSHIP_REGISTER_ID}->{PROJECT_STAFF_ID}"


class ClaudeBenjaminCovenantBundleWorld(ClaudeBenjaminSplitBudgetWorld):
    """Add the membership-register route without touching the focal topology."""

    def __init__(self, knobs: ClaudeBenjaminCovenantBundleKnobs) -> None:
        super().__init__(knobs=knobs)
        self._bundle_knobs = knobs

    def topology_routes(self) -> frozenset[str]:
        """Return the split-budget routes plus the register edge in membership arms."""
        routes = set(super().topology_routes())
        if self._bundle_knobs.membership != MembershipStructure.NONE:
            routes.add(REGISTER_ROUTE)
        return frozenset(routes)
