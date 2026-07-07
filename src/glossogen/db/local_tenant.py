"""Canonical identifiers for the synthetic single-tenant ``local`` group.

Both the FastAPI identity middleware and the CLI subprocess need to agree on
these strings. Keeping them in the tenancy-layer (``glossogen.db``) module —
which the CLI already depends on — avoids the CLI reaching into
``glossogen.server`` just to read a constant.
"""

from uuid import UUID

LOCAL_USER_ID = "local-user"
LOCAL_GROUP_SLUG = "local"
LOCAL_GROUP_NAME = "Local"

# Fixed, deterministic UUID for the synthetic ``local`` group. In no-database
# local mode there is no ``groups`` table to allocate one, so the identity
# middleware stamps this constant as the active group id on every request.
LOCAL_GROUP_ID = UUID("10ca110c-a100-4000-8000-000000000001")
