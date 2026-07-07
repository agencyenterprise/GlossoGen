"""Idempotent bootstrap for the synthetic ``local`` group + ``local-user``.

Runs once during FastAPI lifespan startup. The resulting group UUID is cached
on ``app.state.local_group_id`` so the identity middleware can hand it back as
the active group in local mode without re-querying.
"""

import logging
from uuid import UUID

from glossogen.db.local_tenant import LOCAL_GROUP_NAME, LOCAL_GROUP_SLUG, LOCAL_USER_ID
from glossogen.db.pool import DbPool
from glossogen.db.queries import set_last_active_group, upsert_group

logger = logging.getLogger(__name__)


async def ensure_local_group(pool: DbPool) -> UUID:
    """Upsert the synthetic ``local`` group and seed its last-active row.

    Returns the group's UUID so the identity middleware can stamp it onto every
    request in local mode. Safe to call repeatedly: both operations are upserts.
    """
    async with pool.connection() as conn:
        group = await upsert_group(
            conn=conn,
            clerk_org_id=None,
            slug=LOCAL_GROUP_SLUG,
            name=LOCAL_GROUP_NAME,
        )
        await set_last_active_group(
            conn=conn,
            user_id=LOCAL_USER_ID,
            group_id=group.id,
        )
    logger.info("Local group ready: id=%s slug=%s", group.id, group.slug)
    return group.id
