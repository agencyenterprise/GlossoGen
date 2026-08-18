"""Resolution of the frontend's base URL.

The OAuth consent flow redirects a user-agent to a page the frontend serves, so
the backend needs to know where the frontend lives. Kept in its own module
because both the app factory and the consent redirect read it.
"""

import os


def resolve_frontend_url() -> str:
    """Pick the frontend base URL used for OAuth consent redirects.

    Reads ``FRONTEND_URL`` directly, then falls back to the first entry of
    ``ALLOWED_ORIGINS``, then to the local-dev default ``http://localhost:3000``.
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
