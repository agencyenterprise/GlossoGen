"""Projecting a probe-similarity artifact's groups into keyed observations.

The replica-self and agent-pair artifacts differ in what identifies a group. One is
keyed by the agent, the other by the pair of agents the question was compared across.
Both carry one ``mean_similarity`` per group and both name the question and the
cutoff. So the projection is shared, and each group's own identifying fields come
along as keys without either metric listing them.

Every scalar field on the group becomes a key. A list field (the agent ids of a pair,
the replica indices) is joined, because a key is a dimension cell and a cell holds
text. ``response_texts`` and ``cells`` are dropped: they are the evidence the number
was computed from, not an axis anything groups by.
"""

from collections.abc import Iterator
from typing import Any, cast

from glossogen.evaluation.metric_core.keyed_observation import KeyedObservation
from glossogen.evaluation.metric_core.sidecar_reading import key_text, number_or_none

VALUE_FIELD = "mean_similarity"

# The evidence a similarity was computed from: whole model responses and the
# pairwise matrix. Neither is something a chart groups by, and both are large.
_EVIDENCE_FIELDS = frozenset(
    {"response_texts", "response_texts_by_agent", "cells", "pairs", VALUE_FIELD}
)


def _keys_of(group: dict[str, Any]) -> dict[str, str]:
    """Return the group's identifying fields as dimension cells."""
    keys: dict[str, str] = {}
    for name, value in group.items():
        if name in _EVIDENCE_FIELDS:
            continue
        if isinstance(value, list):
            keys[name] = ", ".join(key_text(value=item) for item in cast(list[Any], value))
            continue
        keys[name] = key_text(value=value)
    return keys


def similarity_observations(groups: list[dict[str, Any]]) -> Iterator[KeyedObservation]:
    """Yield one observation per group carrying a mean similarity."""
    for group in groups:
        value = number_or_none(value=group.get(VALUE_FIELD))
        if value is None:
            continue
        yield KeyedObservation(keys=_keys_of(group=group), value=value)
