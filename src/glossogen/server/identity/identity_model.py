"""Per-request ``Identity`` value attached to ``request.state.identity``.

Every authenticated request resolves to one of these via
``ClerkIdentityMiddleware``. The local synthetic identity (used when
``CLERK_SECRET_KEY`` is unset) carries the exact same shape, so route handlers
never need an ``if local`` branch.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Identity(BaseModel):
    """Resolved user + active group for a single request.

    ``active_group_id`` is the local Postgres ``groups.id`` (UUID), not the
    Clerk org id. Route handlers should use it directly as the tenancy filter
    in all ``runs`` queries.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    active_group_id: UUID
    active_group_slug: str
    available_group_ids: frozenset[UUID]
    is_local_mode: bool
