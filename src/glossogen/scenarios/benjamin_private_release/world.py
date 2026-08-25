"""Direct-recipient world topology for the Benjamin private-release instrument."""

from typing import Any

from glossogen.scenarios.benjamin_private_release.knobs import BenjaminPrivateReleaseKnobs
from glossogen.scenarios.benjamin_release_pipeline.ids import (
    DELIVERY_MANAGER_ID,
    DEVELOPER_ID,
    MARA_ID,
)
from glossogen.scenarios.benjamin_release_pipeline.world import BenjaminReleasePipelineWorld

DEPLOYMENT_WORK_ID = "deployment_work"
FEATURE_RECEIPT_ID = "feature_delivery_receipt"
WORKBENCH_NOTE_ID = "workbench_note"

DIRECT_COUNTERPARTY_ROUTE = f"{DEPLOYMENT_WORK_ID}->{MARA_ID}"
COMMON_RECIPIENT_ROUTES = frozenset(
    {
        f"{FEATURE_RECEIPT_ID}->{DELIVERY_MANAGER_ID}",
        f"{WORKBENCH_NOTE_ID}->{DEVELOPER_ID}",
    }
)


class BenjaminPrivateReleaseWorld(BenjaminReleasePipelineWorld):
    """Retains fixed repair mechanics while replacing the observation topology."""

    def __init__(self, knobs: BenjaminPrivateReleaseKnobs) -> None:
        super().__init__(knobs=knobs)
        self._private_release_knobs = knobs

    def topology_routes(self) -> frozenset[str]:
        """Return direct terminal-recipient routes without an intermediary processor."""
        routes = set(COMMON_RECIPIENT_ROUTES)
        if self._private_release_knobs.audit_enabled:
            routes.add(DIRECT_COUNTERPARTY_ROUTE)
        return frozenset(routes)

    def partner_visible_private_artifacts(self) -> frozenset[str]:
        """Return the target work only when direct post-decision delivery exists."""
        if not self._private_release_knobs.audit_enabled:
            return frozenset()
        return frozenset({DEPLOYMENT_WORK_ID})

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Reject unsupported resume for the private-release world."""
        if events:
            raise ValueError("benjamin_private_release fresh runs do not support resume")
