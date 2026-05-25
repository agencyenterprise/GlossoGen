"""Networkless Clerk session-token verification.

Wraps ``clerk_backend_api.security.verify_token`` to extract the claims the
identity middleware needs: ``sub`` (Clerk user id), the active org claims
(``org_id`` / ``org_slug``), and the full memberships list if the JWT
template exposes one. ``CLERK_JWT_KEY`` must be set to the PEM public key
from the Clerk dashboard so verification stays networkless.

Multi-org concurrent browsing requires that the user has configured the
Clerk JWT template to include ``{{user.organization_memberships}}`` under
a claim named ``org_memberships``. Without it, only the currently active
org's slug is acceptable.
"""

import logging
from typing import Any, NamedTuple

from clerk_backend_api.security.types import TokenVerificationError, VerifyTokenOptions
from clerk_backend_api.security.verifytoken import verify_token

logger = logging.getLogger(__name__)


class ClerkOrgMembership(NamedTuple):
    """One entry from the user's ``org_memberships`` JWT claim."""

    org_id: str
    org_slug: str


class ClerkSessionClaims(NamedTuple):
    """Subset of Clerk JWT claims the identity middleware consumes."""

    user_id: str
    org_id: str | None
    org_slug: str | None
    org_memberships: tuple[ClerkOrgMembership, ...]


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

    raw_org_id = payload.get("org_id")
    raw_org_slug = payload.get("org_slug")
    org_id = raw_org_id if isinstance(raw_org_id, str) and raw_org_id else None
    org_slug = raw_org_slug if isinstance(raw_org_slug, str) and raw_org_slug else None

    memberships = _parse_memberships(payload.get("org_memberships"))

    return ClerkSessionClaims(
        user_id=user_id,
        org_id=org_id,
        org_slug=org_slug,
        org_memberships=memberships,
    )


def _parse_memberships(raw: Any) -> tuple[ClerkOrgMembership, ...]:
    """Coerce the ``org_memberships`` custom claim into a tuple of typed rows.

    The exact shape depends on the Clerk JWT template the user configures.
    Two common shapes are supported:

    * ``[{"id": "org_x", "slg": "team-a"}, ...]`` — Clerk's
      ``organization_memberships`` shortcode (uses short keys).
    * ``[{"organization_id": "org_x", "organization_slug": "team-a"}, ...]``
      — long-form templates.

    Unknown shapes are silently dropped (the membership check will then 403).
    """
    if not isinstance(raw, list):
        return ()
    parsed: list[ClerkOrgMembership] = []
    for entry in raw:  # type: ignore[reportUnknownVariableType]
        if not isinstance(entry, dict):
            continue
        typed: dict[str, Any] = entry  # type: ignore[reportUnknownVariableType]
        org_id_raw = typed.get("id") or typed.get("organization_id") or typed.get("org_id")
        org_slug_raw = typed.get("slg") or typed.get("organization_slug") or typed.get("org_slug")
        if (
            isinstance(org_id_raw, str)
            and isinstance(org_slug_raw, str)
            and org_id_raw
            and org_slug_raw
        ):
            parsed.append(ClerkOrgMembership(org_id=org_id_raw, org_slug=org_slug_raw))
    return tuple(parsed)
