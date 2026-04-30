"""Canonical list of generic evaluator names.

Kept in a separate module to avoid circular imports between
scenario_protocol and evaluator_registry. Both modules read
from this list instead of depending on each other.
"""

GENERIC_EVALUATOR_NAMES: list[str] = [
    "content_filter_refusal",
    "language_strangeness",
    "neologism",
    "perplexity",
    "round_ended_idle",
    "round_ended_timeout",
    "shorthand_codes",
    "slang_emergence",
]
