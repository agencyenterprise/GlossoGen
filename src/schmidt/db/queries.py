"""Typed query helpers over the ``groups``, ``runs``, and ``user_last_active_group`` tables.

Every helper takes a ``psycopg.AsyncConnection`` and returns a Pydantic model
(or list of models). Raw SQL is written inline as parameterized statements;
SQLAlchemy is intentionally not used.
"""

from datetime import datetime
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import TupleRow

from schmidt.db.rows import GroupRow, RunRow, UserLastActiveGroupRow

_GROUP_COLUMNS = "id, clerk_org_id, slug, name, created_at"
_RUN_COLUMNS = (
    "id, group_id, scenario, run_dir_name, status, created_at, "
    "created_by_user_id, source_run_scenario, source_run_dir_name"
)


async def get_group_by_slug(
    conn: AsyncConnection[TupleRow],
    slug: str,
) -> GroupRow | None:
    """Look up a group by its URL slug; returns ``None`` if not found."""
    async with conn.cursor() as cur:
        await cur.execute(
            f"SELECT {_GROUP_COLUMNS} FROM groups WHERE slug = %s",
            (slug,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return _group_row_from_tuple(row)


async def get_group_by_id(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
) -> GroupRow | None:
    """Look up a group by its UUID primary key; returns ``None`` if not found."""
    async with conn.cursor() as cur:
        await cur.execute(
            f"SELECT {_GROUP_COLUMNS} FROM groups WHERE id = %s",
            (group_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return _group_row_from_tuple(row)


async def get_group_by_clerk_org_id(
    conn: AsyncConnection[TupleRow],
    clerk_org_id: str,
) -> GroupRow | None:
    """Look up a group by its Clerk org id; returns ``None`` if not found."""
    async with conn.cursor() as cur:
        await cur.execute(
            f"SELECT {_GROUP_COLUMNS} FROM groups WHERE clerk_org_id = %s",
            (clerk_org_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return _group_row_from_tuple(row)


async def upsert_group(
    conn: AsyncConnection[TupleRow],
    clerk_org_id: str | None,
    slug: str,
    name: str,
) -> GroupRow:
    """Insert or update a group by ``(clerk_org_id)`` when set, else by ``(slug)``.

    Used both for the synthetic ``local`` group bootstrap (clerk_org_id is NULL)
    and for the Clerk webhook ``organization.created`` / ``organization.updated``
    handlers.
    """
    async with conn.cursor() as cur:
        if clerk_org_id is None:
            await cur.execute(
                f"""
                INSERT INTO groups (clerk_org_id, slug, name)
                VALUES (NULL, %s, %s)
                ON CONFLICT (slug) DO UPDATE
                  SET name = EXCLUDED.name
                RETURNING {_GROUP_COLUMNS}
                """,
                (slug, name),
            )
        else:
            await cur.execute(
                f"""
                INSERT INTO groups (clerk_org_id, slug, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (clerk_org_id) DO UPDATE
                  SET slug = EXCLUDED.slug,
                      name = EXCLUDED.name
                RETURNING {_GROUP_COLUMNS}
                """,
                (clerk_org_id, slug, name),
            )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError(f"upsert_group returned no row for slug={slug!r}")
    return _group_row_from_tuple(row)


async def soft_delete_group_by_clerk_org_id(
    conn: AsyncConnection[TupleRow],
    clerk_org_id: str,
) -> None:
    """Mark a Clerk org as deleted by clearing its ``clerk_org_id``.

    The local group row is preserved so existing ``runs.group_id`` foreign keys
    stay valid. Future webhooks for a re-created org will insert a fresh row.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE groups SET clerk_org_id = NULL WHERE clerk_org_id = %s",
            (clerk_org_id,),
        )


async def get_run(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
    scenario: str,
    run_dir_name: str,
) -> RunRow | None:
    """Look up a run within a group; returns ``None`` if not found or not in group."""
    async with conn.cursor() as cur:
        await cur.execute(
            f"""
            SELECT {_RUN_COLUMNS} FROM runs
            WHERE group_id = %s AND scenario = %s AND run_dir_name = %s
            """,
            (group_id, scenario, run_dir_name),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return _run_row_from_tuple(row)


async def list_runs_for_group(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
    scenario: str | None,
    limit: int,
    offset: int,
) -> list[RunRow]:
    """Return runs owned by ``group_id``, newest first, optionally filtered by scenario."""
    async with conn.cursor() as cur:
        if scenario is None:
            await cur.execute(
                f"""
                SELECT {_RUN_COLUMNS} FROM runs
                WHERE group_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (group_id, limit, offset),
            )
        else:
            await cur.execute(
                f"""
                SELECT {_RUN_COLUMNS} FROM runs
                WHERE group_id = %s AND scenario = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (group_id, scenario, limit, offset),
            )
        rows = await cur.fetchall()
    return [_run_row_from_tuple(row) for row in rows]


async def insert_run(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
    scenario: str,
    run_dir_name: str,
    status: str,
    created_at: datetime,
    created_by_user_id: str | None,
    source_run_scenario: str | None,
    source_run_dir_name: str | None,
) -> RunRow:
    """Insert a new run row; conflicts on ``(scenario, run_dir_name)`` are an error."""
    async with conn.cursor() as cur:
        await cur.execute(
            f"""
            INSERT INTO runs (
                group_id, scenario, run_dir_name, status, created_at,
                created_by_user_id, source_run_scenario, source_run_dir_name
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_RUN_COLUMNS}
            """,
            (
                group_id,
                scenario,
                run_dir_name,
                status,
                created_at,
                created_by_user_id,
                source_run_scenario,
                source_run_dir_name,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError(
            f"insert_run returned no row for scenario={scenario!r} run_dir_name={run_dir_name!r}"
        )
    return _run_row_from_tuple(row)


async def insert_run_if_absent(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
    scenario: str,
    run_dir_name: str,
    status: str,
    created_at: datetime,
    created_by_user_id: str | None,
    source_run_scenario: str | None,
    source_run_dir_name: str | None,
) -> bool:
    """Insert a run row only if ``(scenario, run_dir_name)`` is not already taken.

    Returns ``True`` when a row was inserted, ``False`` when one already existed.
    Used by ``scripts/backfill_runs_index.py``.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO runs (
                group_id, scenario, run_dir_name, status, created_at,
                created_by_user_id, source_run_scenario, source_run_dir_name
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (scenario, run_dir_name) DO NOTHING
            """,
            (
                group_id,
                scenario,
                run_dir_name,
                status,
                created_at,
                created_by_user_id,
                source_run_scenario,
                source_run_dir_name,
            ),
        )
        return cur.rowcount == 1


async def update_run_status(
    conn: AsyncConnection[TupleRow],
    scenario: str,
    run_dir_name: str,
    status: str,
) -> None:
    """Update the cached status column for a run."""
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE runs SET status = %s WHERE scenario = %s AND run_dir_name = %s",
            (status, scenario, run_dir_name),
        )


async def get_last_active_group(
    conn: AsyncConnection[TupleRow],
    user_id: str,
) -> UserLastActiveGroupRow | None:
    """Return the last-active group entry for a user, or ``None`` if unrecorded."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT user_id, group_id, updated_at FROM user_last_active_group WHERE user_id = %s",
            (user_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return UserLastActiveGroupRow(user_id=row[0], group_id=row[1], updated_at=row[2])


async def set_last_active_group(
    conn: AsyncConnection[TupleRow],
    user_id: str,
    group_id: UUID,
) -> None:
    """Upsert the last-active group for a user (used by the frontend on org switch)."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO user_last_active_group (user_id, group_id, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
              SET group_id = EXCLUDED.group_id,
                  updated_at = EXCLUDED.updated_at
            """,
            (user_id, group_id),
        )


def _group_row_from_tuple(row: TupleRow) -> GroupRow:
    return GroupRow(
        id=row[0],
        clerk_org_id=row[1],
        slug=row[2],
        name=row[3],
        created_at=row[4],
    )


def _run_row_from_tuple(row: TupleRow) -> RunRow:
    return RunRow(
        id=row[0],
        group_id=row[1],
        scenario=row[2],
        run_dir_name=row[3],
        status=row[4],
        created_at=row[5],
        created_by_user_id=row[6],
        source_run_scenario=row[7],
        source_run_dir_name=row[8],
    )
