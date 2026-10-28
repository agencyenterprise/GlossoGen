"""Environment-derived server configuration, read once per process.

Groups the values :func:`glossogen.server.app_factory.create_app` needs into one
value that is passed explicitly, so the application's lifespan reads its
configuration from an argument rather than from module globals.
"""

import os
from pathlib import Path
from typing import NamedTuple

from glossogen.server.feature_flags import FeatureFlags, load_feature_flags


class ServerRuntimeConfig(NamedTuple):
    """Resolved environment configuration for one server process."""

    runs_dir: Path
    oauth_issuer_url: str | None
    allowed_origins: tuple[str, ...]
    feature_flags: FeatureFlags


def _parse_allowed_origins() -> tuple[str, ...]:
    """Read CORS origins from ``ALLOWED_ORIGINS`` (comma-separated)."""
    origins_raw = os.environ.get("ALLOWED_ORIGINS", "")
    if origins_raw:
        return tuple(origin.strip() for origin in origins_raw.split(","))
    return ("http://localhost:3000",)


def _read_oauth_issuer_url() -> str | None:
    """Read ``OAUTH_ISSUER_URL``, or ``None`` when it is unset or blank.

    Blank counts as unset because ``docker-compose.yml`` passes the variable
    through as an empty string when ``.env`` does not set it.
    """
    url = os.environ.get("OAUTH_ISSUER_URL")
    if url is None or url.strip() == "":
        return None
    return url


def load_server_runtime_config() -> ServerRuntimeConfig:
    """Read the server's environment variables into a ``ServerRuntimeConfig``."""
    return ServerRuntimeConfig(
        runs_dir=Path(os.environ.get("GLOSSOGEN_RUNS_DIR", "./runs")),
        oauth_issuer_url=_read_oauth_issuer_url(),
        allowed_origins=_parse_allowed_origins(),
        feature_flags=load_feature_flags(),
    )
