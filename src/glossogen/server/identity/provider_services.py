"""What the platform offers an identity provider.

:class:`~glossogen.server.identity.identity_provider.IdentityProvider` describes what
a provider gives the platform. This module is the other direction, and it exists
because that direction was previously undeclared: the one call a provider must make
was reachable only by reaching into ``request.app.state``, discoverable only by
reading platform source.

Nothing in this repository calls these. That is the point of them, and it is why
they appear in the vulture whitelist: their callers live in whichever distribution
supplies the provider.

The whole surface a provider needs:

* :func:`approve_parked_consent` to finish a deferred MCP OAuth authorization.
* :func:`frontend_base_url` to build the consent URL it returns from
  ``deferred_consent_url``.
* ``glossogen.db.queries.upsert_group`` to create or rename a group when its
  external organization is created or renamed.
* ``glossogen.db.queries.soft_delete_group_by_external_org_id`` when that
  organization is deleted. It clears the external id and keeps the row, so
  ``runs.group_id`` foreign keys stay valid; deleting the row would orphan runs.

Both query helpers take a connection, which a provider's route handler borrows from
``request.app.state.db_pool``.
"""

import os
from uuid import UUID

from mcp.server.auth.provider import AuthorizeError
from starlette.requests import Request


class ConsentNotApprovable(Exception):
    """The parked consent request cannot be turned into an authorization code.

    Raised when the ``request_id`` names nothing the platform is still holding: a
    consent link that expired, one already used, or one whose OAuth client has since
    gone. All three are the caller's problem to report rather than the server's, so a
    provider's approval endpoint should turn this into a 4xx.

    It exists so a provider never has to catch the MCP library's own error type.
    Making a provider import from ``mcp.server.auth`` to handle an expired link would
    put an internal dependency on the wrong side of the seam.
    """


def frontend_base_url() -> str:
    """Return the frontend's base URL, with no trailing slash.

    Reads ``FRONTEND_URL``, then falls back to the first entry of
    ``ALLOWED_ORIGINS``, then to the local-dev default. A provider building a
    consent URL should use this rather than reading the environment itself, so the
    fallback behaviour stays in one place.
    """
    explicit = os.environ.get("FRONTEND_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    origins_raw = os.environ.get("ALLOWED_ORIGINS", "")
    for candidate in origins_raw.split(","):
        cleaned = candidate.strip()
        if cleaned:
            return cleaned.rstrip("/")
    return "http://localhost:3000"


async def approve_parked_consent(request: Request, request_id: str, group_id: UUID) -> str:
    """Mint the authorization code for a parked MCP consent request.

    Returns the URL the user-agent should be sent to: the OAuth client's
    ``redirect_uri`` with the code and state appended.

    Call this from the approval endpoint the provider contributes, once it has
    verified the caller and settled which group they are authorizing. Choosing that
    group is the provider's decision and the only reason the request was parked.

    Two failures, which a provider should treat differently:

    * :class:`ConsentNotApprovable` when the ``request_id`` names nothing still held,
      meaning the link expired, was already used, or its OAuth client is gone. That is
      the caller's problem; answer 4xx and let them start again.
    * ``RuntimeError`` when MCP is not configured at all, which means
      ``OAUTH_ISSUER_URL`` is unset and no consent request can ever have been parked.
      That is a deployment problem, and a provider contributing this endpoint at all
      implies it should not happen; answer 5xx.
    """
    oauth_provider = getattr(request.app.state, "oauth_provider", None)
    if oauth_provider is None:
        raise RuntimeError(
            "MCP OAuth is not configured (OAUTH_ISSUER_URL is unset), so there is no "
            "parked consent request to approve."
        )
    try:
        redirect_url: str = await oauth_provider.approve_pending_consent(
            request_id=request_id,
            group_id=group_id,
        )
    except AuthorizeError as exc:
        raise ConsentNotApprovable(exc.error_description or exc.error) from exc
    return redirect_url
