"""Shared scenario radio selector for the results-viewer tabs.

Every tab that lets the user pick a scenario defaults to ``veyru`` when
it is among the available options, falling back to the first option
otherwise. This module centralizes that default and the radio rendering
so the tabs do not each repeat the selector logic.
"""

import streamlit as st

DEFAULT_SCENARIO = "veyru"


def default_scenario_index(options: list[str]) -> int:
    """Index of the default scenario in ``options`` (``veyru`` if present, else 0)."""
    if DEFAULT_SCENARIO in options:
        return options.index(DEFAULT_SCENARIO)
    return 0


def render_scenario_radio(options: list[str], key: str) -> str | None:
    """Render a horizontal ``Scenario`` radio defaulting to ``veyru``.

    Returns the chosen scenario name, or ``None`` when ``options`` is
    empty so callers can short-circuit before rendering the rest of the
    tab.
    """
    if not options:
        return None
    return st.radio(
        label="Scenario",
        options=options,
        index=default_scenario_index(options=options),
        horizontal=True,
        key=key,
    )
