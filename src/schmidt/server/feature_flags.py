"""Server feature flags resolved from environment variables.

Gates optional server capabilities exposed over HTTP. Currently controls
whether the REST evaluation-launch endpoint (used by the frontend "Run Eval"
button) is enabled. The CLI ``schmidt evaluate`` command is a separate entry
point and is not affected by these flags.
"""

import os
from dataclasses import dataclass

_DISABLED_VALUES = frozenset({"false", "0", "no", "off"})


def _env_flag_enabled(var_name: str, default_enabled: bool) -> bool:
    """Return whether a boolean env flag is enabled.

    An unset variable resolves to ``default_enabled``. A set variable is
    enabled unless its value is ``false``/``0``/``no``/``off`` (case-insensitive).
    """
    raw = os.environ.get(var_name)
    if raw is None:
        return default_enabled
    return raw.strip().lower() not in _DISABLED_VALUES


@dataclass(frozen=True)
class FeatureFlags:
    """Resolved server feature flags."""

    evaluations_enabled: bool


def load_feature_flags() -> FeatureFlags:
    """Read feature-flag env vars into a ``FeatureFlags`` instance."""
    return FeatureFlags(
        evaluations_enabled=_env_flag_enabled(var_name="ENABLE_EVALUATIONS", default_enabled=True),
    )
