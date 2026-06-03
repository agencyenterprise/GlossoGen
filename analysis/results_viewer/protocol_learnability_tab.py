"""Streamlit "Protocol learnability" tab.

Ranks every ``protocol_learnability`` baseline by how well a fresh same-model
field observer can reconstruct stabilization performance from the windowed
link transcript alone, then surfaces the ``communication_feature_presence``
categories that distinguish the high-learnability protocols from the low ones.

The rounds-window is fixed at the experiment's canonical 16–25 — the ten
genuinely-new seed-42 cases that exist in every derived run. Two sections:

* Expected vs learned — per-model means with SEM error bars on top, plus a
  per-baseline paired scatter below; click a baseline marker to open its
  source run.
* Feature contrast — top categories by ``|high_mean − low_mean|`` between the
  top-tertile and bottom-tertile learners.
"""

import math
import statistics
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.protocol_learnability_data import (
    BaselineLearnability,
    FeatureEvidence,
    FeatureEvidenceSample,
    _iter_run_dirs,
    _read_labels,
    feature_contrast,
    feature_evidence,
    load_ontology_descriptions,
    load_results,
)
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import maybe_open_clicked_run, run_url

_WINDOW_LO = 16
_WINDOW_HI = 25
_TERTILE_FRACTION = 0.33
_DEFAULT_FRONTEND_HOST = "http://localhost:3000"
_DEFAULT_GROUP_SLUG = "local"

_MODEL_COLORS = {
    "sonnet": "#1f77b4",
    "opus47": "#d62728",
    "gpt54": "#2ca02c",
    "unknown": "#777777",
}

# Cross-family marker uses an outline color taken from the OBSERVER family so
# the viewer can tell at a glance which family read the protocol. Filled-shape
# fallback for stylistic consistency with the same-family square marker.
_CROSS_FAMILY_OUTLINE_COLOR = {
    "sonnet": "#1f77b4",
    "opus47": "#d62728",
    "gpt54": "#2ca02c",
}

# The four comparison conditions both charts can draw, in canonical column order.
# Each carries the symbol used in the plots so chart legends/titles can be built
# from whatever subset the user enables via the condition checkboxes.
_CONDITION_KEYS = ("expected", "expected_no_postmortem", "learned", "cross_family")
_CONDITION_SYMBOL_LABELS = {
    "expected": "○ expected",
    "expected_no_postmortem": "△ expected_no_postmortem",
    "learned": "■ learned",
    "cross_family": "◇ cross_family",
}
_DEFAULT_CONDITIONS = frozenset({"expected_no_postmortem", "learned"})


def _render_condition_checkboxes() -> set[str]:
    """Horizontal checkbox row selecting which conditions both charts draw.

    Defaults to ``expected_no_postmortem`` and ``learned`` so the plots open on
    the two-condition comparison rather than all four symbols at once.
    """
    st.markdown("**Conditions**")
    cols = st.columns(len(_CONDITION_KEYS))
    selected: set[str] = set()
    for col, key in zip(cols, _CONDITION_KEYS):
        if col.checkbox(
            label=key,
            value=key in _DEFAULT_CONDITIONS,
            key=f"protocol_learnability_condition_{key}",
        ):
            selected.add(key)
    return selected


def _filter_models(
    results: list[BaselineLearnability], selected: set[str]
) -> list[BaselineLearnability]:
    """Keep only baselines whose ``model_short`` is in ``selected``."""
    if not selected:
        return results
    return [r for r in results if r.model_short in selected]


def _render_per_model_bars(
    results: list[BaselineLearnability], selected_conditions: set[str]
) -> None:
    """Per-model strip plot: each baseline is one bullet, mean drawn as a bar.

    Each model gets **three adjacent columns** on the x-axis:
    ``<model> · baseline`` (intact team continued = resume runs, postmortem on),
    ``<model> · no_postmortem`` (intact team but postmortem killed going forward
    — isolates the no-postmortem effect), and ``<model> · learned`` (a fresh
    same-model field observer = replace runs, postmortem off). Within each
    column we plot the per-baseline ``round_success`` means (each itself
    averaged over its 3 replicas), jittered horizontally for visibility. The
    cohort mean is drawn as a thick horizontal bar across each column with SEM
    error bars. Baselines without any ``resume_expected_no_postmortem`` replicas
    are skipped in the no_postmortem column (no point plotted) but still appear
    in the other two.
    """
    by_model: dict[str, list[BaselineLearnability]] = {}
    for r in results:
        by_model.setdefault(r.model_short, []).append(r)
    models = sorted(by_model)
    within_model_gap = 0.8
    between_model_gap = 1.4
    jitter_half_width = 0.12
    slots_per_model = 4

    def _column_x(model_index: int, slot: int) -> float:
        base = model_index * (slots_per_model * within_model_gap + between_model_gap)
        return base + slot * within_model_gap

    def _jitter(src_id: str) -> float:
        # Deterministic per-baseline horizontal offset inside the column width.
        return ((hash(src_id) % 1000) / 999.0 - 0.5) * 2 * jitter_half_width

    fig = go.Figure()
    tick_vals: list[float] = []
    tick_text: list[str] = []
    # The "cohort mean ± SEM" legend entry is shown once, on whichever mean
    # trace renders first — the expected column may be deselected, so it cannot
    # be pinned to the baseline trace.
    mean_legend_shown = False
    for i, model in enumerate(models):
        color = _MODEL_COLORS.get(model, "#777777")
        rs = by_model[model]
        base_x = _column_x(model_index=i, slot=0)
        no_pm_x = _column_x(model_index=i, slot=1)
        learned_x = _column_x(model_index=i, slot=2)
        cross_x = _column_x(model_index=i, slot=3)
        budgets = sorted({r.budget for r in rs})
        budget_tag = f"b={'/'.join(budgets)}"
        if "expected" in selected_conditions:
            tick_vals.append(base_x)
            tick_text.append(f"{model} · {budget_tag}<br>baseline")
        if "expected_no_postmortem" in selected_conditions:
            tick_vals.append(no_pm_x)
            tick_text.append(f"{model} · {budget_tag}<br>no_postmortem")
        if "learned" in selected_conditions:
            tick_vals.append(learned_x)
            tick_text.append(f"{model} · {budget_tag}<br>learned")
        if "cross_family" in selected_conditions:
            tick_vals.append(cross_x)
            tick_text.append(f"{model} · {budget_tag}<br>cross_family")

        base_xs = [base_x + _jitter(r.src_id) for r in rs]
        base_ys = [r.expected_mean for r in rs]
        base_hover = [
            f"{r.src_id} ({model}) · baseline<br>"
            f"round_success={r.expected_mean:.3f}  n={r.n_expected}"
            for r in rs
        ]
        no_pm_rs = [r for r in rs if r.n_expected_no_pm > 0]
        no_pm_xs = [no_pm_x + _jitter(r.src_id) for r in no_pm_rs]
        no_pm_ys = [r.expected_no_pm_mean for r in no_pm_rs]
        no_pm_hover = [
            f"{r.src_id} ({model}) · no_postmortem<br>"
            f"round_success={r.expected_no_pm_mean:.3f}  n={r.n_expected_no_pm}"
            for r in no_pm_rs
        ]
        learned_xs = [learned_x + _jitter(r.src_id) for r in rs]
        learned_ys = [r.learned_mean for r in rs]
        learned_hover = [
            f"{r.src_id} ({model}) · learned<br>"
            f"round_success={r.learned_mean:.3f}  n={r.n_learned}"
            for r in rs
        ]
        cross_rs = [r for r in rs if r.n_cross_family > 0]
        cross_xs = [cross_x + _jitter(r.src_id) for r in cross_rs]
        cross_ys = [r.cross_family_mean for r in cross_rs]
        cross_marker_colors = [
            _CROSS_FAMILY_OUTLINE_COLOR.get(r.cross_family_observer or "", "#777777")
            for r in cross_rs
        ]
        cross_hover = [
            f"{r.src_id} ({model} → {r.cross_family_observer}) · cross_family<br>"
            f"round_success={r.cross_family_mean:.3f}  n={r.n_cross_family}"
            for r in cross_rs
        ]

        if "expected" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=base_xs,
                    y=base_ys,
                    mode="markers",
                    marker={
                        "symbol": "circle-open",
                        "size": 10,
                        "line": {"width": 1.6, "color": color},
                        "color": color,
                    },
                    name="baseline (resume — intact team)",
                    legendgroup="baseline",
                    showlegend=(i == 0),
                    hovertext=base_hover,
                    hoverinfo="text",
                )
            )
        if no_pm_rs and "expected_no_postmortem" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=no_pm_xs,
                    y=no_pm_ys,
                    mode="markers",
                    marker={
                        "symbol": "triangle-up-open",
                        "size": 11,
                        "line": {"width": 1.6, "color": color},
                        "color": color,
                    },
                    name="no_postmortem (resume — intact team, postmortem off)",
                    legendgroup="no_postmortem",
                    showlegend=(i == 0),
                    hovertext=no_pm_hover,
                    hoverinfo="text",
                )
            )
        if "learned" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=learned_xs,
                    y=learned_ys,
                    mode="markers",
                    marker={"symbol": "square", "size": 10, "color": color},
                    name="learned (replace — fresh observer)",
                    legendgroup="learned",
                    showlegend=(i == 0),
                    hovertext=learned_hover,
                    hoverinfo="text",
                )
            )
        if cross_rs and "cross_family" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=cross_xs,
                    y=cross_ys,
                    mode="markers",
                    marker={
                        "symbol": "diamond-open",
                        "size": 12,
                        "line": {"width": 1.8, "color": cross_marker_colors},
                        "color": cross_marker_colors,
                    },
                    name="cross_family (replace — fresh other-family observer)",
                    legendgroup="cross_family",
                    showlegend=(i == 0),
                    hovertext=cross_hover,
                    hoverinfo="text",
                )
            )
        base_mean = statistics.mean(base_ys)
        learned_mean = statistics.mean(learned_ys)
        base_sem = statistics.stdev(base_ys) / math.sqrt(len(base_ys)) if len(base_ys) >= 2 else 0.0
        learned_sem = (
            statistics.stdev(learned_ys) / math.sqrt(len(learned_ys))
            if len(learned_ys) >= 2
            else 0.0
        )
        if "expected" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=[base_x],
                    y=[base_mean],
                    mode="markers",
                    marker={
                        "symbol": "line-ew-open",
                        "size": 28,
                        "color": color,
                        "line": {"width": 3},
                    },
                    error_y={
                        "type": "data",
                        "array": [base_sem],
                        "thickness": 2,
                        "width": 10,
                        "color": color,
                    },
                    name="cohort mean ± SEM",
                    legendgroup="mean",
                    showlegend=(not mean_legend_shown),
                    hovertext=(
                        f"{model} · baseline<br>"
                        f"mean={base_mean:.3f}  SEM={base_sem:.3f}  n={len(rs)}"
                    ),
                    hoverinfo="text",
                )
            )
            mean_legend_shown = True
        if no_pm_ys and "expected_no_postmortem" in selected_conditions:
            no_pm_mean = statistics.mean(no_pm_ys)
            no_pm_sem = (
                statistics.stdev(no_pm_ys) / math.sqrt(len(no_pm_ys)) if len(no_pm_ys) >= 2 else 0.0
            )
            fig.add_trace(
                go.Scatter(
                    x=[no_pm_x],
                    y=[no_pm_mean],
                    mode="markers",
                    marker={
                        "symbol": "line-ew-open",
                        "size": 28,
                        "color": color,
                        "line": {"width": 3},
                    },
                    error_y={
                        "type": "data",
                        "array": [no_pm_sem],
                        "thickness": 2,
                        "width": 10,
                        "color": color,
                    },
                    name="cohort mean ± SEM",
                    legendgroup="mean",
                    showlegend=(not mean_legend_shown),
                    hovertext=(
                        f"{model} · no_postmortem<br>"
                        f"mean={no_pm_mean:.3f}  SEM={no_pm_sem:.3f}  n={len(no_pm_ys)}"
                    ),
                    hoverinfo="text",
                )
            )
            mean_legend_shown = True
        if "learned" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=[learned_x],
                    y=[learned_mean],
                    mode="markers",
                    marker={
                        "symbol": "line-ew-open",
                        "size": 28,
                        "color": color,
                        "line": {"width": 3},
                    },
                    error_y={
                        "type": "data",
                        "array": [learned_sem],
                        "thickness": 2,
                        "width": 10,
                        "color": color,
                    },
                    name="cohort mean ± SEM",
                    legendgroup="mean",
                    showlegend=(not mean_legend_shown),
                    hovertext=(
                        f"{model} · learned<br>"
                        f"mean={learned_mean:.3f}  SEM={learned_sem:.3f}  n={len(rs)}"
                    ),
                    hoverinfo="text",
                )
            )
            mean_legend_shown = True
        if cross_ys and "cross_family" in selected_conditions:
            cross_mean = statistics.mean(cross_ys)
            cross_sem = (
                statistics.stdev(cross_ys) / math.sqrt(len(cross_ys)) if len(cross_ys) >= 2 else 0.0
            )
            observer_tag = cross_rs[0].cross_family_observer or "?"
            fig.add_trace(
                go.Scatter(
                    x=[cross_x],
                    y=[cross_mean],
                    mode="markers",
                    marker={
                        "symbol": "line-ew-open",
                        "size": 28,
                        "color": color,
                        "line": {"width": 3},
                    },
                    error_y={
                        "type": "data",
                        "array": [cross_sem],
                        "thickness": 2,
                        "width": 10,
                        "color": color,
                    },
                    name="cohort mean ± SEM",
                    legendgroup="mean",
                    showlegend=(not mean_legend_shown),
                    hovertext=(
                        f"{model} → {observer_tag} · cross_family<br>"
                        f"mean={cross_mean:.3f}  SEM={cross_sem:.3f}  n={len(cross_ys)}"
                    ),
                    hoverinfo="text",
                )
            )
            mean_legend_shown = True
    fig.update_layout(
        height=480,
        xaxis={
            "title": "model · condition",
            "tickmode": "array",
            "tickvals": tick_vals,
            "ticktext": tick_text,
            "range": [tick_vals[0] - 0.6, tick_vals[-1] + 0.6],
            "showgrid": False,
        },
        yaxis={"title": "round_success (rounds 16–25)", "range": [0, 1]},
        margin={"l": 60, "r": 20, "t": 30, "b": 60},
        legend={"orientation": "h", "y": 1.08, "x": 0.5, "xanchor": "center"},
    )
    st.plotly_chart(fig, width="stretch")


def _render_scatter(
    results: list[BaselineLearnability], frontend_base: str, selected_conditions: set[str]
) -> None:
    """Paired expected→learned dots per source, sorted by learned descending.

    The y-axis label concatenates the model short name; clicking a marker opens
    the source run in the frontend (``customdata`` carries the URL, handled by
    :func:`maybe_open_clicked_run`). Only the conditions in
    ``selected_conditions`` are drawn.
    """
    fig = go.Figure()
    ordered = sorted(results, key=lambda r: r.learned_mean, reverse=True)
    y_labels = [f"{r.src_id}  ({r.model_short} · b={r.budget})" for r in ordered]
    for r, label in zip(ordered, y_labels, strict=True):
        color = _MODEL_COLORS.get(r.model_short, "#777777")
        url = run_url(frontend_base=frontend_base, run_id=r.src_id)
        line_xs: list[float] = []
        if "expected" in selected_conditions:
            line_xs.append(r.expected_mean)
        if "expected_no_postmortem" in selected_conditions and r.n_expected_no_pm > 0:
            line_xs.append(r.expected_no_pm_mean)
        if "learned" in selected_conditions:
            line_xs.append(r.learned_mean)
        if "cross_family" in selected_conditions and r.n_cross_family > 0:
            line_xs.append(r.cross_family_mean)
        if len(line_xs) >= 2:
            fig.add_trace(
                go.Scatter(
                    x=sorted(line_xs),
                    y=[label] * len(line_xs),
                    mode="lines",
                    line={"color": color, "width": 1.5},
                    opacity=0.4,
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
        if "expected" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=[r.expected_mean],
                    y=[label],
                    mode="markers",
                    marker={
                        "symbol": "circle-open",
                        "size": 11,
                        "line": {"color": color, "width": 2},
                    },
                    name=f"{r.model_short} expected",
                    showlegend=False,
                    hovertemplate=(
                        f"{r.src_id} ({r.model_short} · b={r.budget})<br>"
                        f"expected={r.expected_mean:.3f} ± {r.expected_std:.3f} "
                        f"(n={r.n_expected} replicas)<br>"
                        "<i>click to open source run</i><extra></extra>"
                    ),
                    customdata=[url],
                )
            )
        if r.n_expected_no_pm > 0 and "expected_no_postmortem" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=[r.expected_no_pm_mean],
                    y=[label],
                    mode="markers",
                    marker={
                        "symbol": "triangle-up-open",
                        "size": 12,
                        "line": {"color": color, "width": 2},
                    },
                    name=f"{r.model_short} expected_no_postmortem",
                    showlegend=False,
                    hovertemplate=(
                        f"{r.src_id} ({r.model_short} · b={r.budget})<br>"
                        f"expected_no_postmortem={r.expected_no_pm_mean:.3f} "
                        f"± {r.expected_no_pm_std:.3f} "
                        f"(n={r.n_expected_no_pm} replicas)<br>"
                        f"Δ_postmortem={(r.expected_no_pm_mean - r.expected_mean):+.3f}<br>"
                        f"Δ_observer={(r.learned_mean - r.expected_no_pm_mean):+.3f}<br>"
                        "<i>click to open source run</i><extra></extra>"
                    ),
                    customdata=[url],
                )
            )
        if "learned" in selected_conditions:
            fig.add_trace(
                go.Scatter(
                    x=[r.learned_mean],
                    y=[label],
                    mode="markers",
                    marker={"symbol": "square", "size": 11, "color": color},
                    name=f"{r.model_short} learned",
                    showlegend=False,
                    hovertemplate=(
                        f"{r.src_id} ({r.model_short} · b={r.budget})<br>"
                        f"learned={r.learned_mean:.3f} ± {r.learned_std:.3f} "
                        f"(n={r.n_learned} replicas)<br>"
                        f"delta={r.delta:+.3f}<br>"
                        "<i>click to open source run</i><extra></extra>"
                    ),
                    customdata=[url],
                )
            )
        if r.n_cross_family > 0 and "cross_family" in selected_conditions:
            observer_color = _CROSS_FAMILY_OUTLINE_COLOR.get(
                r.cross_family_observer or "", "#777777"
            )
            delta_family = r.cross_family_mean - r.learned_mean
            fig.add_trace(
                go.Scatter(
                    x=[r.cross_family_mean],
                    y=[label],
                    mode="markers",
                    marker={
                        "symbol": "diamond-open",
                        "size": 13,
                        "line": {"color": observer_color, "width": 2},
                    },
                    name=f"{r.model_short} cross_family ({r.cross_family_observer})",
                    showlegend=False,
                    hovertemplate=(
                        f"{r.src_id} ({r.model_short} · b={r.budget})<br>"
                        f"cross_family={r.cross_family_mean:.3f} "
                        f"± {r.cross_family_std:.3f} "
                        f"(n={r.n_cross_family} replicas, observer={r.cross_family_observer})<br>"
                        f"Δ_family (cross − same) = {delta_family:+.3f}<br>"
                        "<i>click to open source run</i><extra></extra>"
                    ),
                    customdata=[url],
                )
            )
    symbol_legend = ", ".join(
        _CONDITION_SYMBOL_LABELS[key] for key in _CONDITION_KEYS if key in selected_conditions
    )
    fig.update_layout(
        height=max(360, 22 * len(y_labels) + 80),
        xaxis_title=f"round_success over rounds window  ({symbol_legend})",
        yaxis={"categoryorder": "array", "categoryarray": list(reversed(y_labels))},
        margin={"l": 260, "r": 20, "t": 30, "b": 40},
    )
    chart_event = st.plotly_chart(
        fig,
        width="stretch",
        on_select="rerun",
        selection_mode=("points",),
    )
    maybe_open_clicked_run(
        chart_event=chart_event, session_key="protocol_learnability_last_opened_url"
    )


def _render_feature_contrast_bars(rows: list, top_n: int) -> None:
    """Horizontal bar chart of feature gap (high − low), top ``top_n`` by ``|gap|``."""
    if not rows:
        st.info("Not enough baselines (or no feature_presence files) for contrast yet.")
        return
    top = rows[:top_n]
    features = [r.feature for r in top]
    gaps = [r.gap for r in top]
    colors = ["#2ca02c" if g >= 0 else "#d62728" for g in gaps]
    fig = go.Figure(
        data=go.Bar(
            x=gaps,
            y=features,
            orientation="h",
            marker={"color": colors},
            hovertemplate=(
                "%{y}<br>gap=%{x:+.3f}"
                "<br>high_mean=%{customdata[0]:.2f}  low_mean=%{customdata[1]:.2f}"
                "<extra></extra>"
            ),
            customdata=[[r.high_mean, r.low_mean] for r in top],
        )
    )
    fig.update_layout(
        height=max(380, 26 * len(top) + 80),
        xaxis_title="mean feature confidence: high-learnability − low-learnability",
        yaxis={"autorange": "reversed"},
        margin={"l": 280, "r": 20, "t": 20, "b": 40},
    )
    fig.add_vline(x=0, line_width=1, line_color="black")
    st.plotly_chart(fig, width="stretch", key="protocol_learnability_contrast_chart")


def _format_evidence_sample(sample: FeatureEvidenceSample) -> str:
    """Markdown line for one (confidence, run_id, model, justification) tuple."""
    return (
        f"**{sample.confidence:.2f} · `{sample.src_id}` ({sample.model_short})** — "
        f"{sample.justification or '_(no justification recorded)_'}"
    )


def _render_feature_evidence_block(evidence: FeatureEvidence, max_samples: int) -> None:
    """Markdown for one feature: description + top-tertile + bottom-tertile samples."""
    if evidence.description:
        st.markdown(f"_{evidence.description}_")
    else:
        st.caption("_(no ontology description for this category)_")
    st.markdown("**Top-tertile (high-learnability) baselines:**")
    if evidence.high_samples:
        for sample in evidence.high_samples[:max_samples]:
            st.markdown(_format_evidence_sample(sample=sample))
    else:
        st.caption("No samples in the top tertile for this feature.")
    st.markdown("**Bottom-tertile (low-learnability) baselines:**")
    if evidence.low_samples:
        for sample in evidence.low_samples[:max_samples]:
            st.markdown(_format_evidence_sample(sample=sample))
    else:
        st.caption("No samples in the bottom tertile for this feature.")


def _render_feature_contrast_explanation(tertile_fraction: float) -> None:
    """In-tab explanation of how the contrast values are calculated."""
    pct = int(tertile_fraction * 100)
    with st.expander("How are these values calculated?"):
        st.markdown(f"""
**Step 1 — split baselines into tertiles by `learned` score.**
For each baseline we have a `learned` mean (mean `round_success` over rounds 16-25 across
its 3 `phase=replace_learned` derived runs — fresh observer, link history only, no
postmortem). Baselines are sorted descending by that score, then split:

- **High tertile** = top **{pct}%** — protocols a fresh observer can pick up.
- **Low tertile** = bottom **{pct}%** — protocols the newcomer can't recover from the
  link transcript.
- Middle baselines are dropped on purpose — the contrast is between the extremes.

**Step 2 — read each baseline's feature-presence vector.**
For each tertile baseline we load `communication_feature_presence.json`. The file has a
`scores` list with one entry per category in the canon ontology (35 categories), each
carrying a `confidence` (0-1) for that feature in the baseline's link rounds 1-15.

**Step 3 — per-feature contrast.**
For each of the 35 categories:

- `high_mean` = mean `confidence` across the high-tertile baselines.
- `low_mean`  = mean `confidence` across the low-tertile baselines.
- `gap = high_mean − low_mean`.

Bars are sorted by `|gap|` (largest disagreement first). **Green** (`gap > 0`) means the
feature is more common in **transferable** protocols; **red** (`gap < 0`) means it's more
common in **idiosyncratic** ones.

**Caveats.**
The judge only sees the baseline's rounds 1-15 (protocol-development phase). It scores against
the fixed ontology — features the team invented but the ontology doesn't list are invisible.
Sources: [`protocol_learnability_data.py`](analysis/results_viewer/protocol_learnability_data.py)
(`_contrast_uncached`, `_feature_scores`).
            """.strip())


def _render_feature_contrast(
    runs_root: str,
    results: list[BaselineLearnability],
    tertile_fraction: float,
    rows: list,
    top_n: int,
) -> None:
    """Bar chart + per-feature expanders (description + tertile justifications)."""
    _render_feature_contrast_explanation(tertile_fraction=tertile_fraction)
    _render_feature_contrast_bars(rows=rows, top_n=top_n)
    if not rows:
        return

    descriptions = load_ontology_descriptions(runs_root=runs_root)
    st.markdown("---")
    st.markdown("### Feature descriptions and per-tertile evidence")
    st.caption(
        f"Up to 3 sample justifications per tertile from the top/bottom "
        f"{int(tertile_fraction * 100)}% of baselines by learned-mean."
    )
    for row in rows[:top_n]:
        header = (
            f"{row.feature}  ·  gap={row.gap:+.3f}  "
            f"(high={row.high_mean:.2f} / low={row.low_mean:.2f})"
        )
        with st.expander(header):
            if row.feature in descriptions:
                st.markdown(f"_{descriptions[row.feature]}_")
            else:
                st.caption("_(no ontology description for this category)_")
            evidence = feature_evidence(
                runs_root=runs_root,
                feature=row.feature,
                results=results,
                tertile_fraction=tertile_fraction,
            )
            _render_feature_evidence_block(evidence=evidence, max_samples=3)


def _render_model_summary(results: list[BaselineLearnability]) -> None:
    """Per-(model, budget) means underneath the filter so the cohort split is obvious."""
    by_cell: dict[tuple[str, str], list[BaselineLearnability]] = {}
    for r in results:
        by_cell.setdefault((r.model_short, r.budget), []).append(r)
    rows = []
    for model, budget in sorted(by_cell):
        rs = by_cell[(model, budget)]
        rows.append(
            {
                "model": model,
                "budget": budget,
                "n_baselines": len(rs),
                "expected_mean": round(statistics.mean(r.expected_mean for r in rs), 3),
                "learned_mean": round(statistics.mean(r.learned_mean for r in rs), 3),
                "delta_mean": round(statistics.mean(r.delta for r in rs), 3),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_empty_diagnostic(runs_dir: Path) -> None:
    """When ``load_results`` returns empty, surface what was scanned + why.

    Counts protocol_learnability-labelled runs by phase under ``runs_dir`` and
    prints a few labelled samples so the user can see whether the issue is
    "no runs labelled", "labelled but no eval reports", or "wrong runs_dir".
    """
    run_dirs = _iter_run_dirs(root=runs_dir)
    phases = {"phase=baseline": 0, "phase=resume_expected": 0, "phase=replace_learned": 0}
    by_src: dict[str, dict[str, int]] = {}
    sample_labels: list[str] = []
    for d in run_dirs:
        labels = _read_labels(run_dir=d)
        if "protocol_learnability" not in labels:
            continue
        for phase in phases:
            if phase in labels:
                phases[phase] += 1
        src = next((label[4:] for label in labels if label.startswith("src=")), None)
        if src is not None:
            phase_label = next((p for p in phases if p in labels), "?")
            by_src.setdefault(src, {p: 0 for p in phases})[phase_label] += 1
        if len(sample_labels) < 3:
            sample_labels.append(f"  {d.name}: {labels}")
    has_eval_reports = sum(
        1
        for d in run_dirs
        if (d / "veyru_report.json").exists() and "protocol_learnability" in _read_labels(run_dir=d)
    )
    st.warning(
        "No `protocol_learnability` baselines with both resume + replace derived runs "
        "found. Diagnostic below."
    )
    st.markdown("**Scan of `runs_dir`:**")
    st.code(
        f"runs_dir              = {runs_dir}\n"
        f"run_dirs scanned      = {len(run_dirs)}\n"
        f"labelled with         protocol_learnability = "
        f"{sum(1 for d in run_dirs if 'protocol_learnability' in _read_labels(run_dir=d))}\n"
        f"  phase=baseline           = {phases['phase=baseline']}\n"
        f"  phase=resume_expected    = {phases['phase=resume_expected']}\n"
        f"  phase=replace_learned    = {phases['phase=replace_learned']}\n"
        f"with veyru_report.json     = {has_eval_reports}\n"
        f"distinct src= values       = {len(by_src)}\n",
        language="text",
    )
    if sample_labels:
        st.markdown("**Sample labelled runs:**")
        st.code("\n".join(sample_labels), language="text")


def render(evaluated: list[EvaluatedRun], runs_dir: Path) -> None:
    """Render the "Protocol learnability" tab (replace-agent as a metric)."""
    del evaluated  # this tab walks runs_dir directly via labels.json
    st.markdown(
        "**Protocol learnability** — for every `protocol_learnability` baseline, "
        "compare the mean `round_success` over the post-resume comparison window "
        "across its 3 `resume_expected` runs (the intact team continued — "
        "*expected*) vs its 3 `replace_learned` runs (fresh same-model field "
        "observer with windowed link history and no postmortem — *learned*). "
        "Then contrast `communication_feature_presence` confidences between the "
        "top-tertile and bottom-tertile learners."
    )
    st.image(
        str(Path(__file__).parent / "agent-swap-as-metric.png"),
        caption="Method: replace-agent as a metric for protocol learnability",
        width="stretch",
    )
    with st.expander("What this experiment is, in plain English", expanded=False):
        st.markdown(
            "We selected 10 baseline runs of 15 rounds each, for three models — "
            "Claude Sonnet 4.6, Claude Opus 4.7, and GPT-5.4 — so 30 baseline runs in "
            "total. In each, a *field observer* and a *stabilization engineer* worked "
            "together on the comm link with a tight 250-character-per-round budget, plus "
            "a free-form team-discussion postmortem channel after every round. Over the "
            "15 rounds they developed a private communication protocol — shorthand, "
            "codes, compressed phrasings — to stay under budget.\n\n"
            "Then, for each baseline, we asked: **can a fresh field observer pick up "
            "that protocol just by reading the link transcript?** We tested this two "
            "ways, both extending the run by 10 more rounds (rounds 16–25, identical "
            "seed-42 cases so every condition faces the same problems).\n\n"
            "- **Expected** (3 resume runs) — we resumed the original team verbatim "
            "(same observer, same engineer, postmortem still open) and let them keep "
            "playing. This gives the *ceiling*: what the intact team naturally achieves "
            "on those 10 new rounds.\n"
            "- **Learned** (3 replace runs) — we swapped in a brand-new same-model "
            "field observer that had never seen this run, gave it only the previous "
            "10 rounds (5–14) of the link transcript (no postmortem history, no "
            "postmortem going forward), and let it play with the original engineer. "
            "This is where the *replace-agent feature becomes the metric* — performance "
            "here measures whether the protocol is self-explanatory from the link alone.\n\n"
            "That's 30 baselines + 90 resume + 90 replace = **210 runs**.\n\n"
            "For each baseline we compare the two means. A *small* gap means a fresh "
            "observer essentially matched the original team → the protocol is "
            "**transferable**. A *big* gap means the original team's performance "
            "depended on knowledge the newcomer couldn't recover from the transcript → "
            "the protocol is **idiosyncratic**.\n\n"
            "Finally, an LLM judge scored each baseline's link transcript against a "
            "35-category communication ontology (open-coded across all 30 baselines, "
            "then re-scored as a feature-presence vector). Splitting baselines into "
            "the top-third and bottom-third by *learned* score, the **Feature contrast** "
            "tab below shows which features are over-represented in the top third "
            "(ingredients of transferable protocols) vs the bottom third (what makes a "
            "protocol private).\n\n"
            "**Headline finding:** named-code / motif-tagging protocols transfer; "
            "subtractive-compression protocols don't. If the team gives each failure "
            'motif a stable symbolic name ("K", "DR", a specific token), a newcomer '
            "picks it up from context — every occurrence reinforces the mapping. If "
            "instead they compress by dropping vowels, omitting steps, or assuming "
            "shared context, the result is unreadable to anyone who wasn't there to "
            "build the shared ground."
        )

    host = st.text_input(
        label="Frontend base URL (for run links)",
        value=_DEFAULT_FRONTEND_HOST,
        key="protocol_learnability_frontend_host",
        help=(
            "Run links open at "
            "`<base>/g/" + _DEFAULT_GROUP_SLUG + "/runs/<scenario>/<run_dir_name>`."
        ),
    )
    frontend_base = f"{host.rstrip('/')}/g/{_DEFAULT_GROUP_SLUG}"

    all_results = load_results(runs_root=str(runs_dir), window_lo=_WINDOW_LO, window_hi=_WINDOW_HI)
    if not all_results:
        _render_empty_diagnostic(runs_dir=runs_dir)
        return

    available_models = sorted({r.model_short for r in all_results})
    selected_models = st.multiselect("Models", options=available_models, default=available_models)
    results = _filter_models(results=all_results, selected=set(selected_models))
    if not results:
        st.info("No baselines under the current model filter.")
        return

    st.subheader("Per-model summary")
    _render_model_summary(results=results)

    scatter_panel, contrast_panel = st.tabs(["Expected vs learned", "Feature contrast"])
    with scatter_panel:
        selected_conditions = _render_condition_checkboxes()
        if not selected_conditions:
            st.info("Select at least one condition to plot.")
        else:
            symbol_legend = ", ".join(
                _CONDITION_SYMBOL_LABELS[key]
                for key in _CONDITION_KEYS
                if key in selected_conditions
            )
            st.markdown(f"**Per-model means** ({symbol_legend}; error bars = SEM across baselines)")
            _render_per_model_bars(results=results, selected_conditions=selected_conditions)
            st.markdown("**Per-baseline** — click a marker to open the source run")
            _render_scatter(
                results=results,
                frontend_base=frontend_base,
                selected_conditions=selected_conditions,
            )
    with contrast_panel:
        contrast_rows = feature_contrast(
            runs_root=str(runs_dir),
            results=results,
            tertile_fraction=_TERTILE_FRACTION,
        )
        _render_feature_contrast(
            runs_root=str(runs_dir),
            results=results,
            tertile_fraction=_TERTILE_FRACTION,
            rows=contrast_rows,
            top_n=len(contrast_rows),
        )
