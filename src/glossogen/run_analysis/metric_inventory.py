"""Which metrics a selection carries, and what unit each reports in.

Read off the runs' own reports rather than off a registry, exactly as the export's
columns are, so a metric a scenario package shipped last week is measurable the moment
a report names it.

The unit comes from the first run carrying the metric. Units are not always constant
across runs (one can name the size of the vocabulary a metric scored against), which
is why the export puts it in a legend rather than on every row, and why here it labels
an axis rather than a cell.
"""

from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_run_record import AnalysisRunRecord
from glossogen.run_analysis.measure_resolution import (
    RUN_COLUMN_UNITS,
    MeasureField,
    MeasureSource,
)


def metric_units(records: list[AnalysisRunRecord]) -> dict[str, str]:
    """Return each metric name's score unit, from the first run carrying it."""
    units: dict[str, str] = {}
    for record in records:
        for name, metric in record.metrics.items():
            if name in units:
                continue
            units[name] = metric.score_unit
    return units


def available_metric_names(records: list[AnalysisRunRecord]) -> list[str]:
    """Return every metric name the selected runs' reports carry, sorted."""
    return sorted(metric_units(records=records))


def keyed_metric_names(records: list[AnalysisRunRecord]) -> list[str]:
    """Return every metric name that wrote keyed observations, sorted.

    These are registry names, and a report's measurement names are not always the
    same: a metric that scores each channel separately reports
    ``language_repetition_team_a`` while its sidecar is one file registered under
    ``language_repetition``. Offering the report's names at the keyed grain would
    offer names no keyed row carries, so the two lists are kept apart.
    """
    names: set[str] = set()
    for record in records:
        names.update(record.keyed)
    return sorted(names)


def measure_unit(
    field: MeasureField,
    grain: AnalysisGrain,
    units: dict[str, str],
) -> str:
    """Return the unit to label one measure with at one grain.

    A metric's unit describes its run-level score. At the keyed grain the numbers are
    not that score. ``communication_feature_presence`` scores categories at or above
    a threshold while its keyed observations are confidences, so nothing is claimed
    there rather than the wrong quantity.

    Both the catalog and the query answer read this. While each decided for itself
    they were free to disagree, and did: the picker offered a unit the result blanked.
    """
    if field.source is MeasureSource.RUN_COLUMN:
        return RUN_COLUMN_UNITS.get(field.key, "")
    if grain is AnalysisGrain.KEYED:
        return ""
    return units.get(field.key, "")
