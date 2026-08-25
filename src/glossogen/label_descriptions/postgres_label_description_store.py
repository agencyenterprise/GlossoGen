"""Label descriptions in Postgres, beside the runs index.

One row per ``(group_id, label)``, and that pair is the primary key: a label has at
most one meaning per group, and recording it again replaces the old one. The upsert is
``ON CONFLICT`` rather than check-then-insert, so two people describing the same label
at once cannot race into an integrity error.
"""

from uuid import UUID

from glossogen.db.pool import DbPool
from glossogen.label_descriptions.label_description_models import LabelDescription
from glossogen.label_descriptions.label_description_store import LabelDescriptionStore


class PostgresLabelDescriptionStore(LabelDescriptionStore):
    """Label descriptions stored in the ``label_descriptions`` table."""

    def __init__(self, pool: DbPool) -> None:
        self._pool = pool

    async def list_descriptions(self, group_id: UUID) -> list[LabelDescription]:
        """Return the group's label descriptions, sorted by label."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT label, description
                    FROM label_descriptions
                    WHERE group_id = %s
                    ORDER BY label ASC
                    """,
                    (group_id,),
                )
                rows = await cur.fetchall()
        return [LabelDescription(label=row[0], description=row[1]) for row in rows]

    async def set_description(self, group_id: UUID, entry: LabelDescription) -> None:
        """Record what a label means, replacing any previous description of it."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO label_descriptions (group_id, label, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (group_id, label)
                    DO UPDATE SET description = EXCLUDED.description
                    """,
                    (group_id, entry.label, entry.description),
                )

    async def delete_description(self, group_id: UUID, label: str) -> bool:
        """Remove a label's description, returning whether one was there to remove."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM label_descriptions WHERE group_id = %s AND label = %s",
                    (group_id, label),
                )
                return cur.rowcount > 0
