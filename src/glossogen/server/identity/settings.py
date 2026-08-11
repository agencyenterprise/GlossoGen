"""Identity-layer environment configuration.

Reads the Clerk env vars the middleware needs once at process start. The
presence (or absence) of ``CLERK_SECRET_KEY`` is what switches the server
between Clerk-auth mode and single-tenant local mode.

``CLERK_WEBHOOK_SECRET`` is deliberately not read here. The webhook router
reads it per request and answers 503 when it is missing, so the server can
boot in local mode without it, because a startup read would make an optional
secret mandatory.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IdentitySettings:
    """Resolved Clerk env config; ``clerk_secret_key`` absent => local mode."""

    clerk_secret_key: str | None
    clerk_jwt_key: str | None
    clerk_authorized_parties: tuple[str, ...]

    @property
    def is_local_mode(self) -> bool:
        """Return True when no Clerk secret is configured (single-tenant local mode)."""
        return self.clerk_secret_key is None


def load_identity_settings() -> IdentitySettings:
    """Read identity-related env vars into an ``IdentitySettings`` instance."""
    authorized_parties_raw = os.environ.get("CLERK_AUTHORIZED_PARTIES", "")
    authorized_parties = tuple(
        part.strip() for part in authorized_parties_raw.split(",") if part.strip()
    )
    return IdentitySettings(
        clerk_secret_key=os.environ.get("CLERK_SECRET_KEY"),
        clerk_jwt_key=os.environ.get("CLERK_JWT_KEY"),
        clerk_authorized_parties=authorized_parties,
    )
