"""Dashboards in Postgres, beside the runs index.

The content that varies (the selection, the filters, the charts) is one JSONB column;
what a listing needs (name, owner, timestamps) is columns of its own, so listing a
group's dashboards never parses a chart spec.

The unique index on ``(group_id, name)`` is what enforces one name per group. Catching
the integrity error rather than checking first is deliberate: a check-then-insert
races two people saving the same name at once, and the index does not.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import orjson
from psycopg import AsyncConnection, errors
from psycopg.rows import TupleRow
from psycopg.types.json import Jsonb

from glossogen.dashboards.dashboard_models import (
    Dashboard,
    DashboardContent,
    DashboardSummary,
)
from glossogen.dashboards.dashboard_store import DashboardNameTaken, DashboardStore
from glossogen.dashboards.legacy_lineage_translation import translate_legacy_lineage_terms
from glossogen.db.pool import DbPool

logger = logging.getLogger(__name__)

_LIST_COLUMNS = "id, name, description, created_by, created_at, updated_at"


def _spec_of(content: DashboardContent) -> Jsonb:
    """Render the parts of a dashboard that live in the JSON column."""
    return Jsonb(
        orjson.loads(
            content.model_dump_json(include={"selection", "filters", "charts"}).encode("utf-8")
        )
    )


def _stored_dashboard_from_row(row: TupleRow) -> Dashboard:
    """Rebuild a dashboard from its row exactly as stored, validating the spec."""
    dashboard_id, name, description, created_by, created_at, updated_at, spec = row
    return Dashboard.model_validate(
        {
            "dashboard_id": dashboard_id,
            "name": name,
            "description": description,
            "created_by": created_by,
            "created_at": created_at,
            "updated_at": updated_at,
            **spec,
        }
    )


def _spec_of_dashboard(dashboard: Dashboard) -> Jsonb:
    """Render a stored dashboard's JSON-column parts."""
    return Jsonb(
        orjson.loads(
            dashboard.model_dump_json(include={"selection", "filters", "charts"}).encode("utf-8")
        )
    )


class PostgresDashboardStore(DashboardStore):
    """Dashboards stored in the ``dashboards`` table."""

    def __init__(self, pool: DbPool) -> None:
        self._pool = pool

    async def list_dashboards(self, group_id: UUID) -> list[DashboardSummary]:
        """Return the group's dashboards, most recently updated first."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    SELECT {_LIST_COLUMNS},
                           jsonb_array_length(spec -> 'charts') AS chart_count
                    FROM dashboards
                    WHERE group_id = %s
                    ORDER BY updated_at DESC, name ASC
                    """,
                    (group_id,),
                )
                rows = await cur.fetchall()
        return [
            DashboardSummary(
                dashboard_id=row[0],
                name=row[1],
                description=row[2],
                chart_count=row[6],
                created_by=row[3],
                created_at=row[4],
                updated_at=row[5],
            )
            for row in rows
        ]

    async def get_dashboard(self, group_id: UUID, dashboard_id: UUID) -> Dashboard | None:
        """Return one dashboard, or ``None`` when the group has no such dashboard.

        A dashboard stored in the pre-rename lineage vocabulary is written back
        translated, so the translation runs once per row rather than on every read.
        """
        async with self._pool.connection() as conn:
            row = await self._fetch(conn=conn, group_id=group_id, dashboard_id=dashboard_id)
            if row is None:
                return None
            stored = _stored_dashboard_from_row(row=row)
            translated = translate_legacy_lineage_terms(dashboard=stored)
            if translated is not stored:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE dashboards SET spec = %s WHERE group_id = %s AND id = %s",
                        (_spec_of_dashboard(dashboard=translated), group_id, dashboard_id),
                    )
        return translated

    async def _fetch(
        self,
        conn: AsyncConnection[TupleRow],
        group_id: UUID,
        dashboard_id: UUID,
    ) -> TupleRow | None:
        """Read one dashboard row within an open connection."""
        async with conn.cursor() as cur:
            await cur.execute(
                f"SELECT {_LIST_COLUMNS}, spec FROM dashboards WHERE group_id = %s AND id = %s",
                (group_id, dashboard_id),
            )
            return await cur.fetchone()

    async def create_dashboard(
        self,
        group_id: UUID,
        content: DashboardContent,
        created_by: str,
    ) -> Dashboard:
        """Store a new dashboard and return it as stored."""
        now = datetime.now(tz=UTC)
        dashboard_id = uuid4()
        try:
            async with self._pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO dashboards (
                            id, group_id, name, description, spec,
                            created_by, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            dashboard_id,
                            group_id,
                            content.name,
                            content.description,
                            _spec_of(content=content),
                            created_by,
                            now,
                            now,
                        ),
                    )
        except errors.UniqueViolation as exc:
            raise DashboardNameTaken(content.name) from exc

        return Dashboard(
            dashboard_id=dashboard_id,
            name=content.name,
            description=content.description,
            selection=content.selection,
            filters=content.filters,
            charts=content.charts,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    async def update_dashboard(
        self,
        group_id: UUID,
        dashboard_id: UUID,
        content: DashboardContent,
    ) -> Dashboard | None:
        """Replace a dashboard's content, or return ``None`` when it is not there."""
        try:
            async with self._pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"""
                        UPDATE dashboards
                        SET name = %s, description = %s, spec = %s, updated_at = %s
                        WHERE group_id = %s AND id = %s
                        RETURNING {_LIST_COLUMNS}, spec
                        """,
                        (
                            content.name,
                            content.description,
                            _spec_of(content=content),
                            datetime.now(tz=UTC),
                            group_id,
                            dashboard_id,
                        ),
                    )
                    row = await cur.fetchone()
        except errors.UniqueViolation as exc:
            raise DashboardNameTaken(content.name) from exc

        if row is None:
            return None
        return _stored_dashboard_from_row(row=row)

    async def delete_dashboard(self, group_id: UUID, dashboard_id: UUID) -> bool:
        """Remove a dashboard, returning whether one was there to remove."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM dashboards WHERE group_id = %s AND id = %s",
                    (group_id, dashboard_id),
                )
                return cur.rowcount > 0
