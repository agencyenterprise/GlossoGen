"""Networkless Clerk session-token verification.

Wraps ``clerk_backend_api.security.verify_token`` to extract the claims the
identity middleware needs: ``sub`` (Clerk user id) and the active org's
``id`` + ``slug``. ``CLERK_JWT_KEY`` must be set to the PEM public key from
the Clerk dashboard so verification stays networkless.

Clerk session tokens come in two shapes:

* **v2** (current default for new apps): org claims live under the nested
  ``o`` object — ``o.id`` (org id), ``o.slg`` (org slug), ``o.rol``, etc.
* **v1** (legacy): flat ``org_id`` / ``org_slug`` claims at the top level.

This verifier reads both shapes so it works regardless of which token
version the Clerk instance is configured to mint.

The active org is the only source of truth for membership. Multi-org
users are handled by Clerk's ``organizationSyncOptions`` on the frontend
middleware, which activates the URL's org for the current request before
the token is minted — see ``frontend/src/proxy.ts``.
"""

import logging
from typing import Any, NamedTuple, cast

from clerk_backend_api.security.types import TokenVerificationError, VerifyTokenOptions
from clerk_backend_api.security.verifytoken import verify_token

logger = logging.getLogger(__name__)


class ClerkSessionClaims(NamedTuple):
    """Subset of Clerk JWT claims the identity middleware consumes."""

    user_id: str
    org_id: str | None
    org_slug: str | None


class InvalidClerkToken(Exception):
    """Raised when a presented bearer token fails Clerk JWT verification."""


def verify_clerk_session_token(
    token: str,
    clerk_jwt_key: str,
    authorized_parties: tuple[str, ...],
) -> ClerkSessionClaims:
    """Verify a Clerk session token offline and return the relevant claims.

    Raises ``InvalidClerkToken`` for any signature, expiration, or
    authorized-party failure. The middleware turns that into 401.
    """
    options = VerifyTokenOptions(
        jwt_key=clerk_jwt_key,
        authorized_parties=list(authorized_parties) if authorized_parties else None,
    )
    try:
        payload = verify_token(token, options)
    except TokenVerificationError as exc:
        logger.warning("Clerk token verification failed: %s", exc)
        raise InvalidClerkToken(str(exc)) from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise InvalidClerkToken("Clerk token has no `sub` claim")

    org_id, org_slug = _extract_active_org(payload=payload)
    return ClerkSessionClaims(user_id=user_id, org_id=org_id, org_slug=org_slug)


def _extract_active_org(payload: dict[str, object]) -> tuple[str | None, str | None]:
    """Read the active org ``(id, slug)`` from either v2 or v1 token shape.

    v2 tokens nest the active org under ``o = {id, slg, rol, ...}``; v1
    tokens carry flat top-level ``org_id`` / ``org_slug`` claims. Returns
    ``(None, None)`` when neither shape carries a non-empty org.
    """
    nested_raw = payload.get("o")
    if isinstance(nested_raw, dict):
        nested = cast(dict[str, Any], nested_raw)
        return (
            _string_claim(nested.get("id")),
            _string_claim(nested.get("slg")),
        )
    return (
        _string_claim(payload.get("org_id")),
        _string_claim(payload.get("org_slug")),
    )


def _string_claim(value: object) -> str | None:
    """Return ``value`` if it is a non-empty string, otherwise ``None``."""
    if isinstance(value, str) and value:
        return value
    return None
