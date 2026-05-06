"""Streamlit tab comparing round_success between baseline_oss and oss_frontier runs.

The view is a pivot table with budgets on the rows and a two-level column
header — outer level is ``PM=T`` / ``PM=F`` (postmortem enabled vs disabled),
inner level is the engineer→observer config (or ``baseline_oss``). Each cell
shows three metrics on separate lines (round_success, perplexity, language
emergence). Cell background colour is driven by **mean round_success only**,
on a red→yellow→green gradient so improvements stand out visually.

The baseline_oss column is restricted to **llama-llama** runs (the OSS engineer
common to every oss_frontier mixed-model cell), so each comparison column shares
the same OSS-baseline backbone. Budgets shown: ``250s`` and ``800s``.
"""

from typing import NamedTuple, cast

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.colors import to_hex

from analysis.results_viewer.oss_frontier_data import CellRun, list_oss_frontier_runs
from analysis.results_viewer.run_catalog import EvaluatedRun

_SUPPORTED_BUDGETS: tuple[int, ...] = (250, 800)
_BASELINE_CONFIG_KEY = "baseline_oss"
_GRADIENT_CMAP = plt.get_cmap("RdYlGn")


class _SeriesBucket(NamedTuple):
    """Per-(config, pm, budget) aggregate of all three metrics across replicas."""

    config: str
    pm: bool
    budget: int
    n: int
    mean_round_success: float
    mean_perplexity: float | None
    mean_language_emergence: float | None


def _config_key(run: CellRun) -> str:
    """Inner-column key.

    Returns ``baseline_oss`` for uniform-OSS runs, otherwise
    ``"<eng> engineer → <obs> observer"`` so each cell reads as a sentence.
    """
    if run.group == "baseline_oss":
        return _BASELINE_CONFIG_KEY
    return f"{run.engineer} engineer → {run.field_observer} observer"


def _config_sort_key(config: str) -> tuple[int, str]:
    """baseline_oss first, then frontier configs alphabetically."""
    if config == _BASELINE_CONFIG_KEY:
        return (0, config)
    return (1, config)


def _pm_label(pm: bool) -> str:
    """Outer-column label."""
    return "Postmortem enabled" if pm else "Postmortem disabled"


def _mean_or_none(values: list[float]) -> float | None:
    """Mean of ``values``, or ``None`` if the list is empty."""
    if not values:
        return None
    return sum(values) / len(values)


def _aggregate(runs: list[CellRun]) -> list[_SeriesBucket]:
    """Group runs by (config, pm, budget) and compute mean of each metric per bucket."""
    buckets: dict[tuple[str, bool, int], list[CellRun]] = {}
    for run in runs:
        key = (_config_key(run=run), run.postmortem, run.budget)
        buckets.setdefault(key, []).append(run)
    out: list[_SeriesBucket] = []
    for (config, pm, budget), replicas in buckets.items():
        rs_values = [r.round_success for r in replicas]
        mean_rs = sum(rs_values) / len(rs_values)
        mean_ppl = _mean_or_none(
            values=[r.perplexity for r in replicas if r.perplexity is not None]
        )
        mean_le = _mean_or_none(
            values=[r.language_emergence for r in replicas if r.language_emergence is not None]
        )
        out.append(
            _SeriesBucket(
                config=config,
                pm=pm,
                budget=budget,
                n=len(replicas),
                mean_round_success=mean_rs,
                mean_perplexity=mean_ppl,
                mean_language_emergence=mean_le,
            )
        )
    return out


def _format_cell_text(entry: _SeriesBucket | None) -> str:
    """Multi-line cell text (HTML): one ``<br>``-separated line per metric.

    The styler is rendered via ``st.html`` so ``<br>`` tags translate to
    visual line breaks inside each cell.
    """
    if entry is None:
        return "—"
    rs = f"rs: {entry.mean_round_success:.3f}"
    ppl = f"ppl: {entry.mean_perplexity:.2f}" if entry.mean_perplexity is not None else "ppl: —"
    le = (
        f"le: {entry.mean_language_emergence:.2f}"
        if entry.mean_language_emergence is not None
        else "le: —"
    )
    n = f"n: {entry.n}"
    return f"{rs}<br>{ppl}<br>{le}<br>{n}"


def _build_pivot_frames(
    buckets: list[_SeriesBucket],
    selected_budgets: set[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(display_df, mean_df)`` sharing a two-level column index ``(PM, config)``.

    ``display_df`` cells are multi-line strings (one per metric). ``mean_df``
    cells are floats holding the round_success mean and drive the colour
    gradient. Missing cells are ``NaN`` in ``mean_df`` and ``"—"`` in
    ``display_df``.
    """
    configs = sorted({b.config for b in buckets}, key=_config_sort_key)
    pms = [True, False]
    column_tuples: list[tuple[str, str]] = []
    for pm in pms:
        present_configs = {b.config for b in buckets if b.pm == pm}
        for config in configs:
            if config in present_configs:
                column_tuples.append((_pm_label(pm=pm), config))
    columns = pd.MultiIndex.from_tuples(tuples=column_tuples, names=["PM", "config"])
    row_index = pd.Index(data=[f"{b}s" for b in sorted(selected_budgets)], name="budget")
    display_df = pd.DataFrame(index=row_index, columns=columns, dtype=object)
    mean_df = pd.DataFrame(index=row_index, columns=columns, dtype=float)
    by_key = {(_pm_label(pm=b.pm), b.config, b.budget): b for b in buckets}
    for budget in sorted(selected_budgets):
        row_label = f"{budget}s"
        for pm_label, config in column_tuples:
            entry = by_key.get((pm_label, config, budget))
            display_df.loc[row_label, (pm_label, config)] = _format_cell_text(entry=entry)
            if entry is not None:
                mean_df.loc[row_label, (pm_label, config)] = entry.mean_round_success
    return display_df, mean_df


def _gradient_css_for_value(value: float) -> str:
    """``background-color`` CSS for a 0–1 round_success value on the RdYlGn ramp."""
    if pd.isna(value):
        return ""
    clamped = max(0.0, min(1.0, float(value)))
    rgba = _GRADIENT_CMAP(clamped)
    return f"background-color: {to_hex(rgba)}; color: black;"


def _build_css_frame(mean_df: pd.DataFrame) -> pd.DataFrame:
    """Same-shaped DataFrame of CSS strings driven by ``mean_df`` round_success."""
    css = pd.DataFrame("", index=mean_df.index, columns=mean_df.columns)
    for row in mean_df.index:
        for col in mean_df.columns:
            css.loc[row, col] = _gradient_css_for_value(value=cast(float, mean_df.loc[row, col]))
    return css


def _render_pivot_table(buckets: list[_SeriesBucket], selected_budgets: set[int]) -> None:
    """Render the multi-metric pivot with colour driven by round_success."""
    display_df, mean_df = _build_pivot_frames(buckets=buckets, selected_budgets=selected_budgets)
    if display_df.empty:
        st.info("No matching data for the current filters.")
        return
    css_df = _build_css_frame(mean_df=mean_df)
    styled = (
        display_df.style.apply(lambda _df: css_df, axis=None)
        .set_table_styles(
            [
                {"selector": "td", "props": [("padding", "8px 12px"), ("text-align", "left")]},
                {"selector": "th", "props": [("padding", "6px 10px"), ("text-align", "center")]},
                {"selector": "table", "props": [("border-collapse", "collapse")]},
            ]
        )
        .format(escape=None)
    )
    st.markdown(
        "**Per-cell metrics** — `rs` = mean round_success (drives colour, 0–1 scale); "
        "`ppl` = mean perplexity (nats, gpt2); `le` = mean rounds with language "
        "emergence; `n` = replica count."
    )
    st.html(styled.to_html())


def _render_runs_filter(runs: list[CellRun]) -> tuple[set[str], set[str], set[int]]:
    """Render three multi-select widgets and return the selected (config, PM, budget) sets.

    Each widget defaults to all options selected. Selecting a subset narrows the
    per-run rows below — equivalent to clicking a cell in the pivot above.
    """
    all_configs = sorted({_config_key(run=r) for r in runs}, key=_config_sort_key)
    all_pms = sorted({_pm_label(pm=r.postmortem) for r in runs}, reverse=True)
    all_budgets = sorted({r.budget for r in runs})
    cols = st.columns(3)
    with cols[0]:
        sel_configs = st.multiselect(
            label="Config",
            options=all_configs,
            default=all_configs,
            key="oss_frontier_filter_config",
        )
    with cols[1]:
        sel_pms = st.multiselect(
            label="PM",
            options=all_pms,
            default=all_pms,
            key="oss_frontier_filter_pm",
        )
    with cols[2]:
        sel_budgets = st.multiselect(
            label="Budget (s)",
            options=all_budgets,
            default=all_budgets,
            key="oss_frontier_filter_budget",
        )
    return set(sel_configs), set(sel_pms), set(sel_budgets)


def _render_runs_table(runs: list[CellRun], frontend_base: str) -> None:
    """Per-run table with all metrics, a clickable run link, and a coloured round_success column."""
    rows = sorted(
        runs,
        key=lambda r: (
            _config_sort_key(_config_key(run=r)),
            not r.postmortem,
            r.budget,
            r.run_id,
        ),
    )
    table_rows = [
        {
            "config": _config_key(run=r),
            "PM": _pm_label(pm=r.postmortem),
            "budget": r.budget,
            "rounds": r.total_rounds,
            "round_success": float(r.round_success),
            "perplexity": (float(r.perplexity) if r.perplexity is not None else float("nan")),
            "language_emergence": (
                float(r.language_emergence) if r.language_emergence is not None else float("nan")
            ),
            "run": f"{frontend_base}/runs/{r.run_id}",
        }
        for r in rows
    ]
    if not table_rows:
        st.info("No runs match the current filter combination.")
        return
    df = pd.DataFrame(table_rows)
    styled = df.style.background_gradient(
        subset=["round_success"], cmap="RdYlGn", vmin=0.0, vmax=1.0
    ).format(
        {
            "round_success": "{:.3f}",
            "perplexity": "{:.2f}",
            "language_emergence": "{:.2f}",
        },
        na_rep="—",
    )
    link_column = st.column_config.LinkColumn(label="run", display_text=r"runs/.*/(\d+)")
    st.dataframe(
        data=styled,
        column_config={"run": link_column},
        hide_index=True,
        width="stretch",
    )


def _render_frontend_base() -> str:
    """Text input for the schmidt frontend base URL used for per-run links."""
    raw = st.text_input(
        label="Frontend base URL (for run links)",
        value="http://localhost:3000",
        key="oss_frontier_frontend_base",
        help=(
            "Per-run URLs in the table below link to "
            "`<base>/runs/<scenario>/<run_dir_name>` on this host."
        ),
    )
    return raw.rstrip("/")


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the OSS-vs-Frontier comparison tab as a colored pivot table."""
    st.header("OSS vs Frontier — round_success comparison")
    st.caption(
        "Mean round_success per configuration, with PM enabled / disabled merged "
        "under each engineer→observer column. baseline_oss is restricted to "
        "llama-llama runs at the same budget so the comparison shares an OSS "
        "backbone. Cells coloured red→green on the absolute 0–1 scale."
    )
    raw = list_oss_frontier_runs(evaluated=evaluated)
    if not raw:
        st.info("No baseline_oss or oss_frontier runs with round_success measurements yet.")
        return
    runs = [
        r
        for r in raw
        if r.budget in _SUPPORTED_BUDGETS and (r.group != "baseline_oss" or r.engineer == "llama")
    ]
    if not runs:
        st.info("No runs match the supported budgets (250s, 800s).")
        return
    buckets = _aggregate(runs=runs)
    _render_pivot_table(buckets=buckets, selected_budgets=set(_SUPPORTED_BUDGETS))
    frontend_base = _render_frontend_base()
    st.subheader("Per-run scores")
    sel_configs, sel_pms, sel_budgets = _render_runs_filter(runs=runs)
    filtered = [
        r
        for r in runs
        if _config_key(run=r) in sel_configs
        and _pm_label(pm=r.postmortem) in sel_pms
        and r.budget in sel_budgets
    ]
    _render_runs_table(runs=filtered, frontend_base=frontend_base)
