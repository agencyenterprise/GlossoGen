"""Canonical list of generic metric names.

Kept in a separate module to avoid circular imports between
scenario_protocol and metric_registry. Both modules read from this
list instead of depending on each other.
"""

GENERIC_METRIC_NAMES: list[str] = [
    "content_filter_refusal",
    "language_strangeness",
    "mean_message_length",
    "mean_word_length",
    "neologism",
    "perplexity",
    "round_ended_idle",
    "round_ended_timeout",
    "shorthand_codes",
    "slang_emergence",
]
