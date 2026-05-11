"""Streamlit "Language features" tab — three subtabs over communication_feature_presence.

Top of the tab carries four horizontal-checkbox cohort filters (model,
postmortem on/off, run kind, budget) plus a confidence-threshold
slider — the same idiom the Verbosity tab uses, so the two tabs feel
consistent. Below that, three subtabs:

* **Per-feature frequency** — for each ontology category, fraction of
  cohort runs whose confidence sits at or above the threshold. Bars
  sorted descending so the most-prevalent mechanisms read first.
* **Feature-conditioned outcomes** — pick a Group A category set and
  a Group B category set; show paired bars of mean in-team
  ``round_success`` for runs whose feature vector hits each group at
  the current threshold.
* **Per-run lookup** — pick one run; show its 19-category vector +
  the judge's justifications (ordered to match the bar chart) + a
  deep-link back to the schmidt frontend run viewer.
"""

import logging
import statistics
from typing import NamedTuple

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.feature_presence_data import (
    FEATURE_CLASS_PRESETS,
    ONTOLOGY_DEFAULT_DIR,
    FeaturePresenceRun,
    OntologyView,
    list_feature_presence_runs,
    resolve_ontology,
    runs_matching_feature_class,
)
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import render_frontend_base, run_url
from analysis.results_viewer.series_plot import render_horizontal_checkboxes

logger = logging.getLogger(__name__)

_KIND_BASELINE = "baseline"
_KIND_CROSS_TEAM = "cross-team"


def _kind_of(run: FeaturePresenceRun) -> str:
    """Bucket a run into one of the run-kind groups."""
    if run.cross_team_source_a_run_id is not None:
        return _KIND_CROSS_TEAM
    return _KIND_BASELINE


def _budget_of(run: FeaturePresenceRun) -> int | None:
    """Pull ``round_time_budget_seconds`` from the run's scenario_config."""
    value = run.scenario_config.get("round_time_budget_seconds")
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _postmortem_enabled_at_start(run: FeaturePresenceRun) -> bool:
    """Effective postmortem state at run start.

    ``postmortem_disabled_at_start`` is a cross-team / replace-agent knob
    that force-disables postmortem regardless of the underlying
    ``postmortem_enabled`` setting, so the effective bit is the
    conjunction of "scenario enables it" and "no override turning it off".
    """
    enabled = bool(run.scenario_config.get("postmortem_enabled", False))
    disabled_override = bool(run.scenario_config.get("postmortem_disabled_at_start", False))
    return enabled and not disabled_override


class _OutcomeStats(NamedTuple):
    """Summary statistics for one feature-group's outcome metric."""

    n: int
    mean: float
    std: float


def _make_outcome_stats(values: list[float]) -> _OutcomeStats:
    """Aggregate raw outcome floats into n/mean/std (std=0 when n<2)."""
    if not values:
        return _OutcomeStats(n=0, mean=0.0, std=0.0)
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return _OutcomeStats(n=len(values), mean=mean, std=std)


def _render_model_filter(runs: list[FeaturePresenceRun]) -> set[str]:
    """Horizontal checkboxes for each distinct primary model in the data."""
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.primary_model] = counts.get(run.primary_model, 0) + 1
    options = [(model, model, counts[model]) for model in sorted(counts)]
    return render_horizontal_checkboxes(
        title="Model",
        options=options,
        key_prefix="feature_presence_model_filter",
    )


def _render_postmortem_filter(runs: list[FeaturePresenceRun]) -> set[bool]:
    """Two checkboxes: effective postmortem on / off at run start."""
    counts = {True: 0, False: 0}
    for run in runs:
        counts[_postmortem_enabled_at_start(run=run)] += 1
    options = [
        ("postmortem", "with postmortem", counts[True]),
        ("no_postmortem", "no postmortem", counts[False]),
    ]
    options = [(k, lbl, c) for k, lbl, c in options if c > 0]
    selected_keys = render_horizontal_checkboxes(
        title="Postmortem",
        options=options,
        key_prefix="feature_presence_postmortem_filter",
    )
    selected: set[bool] = set()
    if "postmortem" in selected_keys:
        selected.add(True)
    if "no_postmortem" in selected_keys:
        selected.add(False)
    return selected


def _render_kind_filter(runs: list[FeaturePresenceRun]) -> set[str]:
    """Checkboxes for each distinct run kind (baseline vs cross-team-swap)."""
    counts: dict[str, int] = {}
    for run in runs:
        kind = _kind_of(run=run)
        counts[kind] = counts.get(kind, 0) + 1
    options = [(kind, kind, counts[kind]) for kind in sorted(counts)]
    return render_horizontal_checkboxes(
        title="Run kind",
        options=options,
        key_prefix="feature_presence_kind_filter",
    )


def _render_budget_filter(runs: list[FeaturePresenceRun]) -> set[int | None]:
    """Checkboxes for each distinct budget bucket; ``None`` shown as ``unknown``."""
    counts: dict[int | None, int] = {}
    for run in runs:
        budget = _budget_of(run=run)
        counts[budget] = counts.get(budget, 0) + 1
    if not counts:
        return set()
    sorted_keys = sorted(
        counts.keys(),
        key=lambda b: (b is None, b if b is not None else 0),
    )
    options = [
        (
            "unknown" if b is None else str(b),
            "unknown" if b is None else str(b),
            counts[b],
        )
        for b in sorted_keys
    ]
    selected_keys = render_horizontal_checkboxes(
        title="Budget per round",
        options=options,
        key_prefix="feature_presence_budget_filter",
    )
    selected: set[int | None] = set()
    for key in selected_keys:
        if key == "unknown":
            selected.add(None)
        else:
            selected.add(int(key))
    return selected


_FREQUENCY_JUSTIFICATION_SAMPLES = 10


def _render_frequency_section(
    runs: list[FeaturePresenceRun],
    ontology: OntologyView,
    threshold: float,
) -> None:
    """Section 1: bar chart of per-category presence fraction + sample justifications."""
    if not runs:
        st.info("No runs in the current cohort.")
        return
    rows: list[tuple[str, float, float, float]] = []
    for category in ontology.categories:
        values = [run.scores.get(category.id, 0.0) for run in runs]
        present = sum(1 for v in values if v >= threshold)
        fraction = present / len(values)
        mean = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0.0
        rows.append((category.id, fraction, mean, std))
    rows.sort(key=lambda r: -r[1])
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=[r[0] for r in rows],
            y=[r[1] for r in rows],
            hovertext=[
                f"{r[0]}<br>fraction ≥ {threshold:g}: {r[1]:.2%}<br>"
                f"mean: {r[2]:.2f} (std {r[3]:.2f})"
                for r in rows
            ],
            hoverinfo="text",
            marker={"color": "#5B8FF9"},
        )
    )
    fig.update_layout(
        yaxis={"title": f"Fraction of runs with confidence ≥ {threshold:g}", "range": [0, 1]},
        xaxis={"title": "Ontology category"},
        height=420,
        margin={"l": 40, "r": 20, "t": 20, "b": 120},
    )
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"n_cohort = {len(runs)} runs · ontology version `{ontology.version}`")

    st.markdown("### Justifications by category")
    st.caption(
        f"Up to {_FREQUENCY_JUSTIFICATION_SAMPLES} sample justifications per category, "
        "drawn from the highest-confidence cohort runs first."
    )
    for category_id, fraction, mean, std in rows:
        category_meta = ontology.by_id.get(category_id)
        header = (
            f"{category_id} — {fraction:.0%} of runs ≥ {threshold:g} "
            f"(mean {mean:.2f}, std {std:.2f})"
        )
        with st.expander(header):
            if category_meta is not None:
                st.markdown(f"_{category_meta.description}_")
            samples = sorted(
                (
                    (
                        run.scores.get(category_id, 0.0),
                        run.run_id,
                        run.justifications.get(category_id, ""),
                    )
                    for run in runs
                ),
                key=lambda entry: -entry[0],
            )
            shown = 0
            for confidence, run_id, justification in samples:
                if not justification:
                    continue
                st.markdown(f"**{confidence:.2f} · `{run_id}`** — {justification}")
                shown += 1
                if shown >= _FREQUENCY_JUSTIFICATION_SAMPLES:
                    break
            if shown == 0:
                st.caption("No justifications recorded for this category in the current cohort.")


def _render_feature_class_picker(
    label: str,
    ontology: OntologyView,
    preset_key: str,
    default_preset: str,
) -> set[str]:
    """Preset dropdown + multiselect for a feature class; returns the resolved ids."""
    available_ids = [cat.id for cat in ontology.categories]
    preset_options = ["(custom)"] + list(FEATURE_CLASS_PRESETS.keys())
    chosen_preset = st.selectbox(
        label=f"{label} preset",
        options=preset_options,
        index=preset_options.index(default_preset) if default_preset in preset_options else 0,
        key=f"{preset_key}_preset",
    )
    if chosen_preset == "(custom)":
        default_ids: list[str] = []
    else:
        default_ids = [
            cat_id for cat_id in FEATURE_CLASS_PRESETS[chosen_preset] if cat_id in available_ids
        ]
    chosen = st.multiselect(
        label=f"{label} categories",
        options=available_ids,
        default=default_ids,
        key=f"{preset_key}_categories",
    )
    return set(chosen)


def _add_paired_outcome_bars(
    fig: go.Figure,
    title: str,
    group_a: _OutcomeStats,
    group_b: _OutcomeStats,
) -> None:
    """Add A-vs-B mean bars with std error bars to ``fig``."""
    fig.add_trace(
        go.Bar(
            x=[f"Group A (n={group_a.n})", f"Group B (n={group_b.n})"],
            y=[group_a.mean, group_b.mean],
            error_y={
                "type": "data",
                "array": [group_a.std, group_b.std],
                "visible": True,
            },
            marker={"color": ["#5B8FF9", "#F6BD16"]},
            name=title,
        )
    )


def _render_outcomes_section(
    runs: list[FeaturePresenceRun],
    ontology: OntologyView,
    threshold: float,
) -> None:
    """Section 2: in-team ``round_success`` for Group A vs Group B feature-class cohorts."""
    if not runs:
        st.info("No runs in the current cohort.")
        return
    col_a, col_b = st.columns(2)
    with col_a:
        group_a_ids = _render_feature_class_picker(
            label="Group A",
            ontology=ontology,
            preset_key="feature_presence_group_a",
            default_preset="Abbreviation family",
        )
    with col_b:
        group_b_ids = _render_feature_class_picker(
            label="Group B",
            ontology=ontology,
            preset_key="feature_presence_group_b",
            default_preset="Arbitrary mapping family",
        )
    require_all = st.checkbox(
        label="Require all selected categories (default: any)",
        value=False,
        key="feature_presence_require_all",
    )

    if not group_a_ids or not group_b_ids:
        st.info("Pick at least one category for each group to render comparisons.")
        return

    cohort_a = runs_matching_feature_class(
        runs=runs,
        category_ids=group_a_ids,
        threshold=threshold,
        require_all=require_all,
    )
    cohort_b = runs_matching_feature_class(
        runs=runs,
        category_ids=group_b_ids,
        threshold=threshold,
        require_all=require_all,
    )

    in_team_a = _make_outcome_stats(
        values=[
            run.in_team_round_success for run in cohort_a if run.in_team_round_success is not None
        ]
    )
    in_team_b = _make_outcome_stats(
        values=[
            run.in_team_round_success for run in cohort_b if run.in_team_round_success is not None
        ]
    )

    st.markdown("**In-team `round_success`**")
    in_team_fig = go.Figure()
    _add_paired_outcome_bars(
        fig=in_team_fig, title="round_success", group_a=in_team_a, group_b=in_team_b
    )
    in_team_fig.update_layout(
        yaxis={"range": [0, 1], "title": "round_success"},
        showlegend=False,
        height=400,
        margin={"l": 40, "r": 20, "t": 20, "b": 40},
    )
    st.plotly_chart(in_team_fig, use_container_width=True)
    st.caption(_outcome_caption(group_a=in_team_a, group_b=in_team_b))


def _outcome_caption(group_a: _OutcomeStats, group_b: _OutcomeStats) -> str:
    """One-line caption summarizing the A-vs-B delta."""
    if group_a.n == 0 and group_b.n == 0:
        return "No qualifying runs."
    if group_a.n == 0:
        return f"Group A empty · B: n={group_b.n}, mean={group_b.mean:.3f}"
    if group_b.n == 0:
        return f"Group B empty · A: n={group_a.n}, mean={group_a.mean:.3f}"
    delta = group_a.mean - group_b.mean
    return (
        f"A: n={group_a.n}, mean={group_a.mean:.3f} · "
        f"B: n={group_b.n}, mean={group_b.mean:.3f} · Δ(A−B) = {delta:+.3f}"
    )


def _render_lookup_section(
    runs: list[FeaturePresenceRun],
    ontology: OntologyView,
    frontend_base: str,
) -> None:
    """Section 3: per-run inspector showing the full 19-category vector + justifications."""
    if not runs:
        st.info("No runs in the current cohort.")
        return
    sorted_runs = sorted(runs, key=lambda r: r.run_id, reverse=True)
    chosen = st.selectbox(
        label="Run",
        options=sorted_runs,
        format_func=_format_run_picker_option,
        key="feature_presence_run_picker",
    )
    if chosen is None:
        return
    st.markdown(
        f"[Open in run viewer]({run_url(frontend_base=frontend_base, run_id=chosen.run_id)})"
    )
    if chosen.in_team_round_success is not None:
        st.caption(f"round_success: {chosen.in_team_round_success:.3f}")
    if chosen.after_resume_round_success is not None:
        st.caption(f"round_success_after_resume: {chosen.after_resume_round_success:.3f}")
    if chosen.notes:
        st.markdown(f"**Judge notes:** {chosen.notes}")

    category_rows = sorted(
        ontology.categories,
        key=lambda cat: -chosen.scores.get(cat.id, 0.0),
    )
    fig = go.Figure(
        go.Bar(
            x=[chosen.scores.get(cat.id, 0.0) for cat in category_rows],
            y=[cat.id for cat in category_rows],
            orientation="h",
            marker={"color": "#5B8FF9"},
        )
    )
    fig.update_layout(
        xaxis={"range": [0, 1], "title": "Confidence"},
        yaxis={"autorange": "reversed"},
        height=max(360, 28 * len(category_rows)),
        margin={"l": 220, "r": 20, "t": 20, "b": 40},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Justifications")
    for cat in category_rows:
        confidence = chosen.scores.get(cat.id, 0.0)
        justification = chosen.justifications.get(cat.id, "")
        if not justification:
            continue
        with st.expander(f"{cat.id} — {confidence:.2f}"):
            st.markdown(f"_{cat.description}_")
            st.write(justification)


def _format_run_picker_option(run: FeaturePresenceRun) -> str:
    """Compact run-picker label: ``run_id (model) [labels]``."""
    label_suffix = f" [{', '.join(run.labels)}]" if run.labels else ""
    return f"{run.run_id} ({run.primary_model}){label_suffix}"


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the "Language features" tab end to end."""
    runs = list_feature_presence_runs(evaluated_runs=evaluated)
    if not runs:
        st.info(
            "No `communication_feature_presence.json` sidecars found. Run the "
            "communication-feature pipeline (`scripts/run_communication_pipeline.sh`) first."
        )
        return
    ontology = resolve_ontology(runs=runs, ontology_dir=ONTOLOGY_DEFAULT_DIR)
    if ontology is None:
        st.error(
            f"No ontology JSON found under `{ONTOLOGY_DEFAULT_DIR}`. Run the consolidation "
            "phase (`scripts/run_communication_pipeline.sh --phase 2`) first."
        )
        return
    versions = {run.ontology_version for run in runs}
    if len(versions) > 1:
        st.warning(
            f"Mixed ontology versions in sidecars: {sorted(versions)}. Showing categories from "
            f"`{ontology.version}`; runs scored against other versions may misalign."
        )
    frontend_base = render_frontend_base(streamlit_key="feature_presence_frontend_base")
    selected_models = _render_model_filter(runs=runs)
    selected_postmortem = _render_postmortem_filter(runs=runs)
    selected_kinds = _render_kind_filter(runs=runs)
    selected_budgets = _render_budget_filter(runs=runs)
    threshold = st.slider(
        label="Confidence threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.5,
        step=0.05,
        key="feature_presence_threshold",
    )
    if not selected_models:
        st.info("Select at least one model.")
        return
    if not selected_postmortem:
        st.info("Select at least one postmortem option.")
        return
    if not selected_kinds:
        st.info("Select at least one run kind.")
        return
    if not selected_budgets:
        st.info("Select at least one budget bucket.")
        return
    filtered_runs = [
        run
        for run in runs
        if run.primary_model in selected_models
        and _postmortem_enabled_at_start(run=run) in selected_postmortem
        and _kind_of(run=run) in selected_kinds
        and _budget_of(run=run) in selected_budgets
    ]
    st.caption(f"Cohort size: {len(filtered_runs)} / {len(runs)} runs match.")
    frequency_panel, outcomes_panel, lookup_panel = st.tabs(
        ["Per-feature frequency", "Feature-conditioned outcomes", "Per-run lookup"]
    )
    with frequency_panel:
        _render_frequency_section(runs=filtered_runs, ontology=ontology, threshold=threshold)
    with outcomes_panel:
        _render_outcomes_section(
            runs=filtered_runs,
            ontology=ontology,
            threshold=threshold,
        )
    with lookup_panel:
        _render_lookup_section(runs=filtered_runs, ontology=ontology, frontend_base=frontend_base)
