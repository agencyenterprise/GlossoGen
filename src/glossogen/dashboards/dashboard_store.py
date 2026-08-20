"""What a dashboard store has to do, whichever thing is storing them.

Two implementations exist because the platform runs two ways. With a database the
dashboards live beside the runs index, which is what makes them visible to everyone
in a group. Without one, a single-tenant checkout keeps them in the runs directory,
so the feature is not something only a deployment has.

Every method is scoped by ``group_id``. A store never sees a request, so there is no
path by which one group's dashboard could be handed to another.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from glossogen.dashboards.dashboard_models import Dashboard, DashboardContent, DashboardSummary


class DashboardNameTaken(Exception):
    """A group already has a dashboard by that name."""


class DashboardStore(ABC):
    """Storage for one group's dashboards."""

    @abstractmethod
    async def list_dashboards(self, group_id: UUID) -> list[DashboardSummary]:
        """Return the group's dashboards, most recently updated first."""

    @abstractmethod
    async def get_dashboard(self, group_id: UUID, dashboard_id: UUID) -> Dashboard | None:
        """Return one dashboard, or ``None`` when the group has no such dashboard."""

    @abstractmethod
    async def create_dashboard(
        self,
        group_id: UUID,
        content: DashboardContent,
        created_by: str,
    ) -> Dashboard:
        """Store a new dashboard and return it as stored."""

    @abstractmethod
    async def update_dashboard(
        self,
        group_id: UUID,
        dashboard_id: UUID,
        content: DashboardContent,
    ) -> Dashboard | None:
        """Replace a dashboard's content, or return ``None`` when it is not there."""

    @abstractmethod
    async def delete_dashboard(self, group_id: UUID, dashboard_id: UUID) -> bool:
        """Remove a dashboard, returning whether one was there to remove."""
