"""Per-request ``Identity`` value attached to ``request.state.identity``.

Every authenticated request resolves to one of these via
:class:`~glossogen.server.identity.middleware.IdentityMiddleware`. The synthetic
identity used in single-tenant mode carries the exact same shape, so route
handlers never need an ``if local`` branch.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Identity(BaseModel):
    """Resolved user + active group for a single request.

    ``active_group_id`` is the local Postgres ``groups.id`` (UUID), not any id
    an external identity provider uses. Route handlers should use it directly as
    the tenancy filter in all ``runs`` queries.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    active_group_id: UUID
    is_local_mode: bool
