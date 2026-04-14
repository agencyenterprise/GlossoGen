"""Canonical list of generic evaluator names.

Kept in a separate module to avoid circular imports between
scenario_protocol and evaluator_registry. Both modules read
from this list instead of depending on each other.
"""

GENERIC_EVALUATOR_NAMES: list[str] = [
    "language_strangeness",
    "neologism",
    "shorthand_codes",
    "slang_emergence",
]
