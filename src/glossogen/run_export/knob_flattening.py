"""Turning a run's recorded scenario config into flat, named columns.

The recorded config is the source of truth here, not any knobs model. A scenario's
knobs class ignores extra keys, so it cannot tell you what an older run actually
ran with; the `scenario_config` on the run's first event can.

One flattening rule, applied everywhere, with no per-knob special cases:

* a scalar is its own column
* a mapping is exploded recursively with dotted keys, so `model_overrides`
  becomes `model_overrides.field_observer.model`
* a list becomes one column holding compact JSON

Lists stay whole because the ones that appear here have no sane column expansion.
`scheduled_events` is a list of tagged objects whose length varies per run, so
exploding it by index would invent columns that mean different things in different
rows.

The column set therefore depends on values and not only on top-level keys: two
runs of one scenario whose `model_overrides` name different agents contribute
different columns. That is the same sparseness a mixed-scenario selection
produces, and it needs no separate handling.
"""

from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple, cast

from glossogen.run_export.csv_cell_text import render_json, render_scalar

KNOB_COLUMN_PREFIX = "knob."


class KnobCell(NamedTuple):
    """One flattened knob: its dotted key and its rendered cell text."""

    key: str
    text: str


def _is_scalar(value: Any) -> bool:
    """Return True for values that render as one cell without further structure."""
    return value is None or isinstance(value, (str, int, float, bool))


def _flatten(prefix: str, value: Any, into: list[KnobCell]) -> None:
    """Append the cells ``value`` contributes under the dotted ``prefix``."""
    if _is_scalar(value):
        into.append(KnobCell(key=prefix, text=render_scalar(value=value)))
        return
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, Any], value)
        if not mapping:
            # Otherwise the key vanishes and "recorded as empty" is indistinguishable
            # from "never recorded", which is the distinction an empty list keeps.
            into.append(KnobCell(key=prefix, text=render_json(value={})))
            return
        for raw_key in sorted(mapping, key=str):
            _flatten(prefix=f"{prefix}.{raw_key}", value=mapping[raw_key], into=into)
        return
    if isinstance(value, Sequence):
        into.append(KnobCell(key=prefix, text=render_json(value=value)))
        return
    into.append(KnobCell(key=prefix, text=render_scalar(value=value)))


def flatten_knobs(scenario_config: Mapping[str, Any]) -> list[KnobCell]:
    """Flatten one run's scenario config into prefixed, dotted knob cells."""
    cells: list[KnobCell] = []
    for raw_key in sorted(scenario_config, key=str):
        _flatten(
            prefix=f"{KNOB_COLUMN_PREFIX}{raw_key}",
            value=scenario_config[raw_key],
            into=cells,
        )
    return cells


def knob_cells_by_key(scenario_config: Mapping[str, Any]) -> dict[str, str]:
    """Flatten one run's config into a key-to-cell-text mapping."""
    return {cell.key: cell.text for cell in flatten_knobs(scenario_config=scenario_config)}
