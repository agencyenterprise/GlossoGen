"""Canonical identifiers for the synthetic single-tenant ``local`` group.

Both the FastAPI identity middleware and the CLI subprocess need to agree on
these strings. Keeping them in the tenancy-layer (``schmidt.db``) module —
which the CLI already depends on — avoids the CLI reaching into
``schmidt.server`` just to read a constant.
"""

LOCAL_USER_ID = "local-user"
LOCAL_GROUP_SLUG = "local"
LOCAL_GROUP_NAME = "Local"
