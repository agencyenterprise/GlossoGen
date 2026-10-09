"""Checking a query's keys against what the selection carries.

Group-by keys, filter keys and measure keys are free text on the query. The engine
reads a dimension the rows do not have as a blank cell and a measure they do not
have as a missing number, so a mistyped key answers with one group named "" or
with every cell empty, and nothing says why. The check here resolves every key
against the field catalog built from the same records the query reads, so a key
the catalog would not offer is refused by name.

An empty selection is still answered with an empty result rather than refused: its
catalog carries no keys, so refusing against it would refuse every key. The same
holds per family of key. A selection with runs but no rows at the asked grain (a
cohort nothing has scored per round yet) offers no dimensions, so none are checked;
one whose runs carry no report offers no metric, so a metric measure is not checked
either and answers with blanks the way it did before evaluation. Run columns are
offered on every selection with runs, so a run-column measure is always checked.
"""

from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_query_models import AnalysisQuerySpec
from glossogen.run_analysis.analysis_result_models import AnalysisFieldCatalog


class UnknownAnalysisKeysError(ValueError):
    """A query names a dimension or a measure the selection does not carry."""

    def __init__(
        self,
        grain: AnalysisGrain,
        unknown_dimensions: list[str],
        unknown_measures: list[str],
        known_dimensions: list[str],
        known_measures: list[str],
    ) -> None:
        parts: list[str] = []
        if unknown_dimensions:
            parts.append(
                f"Unknown dimension key(s) at the {grain.value} grain: "
                f"{', '.join(unknown_dimensions)}. This selection carries: "
                f"{', '.join(known_dimensions)}."
            )
        if unknown_measures:
            parts.append(
                f"Unknown measure key(s) at the {grain.value} grain: "
                f"{', '.join(unknown_measures)}. This selection carries: "
                f"{', '.join(known_measures)}."
            )
        super().__init__(" ".join(parts))


def _measure_key(source: str, key: str) -> str:
    """Name a measure the way the error reports it: ``source:key``."""
    return f"{source}:{key}"


def check_query_keys(spec: AnalysisQuerySpec, catalog: AnalysisFieldCatalog) -> None:
    """Refuse a spec naming a dimension or a measure ``catalog`` does not offer.

    Raises :class:`UnknownAnalysisKeysError` naming every unknown key and the grain.
    A catalog over no runs checks nothing; a family of key the catalog offers none
    of is not checked.
    """
    if catalog.run_count == 0:
        return

    known_measures = [
        _measure_key(source=measure.source, key=measure.key) for measure in catalog.measures
    ]
    offered_sources = {measure.source for measure in catalog.measures}
    known = set(known_measures)
    unknown_measures = [
        _measure_key(source=measure.source.value, key=measure.key)
        for measure in spec.measures
        if measure.source.value in offered_sources
        and _measure_key(source=measure.source.value, key=measure.key) not in known
    ]

    unknown_dimensions: list[str] = []
    known_dimensions = [dimension.key for dimension in catalog.dimensions]
    if catalog.observation_count > 0:
        requested_dimensions = list(spec.group_by)
        requested_dimensions.extend(dimension_filter.key for dimension_filter in spec.filters)
        known_dimension_set = set(known_dimensions)
        unknown_dimensions = list(
            dict.fromkeys(key for key in requested_dimensions if key not in known_dimension_set)
        )

    if not unknown_dimensions and not unknown_measures:
        return
    raise UnknownAnalysisKeysError(
        grain=spec.grain,
        unknown_dimensions=unknown_dimensions,
        unknown_measures=list(dict.fromkeys(unknown_measures)),
        known_dimensions=known_dimensions,
        known_measures=known_measures,
    )
