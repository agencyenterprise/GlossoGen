"""Dashboards as JSON files under the runs directory.

This is what a checkout with no ``DATABASE_URL`` uses. Dashboards sit beside the runs
they describe, which means a runs directory copied to another machine carries its
analyses with it.

Files are written to a temporary name and renamed into place, so a reader never sees a
half-written dashboard and a crashed write leaves the previous version intact.

The group directory is part of the path rather than a field inside the file. A read
therefore cannot return another group's dashboard even if a file were mislabelled.
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
import orjson
from pydantic import ValidationError

from glossogen.dashboards.dashboard_models import (
    Dashboard,
    DashboardContent,
    DashboardSummary,
    summarize,
)
from glossogen.dashboards.dashboard_store import DashboardNameTaken, DashboardStore
from glossogen.dashboards.legacy_lineage_translation import translate_legacy_lineage_terms

logger = logging.getLogger(__name__)

DASHBOARD_DIR_NAME = "_dashboards"


class FilesystemDashboardStore(DashboardStore):
    """Dashboards stored as one JSON file per dashboard, under the runs directory."""

    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir

    def _group_dir(self, group_id: UUID) -> Path:
        """Return where one group's dashboards live."""
        return self._runs_dir / DASHBOARD_DIR_NAME / str(group_id)

    def _path_of(self, group_id: UUID, dashboard_id: UUID) -> Path:
        """Return where one dashboard lives."""
        return self._group_dir(group_id=group_id) / f"{dashboard_id}.json"

    async def _read_all(self, group_id: UUID) -> list[Dashboard]:
        """Read every dashboard a group has, skipping any file that no longer parses."""
        group_dir = self._group_dir(group_id=group_id)
        if not group_dir.is_dir():
            return []
        dashboards: list[Dashboard] = []
        for path in sorted(group_dir.glob("*.json")):
            try:
                dashboards.append(await self._read_one(path=path))
            except (OSError, orjson.JSONDecodeError, ValidationError):
                logger.exception("Skipping unreadable dashboard file %s in the listing", path)
        return dashboards

    async def _read_one(self, path: Path) -> Dashboard:
        """Read one dashboard file.

        A file that no longer parses raises. Returning ``None`` would be
        indistinguishable from "this group has no such dashboard", which is a 404, and
        a dashboard that exists but cannot be read is not missing: it is broken, and
        saying so is the only way anyone finds out. The listing tolerates it
        separately, because one broken dashboard must not hide the rest.

        A dashboard stored in the pre-rename lineage vocabulary is written back
        translated, so the translation runs once per file rather than on every read.
        """
        async with aiofiles.open(path, mode="rb") as handle:
            raw = await handle.read()
        stored = Dashboard.model_validate(orjson.loads(raw))
        translated = translate_legacy_lineage_terms(dashboard=stored)
        if translated is not stored:
            await self._write_to_path(path=path, dashboard=translated)
        return translated

    async def _write_to_path(self, path: Path, dashboard: Dashboard) -> None:
        """Write one dashboard to its file, replacing any previous version atomically."""
        pending = path.with_suffix(".json.pending")
        async with aiofiles.open(pending, mode="wb") as handle:
            await handle.write(dashboard.model_dump_json(indent=2).encode("utf-8"))
        await asyncio.to_thread(pending.replace, path)

    async def _write(self, group_id: UUID, dashboard: Dashboard) -> None:
        """Write one dashboard, replacing any previous version atomically."""
        group_dir = self._group_dir(group_id=group_id)
        await asyncio.to_thread(group_dir.mkdir, parents=True, exist_ok=True)
        final = self._path_of(group_id=group_id, dashboard_id=dashboard.dashboard_id)
        await self._write_to_path(path=final, dashboard=dashboard)

    async def _refuse_duplicate_name(
        self,
        group_id: UUID,
        name: str,
        dashboard_id: UUID | None,
    ) -> None:
        """Raise when another dashboard in the group already carries this name."""
        for existing in await self._read_all(group_id=group_id):
            if existing.name != name:
                continue
            if dashboard_id is not None and existing.dashboard_id == dashboard_id:
                continue
            raise DashboardNameTaken(name)

    async def list_dashboards(self, group_id: UUID) -> list[DashboardSummary]:
        """Return the group's dashboards, most recently updated first."""
        dashboards = await self._read_all(group_id=group_id)
        # Newest first, ties broken by name ascending, matching the Postgres store's
        # ORDER BY. A shared dashboard list that reorders when a deployment gains a
        # database is a difference nobody can explain.
        dashboards.sort(key=lambda dashboard: dashboard.name)
        dashboards.sort(key=lambda dashboard: dashboard.updated_at, reverse=True)
        return [summarize(dashboard=dashboard) for dashboard in dashboards]

    async def get_dashboard(self, group_id: UUID, dashboard_id: UUID) -> Dashboard | None:
        """Return one dashboard, or ``None`` when the group has no such dashboard."""
        path = self._path_of(group_id=group_id, dashboard_id=dashboard_id)
        if not path.is_file():
            return None
        return await self._read_one(path=path)

    async def create_dashboard(
        self,
        group_id: UUID,
        content: DashboardContent,
        created_by: str,
    ) -> Dashboard:
        """Store a new dashboard and return it as stored."""
        await self._refuse_duplicate_name(group_id=group_id, name=content.name, dashboard_id=None)
        now = datetime.now(tz=UTC)
        dashboard = Dashboard(
            dashboard_id=uuid4(),
            name=content.name,
            description=content.description,
            selection=content.selection,
            filters=content.filters,
            charts=content.charts,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        await self._write(group_id=group_id, dashboard=dashboard)
        return dashboard

    async def update_dashboard(
        self,
        group_id: UUID,
        dashboard_id: UUID,
        content: DashboardContent,
    ) -> Dashboard | None:
        """Replace a dashboard's content, or return ``None`` when it is not there."""
        existing = await self.get_dashboard(group_id=group_id, dashboard_id=dashboard_id)
        if existing is None:
            return None
        await self._refuse_duplicate_name(
            group_id=group_id, name=content.name, dashboard_id=dashboard_id
        )
        updated = Dashboard(
            dashboard_id=existing.dashboard_id,
            name=content.name,
            description=content.description,
            selection=content.selection,
            filters=content.filters,
            charts=content.charts,
            created_by=existing.created_by,
            created_at=existing.created_at,
            updated_at=datetime.now(tz=UTC),
        )
        await self._write(group_id=group_id, dashboard=updated)
        return updated

    async def delete_dashboard(self, group_id: UUID, dashboard_id: UUID) -> bool:
        """Remove a dashboard, returning whether one was there to remove."""
        path = self._path_of(group_id=group_id, dashboard_id=dashboard_id)
        if not path.is_file():
            return False
        await asyncio.to_thread(path.unlink)
        return True
