"""Resolves the per-call output-token cap for every LLM provider.

Reads ``LLM_MAX_TOKENS`` from the environment so the same cap applies to
the Claude, OpenAI, and HuggingFace providers without duplicating the
default in three places. The default is large enough to fit the
verbose communication-feature pipeline judge outputs (free-form labels
with multi-round evidence citations + verbatim quotes), which used to
truncate against the previous 4096 cap.
"""

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_LLM_MAX_TOKENS = 16384
"""Default cap applied when ``LLM_MAX_TOKENS`` is unset."""


def resolve_max_tokens() -> int:
    """Return the configured per-call max-output-tokens for LLM providers.

    Honours the ``LLM_MAX_TOKENS`` environment variable when set to a
    positive integer; falls back to :data:`DEFAULT_LLM_MAX_TOKENS`
    otherwise. Logs a warning (not an exception) on malformed values so
    the caller still gets a usable cap.
    """
    raw = os.environ.get("LLM_MAX_TOKENS")
    if raw is None:
        return DEFAULT_LLM_MAX_TOKENS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Ignoring malformed LLM_MAX_TOKENS=%r; falling back to %d",
            raw,
            DEFAULT_LLM_MAX_TOKENS,
        )
        return DEFAULT_LLM_MAX_TOKENS
    if value <= 0:
        logger.warning(
            "Ignoring non-positive LLM_MAX_TOKENS=%d; falling back to %d",
            value,
            DEFAULT_LLM_MAX_TOKENS,
        )
        return DEFAULT_LLM_MAX_TOKENS
    return value
