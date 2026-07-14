"""Typed query helpers over the ``groups``, ``runs``, and ``user_last_active_group`` tables.

Every helper takes a ``psycopg.AsyncConnection`` and returns a Pydantic model
(or list of models). Raw SQL is written inline as parameterized statements;
SQLAlchemy is intentionally not used.
"""

from datetime import datetime
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import TupleRow

from glossogen.db.rows import DerivedSourceCountRow, GroupRow, RunRow, UserLastActiveGroupRow

_GROUP_COLUMNS = "id, clerk_org_id, slug, name, created_at"
_RUN_COLUMNS = (
    "id, group_id, scenario, run_dir_name, status, created_at, "
    "created_by_user_id, source_run_scenario, source_run_dir_name, "
    "evaluation_content_hash"
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
    """Return runs owned by ``group_id``, newest first, optionally filtered by scenario.

    Ordering is by the unix-epoch prefix of ``run_dir_name`` (= when the
    simulation originally ran), descending. This matches what the UI displays
    as the run date, so an old run re-imported today does not jump above
    sims actually launched today.
    """
    async with conn.cursor() as cur:
        if scenario is None:
            await cur.execute(
                f"""
                SELECT {_RUN_COLUMNS} FROM runs
                WHERE group_id = %s
                ORDER BY split_part(run_dir_name, '_', 1)::bigint DESC, run_dir_name DESC
                LIMIT %s OFFSET %s
                """,
                (group_id, limit, offset),
            )
        else:
            await cur.execute(
                f"""
                SELECT {_RUN_COLUMNS} FROM runs
                WHERE group_id = %s AND scenario = %s
                ORDER BY split_part(run_dir_name, '_', 1)::bigint DESC, run_dir_name DESC
                LIMIT %s OFFSET %s
                """,
                (group_id, scenario, limit, offset),
            )
        rows = await cur.fetchall()
    return [_run_row_from_tuple(row) for row in rows]


async def list_children_of_run(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
    parent_scenario: str,
    parent_run_dir_name: str,
) -> list[RunRow]:
    """Return runs derived from ``(parent_scenario, parent_run_dir_name)``.

    A run is a child if its ``source_run_scenario`` / ``source_run_dir_name``
    columns match the parent. Covers ``replace-agent``, ``resume-at-round``,
    and ``cross-run-replace-agent`` (source A) derivations — all three
    register through ``_register_derived_run`` with the timeline parent.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            f"""
            SELECT {_RUN_COLUMNS} FROM runs
            WHERE group_id = %s
              AND source_run_scenario = %s
              AND source_run_dir_name = %s
            ORDER BY split_part(run_dir_name, '_', 1)::bigint DESC, run_dir_name DESC
            """,
            (group_id, parent_scenario, parent_run_dir_name),
        )
        rows = await cur.fetchall()
    return [_run_row_from_tuple(row) for row in rows]


async def list_derived_source_counts(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
) -> list[DerivedSourceCountRow]:
    """Return every run that is the timeline parent of ≥1 derived run, with its child count.

    Aggregates the ``runs`` table by ``(source_run_scenario,
    source_run_dir_name)``; a row is emitted only for parents that have at
    least one derivation (replace-agent, resume-at-round, or
    cross-run-replace-agent source A). Newest parent first.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT source_run_scenario, source_run_dir_name, count(*)
            FROM runs
            WHERE group_id = %s
              AND source_run_scenario IS NOT NULL
              AND source_run_dir_name IS NOT NULL
            GROUP BY source_run_scenario, source_run_dir_name
            ORDER BY split_part(source_run_dir_name, '_', 1)::bigint DESC, source_run_dir_name DESC
            """,
            (group_id,),
        )
        rows = await cur.fetchall()
    return [
        DerivedSourceCountRow(
            scenario=row[0],
            run_dir_name=row[1],
            derived_count=row[2],
        )
        for row in rows
    ]


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


async def delete_run(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
    scenario: str,
    run_dir_name: str,
) -> None:
    """Delete a run's index row, scoped to its owning group."""
    async with conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM runs WHERE group_id = %s AND scenario = %s AND run_dir_name = %s",
            (group_id, scenario, run_dir_name),
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
        evaluation_content_hash=row[9],
    )


async def update_run_evaluation_content_hash(
    conn: AsyncConnection[TupleRow],
    group_id: UUID,
    scenario: str,
    run_dir_name: str,
    content_hash: str,
) -> None:
    """Persist the digest of the last ``PUT /evaluation`` for a run.

    Called by the eval PUT handler immediately after ``write_report``. The
    ``group_id`` scope is defensive — the row's identity is already
    ``(scenario, run_dir_name)`` unique — so an UPDATE against a row
    belonging to another group is a no-op instead of a cross-tenant leak.
    An UPDATE that matches zero rows (e.g. a run only present on the
    filesystem, missed by the runs index) is not an error; the sync tool
    will detect the mismatch on the next pass and re-PUT.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE runs SET evaluation_content_hash = %s
             WHERE group_id = %s AND scenario = %s AND run_dir_name = %s
            """,
            (content_hash, group_id, scenario, run_dir_name),
        )


async def list_runs_missing_evaluation_content_hash(
    conn: AsyncConnection[TupleRow],
) -> list[RunRow]:
    """Return every run row whose ``evaluation_content_hash`` is NULL.

    Used by ``scripts/backfill_evaluation_content_hash.py`` to seed the
    column for pre-existing rows written before migration 0004 landed.
    Not group-scoped: the backfill script walks every group's runs.
    """
    async with conn.cursor() as cur:
        await cur.execute(f"""
            SELECT {_RUN_COLUMNS} FROM runs
             WHERE evaluation_content_hash IS NULL
             ORDER BY scenario, run_dir_name
            """)
        rows = await cur.fetchall()
    return [_run_row_from_tuple(row) for row in rows]
