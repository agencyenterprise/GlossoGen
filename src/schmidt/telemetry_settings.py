"""Telemetry (Langfuse) environment configuration.

Reads the Langfuse env vars once so the simulation run path can decide whether
to initialize OpenTelemetry export. Telemetry is enabled only when both the
public and secret keys are present.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetrySettings:
    """Resolved Langfuse env config; telemetry is enabled only when both keys are set."""

    public_key: str | None
    secret_key: str | None
    host: str | None

    @property
    def enabled(self) -> bool:
        """Return True when both Langfuse API keys are configured."""
        return self.public_key is not None and self.secret_key is not None


def load_telemetry_settings() -> TelemetrySettings:
    """Read Langfuse env vars into a ``TelemetrySettings`` instance."""
    return TelemetrySettings(
        public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
        host=os.environ.get("LANGFUSE_HOST"),
    )
