"""Metrics contributed by other installed distributions, by name only.

A distribution advertises a metric by declaring an entry point::

    [project.entry-points."glossogen.metrics"]
    my_signal = "my_metrics.my_signal:MySignalMetric"

The entry-point name is the name the metric answers to on ``--metrics`` and in
the report, so it must match the class's own ``name`` attribute.

This module deliberately does not import ``Metric``, and so cannot import the
classes it names. ``metric_protocol`` imports the scenario contract, and the
scenario contract asks this module which metrics it may advertise, so importing
metric classes from here would close that cycle. It is the same reason
``generic_metric_names`` exists.

Loading the classes is :func:`glossogen.evaluation.metric_core.metric_registry.available_metrics`,
which already lives on the far side of that cycle.
"""

from importlib.metadata import EntryPoint

from glossogen.plugin_entry_points import entry_points_in_group

METRIC_ENTRY_POINT_GROUP = "glossogen.metrics"


def external_metric_entry_points() -> dict[str, EntryPoint]:
    """Return every externally-declared metric entry point, keyed by name.

    Reads installed metadata and imports nothing.
    """
    return entry_points_in_group(group=METRIC_ENTRY_POINT_GROUP)


def external_metric_names() -> list[str]:
    """Return the names of metrics other installed distributions declare."""
    return sorted(external_metric_entry_points())
