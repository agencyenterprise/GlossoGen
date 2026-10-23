"""Which rows the per-round and per-agent tables have.

The export's round and agent tables and the analysis's round and agent grains read
these, so a chart and the exported table it would come from cover the same
observations.
"""

from collections.abc import Iterable


def reported_round_numbers(rounds_by_metric: Iterable[Iterable[int]]) -> list[int]:
    """Return every round at least one metric reported, ascending.

    A round no metric reported gets no row, which reads as no observation rather
    than a zero.
    """
    return sorted({number for rounds in rounds_by_metric for number in rounds})


def agent_row_ids(
    roster_ids: Iterable[str], agents_by_metric: Iterable[Iterable[str]]
) -> list[str]:
    """Return the roster's agent ids, then any id only a metric named.

    Roster ids keep roster order and metric-only ids follow in the order first seen,
    so a per-agent number is never dropped for naming an id the roster is missing.
    """
    ids = dict.fromkeys(roster_ids)
    for agent_ids in agents_by_metric:
        ids.update(dict.fromkeys(agent_ids))
    return list(ids)
