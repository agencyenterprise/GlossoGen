"""What one row of an analysis is: a run, a round, an agent, or a metric's own key.

The first three mirror the export's tables of the same names. The fourth is for
metrics that measure a run along an axis of their own, such as a feature ontology's
categories, a probe's questions, or a message id. Those numbers went to a file beside
the report because a Measurement has nowhere to put them, and this grain's dimensions
are whatever keys the metric used, so nothing here has to know what any of them mean.

The export's message and round-context tables are not grains. Their cells are what an
agent said and what it was told, so there is nothing on them to average.
"""

from enum import Enum


class AnalysisGrain(str, Enum):
    """The unit of observation a query groups and aggregates over."""

    RUN = "run"
    ROUND = "round"
    AGENT = "agent"
    KEYED = "keyed"
