"""Extracts per-round hit lists from an evaluator's free-text evidence."""

import re

_ROUNDS_PREFIX = "Rounds:"
_INT_PATTERN = re.compile(r"\d+")


def extract_rounds_identified(evidence: list[str]) -> list[int]:
    """Return the rounds flagged by an evaluator, parsed from its evidence list.

    Evaluators that detect a per-round phenomenon emit an evidence line shaped
    like ``"Rounds: 1, 3, 4, 6"``. This walks the evidence list, finds the
    first such line, and parses the integers. Evaluators without per-round
    tracking (e.g. ``round_success``) return an empty list.
    """
    for line in evidence:
        if line.startswith(_ROUNDS_PREFIX):
            return [int(match.group()) for match in _INT_PATTERN.finditer(line)]
    return []
