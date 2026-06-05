"""Streamlit "Language features" tab — three subtabs over communication_feature_presence.

Top of the tab carries four horizontal-checkbox cohort filters (model,
postmortem on/off, run kind, budget) plus two threshold sliders:
``Confidence threshold`` (binarizes per-category confidence into
present/absent) and ``Round-success threshold`` (drops cohort runs
whose ``round_success`` is below the cutoff or missing). Every subtab
renders over the post-filter cohort, so the displayed signal always
reads as "among winning runs that match the metadata filters". Three
subtabs:

* **Per-feature frequency** — for each ontology category, bar = fraction
  of cohort runs whose confidence is ≥ the confidence threshold. Bars
  sorted descending; sample justifications expand below.
* **Feature-conditioned outcomes** — pick a Group A category set and
  a Group B category set; bars show the fraction of cohort runs whose
  feature vector hits each group at the confidence threshold (i.e.
  share of winners that developed each feature class).
* **Per-run lookup** — pick one run; horizontal bar chart of its
  19-category vector with bars coloured by the confidence threshold,
  vertical dashed line at the threshold, win/loss caption from the
  success threshold, and the judge's justifications (ordered to match
  the bar chart) + deep-link to the run viewer.
* **Knob correlation** — pick one ontology category; line plot of how
  often that feature emerges as a function of the per-round budget
  (X axis), split into one line for postmortem-enabled runs and one for
  postmortem-disabled runs. Y = fraction of bucket runs whose confidence
  is ≥ the confidence threshold. This subtab renders over the
  metadata-filtered cohort *before* the round-success drop, so the
  signal reads as "how often the knob setting produces this feature",
  independent of round success.
"""

import logging
import statistics
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer import judge_replay_filter, seed_mode_filter
from analysis.results_viewer.feature_presence_data import (
    FeaturePresenceRun,
    OntologyView,
    list_feature_presence_runs,
    resolve_ontology,
    runs_matching_feature_class,
)
from analysis.results_viewer.natural_sort import natural_sort_key
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import render_frontend_base, run_url
from analysis.results_viewer.scenario_selector import default_scenario_index
from analysis.results_viewer.series_plot import render_horizontal_checkboxes
from schmidt.evaluation.metrics.communication.label_models import ontology_dir_for_scenario

logger = logging.getLogger(__name__)

_KIND_BASELINE = "baseline"
_KIND_CROSS_TEAM = "cross-team"


def _kind_of(run: FeaturePresenceRun) -> str:
    """Bucket a run into one of the run-kind groups."""
    if run.cross_team_source_a_run_id is not None:
        return _KIND_CROSS_TEAM
    return _KIND_BASELINE


def _budget_of(run: FeaturePresenceRun) -> int | None:
    """Pull the per-round time budget from the run's scenario_config.

    ``round_time_budget_seconds`` is the canonical knob on ``BaseKnobs``
    surfaced by every budget-bearing scenario. Returns ``None`` when the
    scenario has no per-round budget (e.g. Salon).
    """
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
        initial_state=True,
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
        initial_state=True,
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
        initial_state=True,
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
        initial_state=True,
    )
    selected: set[int | None] = set()
    for key in selected_keys:
        if key == "unknown":
            selected.add(None)
        else:
            selected.add(int(key))
    return selected


_FREQUENCY_JUSTIFICATION_SAMPLES = 10
_WIN_COLOR = "#5B8FF9"


def _render_frequency_section(
    runs: list[FeaturePresenceRun],
    ontology: OntologyView,
    threshold: float,
) -> None:
    """Section 1: bar chart of per-category presence fraction + sample justifications.

    The cohort is already filtered upstream by the success threshold,
    so every run shown here meets the success bar. Bars read directly
    as "fraction of qualifying runs that exhibit this mechanism".
    """
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
            marker={"color": _WIN_COLOR},
        )
    )
    fig.update_layout(
        yaxis={"title": f"Fraction of runs with confidence ≥ {threshold:g}", "range": [0, 1]},
        xaxis={"title": "Ontology category"},
        height=420,
        margin={"l": 40, "r": 20, "t": 20, "b": 120},
    )
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, width="stretch")
    st.caption(f"n_cohort = {len(runs)} runs · ontology version `{ontology.version}`")

    _render_justifications_by_category(
        runs=runs,
        ontology=ontology,
        category_summaries=[
            (row[0], _frequency_expander_header(row=row, threshold=threshold)) for row in rows
        ],
    )


def _frequency_expander_header(
    row: tuple[str, float, float, float],
    threshold: float,
) -> str:
    """Header line for one category's justifications expander in the frequency view."""
    category_id, fraction, mean, std = row
    return (
        f"{category_id} — {fraction:.0%} of runs ≥ {threshold:g} "
        f"(mean {mean:.2f}, std {std:.2f})"
    )


def _render_justifications_by_category(
    runs: list[FeaturePresenceRun],
    ontology: OntologyView,
    category_summaries: list[tuple[str, str]],
) -> None:
    """Render a `Justifications by category` section over ``category_summaries``.

    Each ``(category_id, header)`` pair becomes one expander showing
    the category's ontology description plus up to
    ``_FREQUENCY_JUSTIFICATION_SAMPLES`` runs' justifications sorted by
    descending confidence on that category.
    """
    if not category_summaries:
        return
    st.markdown("### Justifications by category")
    st.caption(
        f"Up to {_FREQUENCY_JUSTIFICATION_SAMPLES} sample justifications per category, "
        "drawn from the highest-confidence cohort runs first."
    )
    for category_id, header in category_summaries:
        category_meta = ontology.by_id.get(category_id)
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
    key_prefix: str,
) -> set[str]:
    """Multiselect of ontology categories for a feature class; returns the chosen ids."""
    available_ids = sorted((cat.id for cat in ontology.categories), key=natural_sort_key)
    chosen = st.multiselect(
        label=f"{label} categories",
        options=available_ids,
        default=[],
        key=f"{key_prefix}_categories",
        help=(
            "Each category is one mechanism from the ontology. Pick any subset; "
            "a run hits the group if its confidence on any (or all) of these "
            "is >= the confidence threshold."
        ),
    )
    return set(chosen)


def _render_outcomes_section(
    runs: list[FeaturePresenceRun],
    ontology: OntologyView,
    threshold: float,
    success_threshold: float,
) -> None:
    """Section 2: feature-class prevalence within the winners-only cohort.

    Bars show the fraction of cohort runs whose feature vector hits
    Group A vs Group B at the confidence threshold. Since the cohort is
    pre-filtered by the success threshold, this reads as "share of
    winning runs that developed each feature class".
    """
    if not runs:
        st.info("No runs in the current cohort.")
        return
    col_a, col_b = st.columns(2)
    with col_a:
        group_a_ids = _render_feature_class_picker(
            label="Group A",
            ontology=ontology,
            key_prefix="feature_presence_group_a",
        )
    with col_b:
        group_b_ids = _render_feature_class_picker(
            label="Group B",
            ontology=ontology,
            key_prefix="feature_presence_group_b",
        )
    require_all = st.checkbox(
        label="Require all selected categories (default: any)",
        value=False,
        key="feature_presence_require_all",
    )

    if group_a_ids and group_b_ids:
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
        fraction_a = len(cohort_a) / len(runs)
        fraction_b = len(cohort_b) / len(runs)

        st.markdown(
            f"**Feature-class prevalence among winners** "
            f"(round_success ≥ {success_threshold:g}, n_cohort = {len(runs)})"
        )
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=[f"Group A (n={len(cohort_a)})", f"Group B (n={len(cohort_b)})"],
                y=[fraction_a, fraction_b],
                marker={"color": ["#5B8FF9", "#F6BD16"]},
            )
        )
        fig.update_layout(
            yaxis={
                "range": [0, 1],
                "title": "fraction of cohort exhibiting the group",
            },
            showlegend=False,
            height=400,
            margin={"l": 40, "r": 20, "t": 20, "b": 40},
        )
        st.plotly_chart(fig, width="stretch")
        st.caption(
            f"A: {fraction_a:.2%} ({len(cohort_a)}/{len(runs)}) · "
            f"B: {fraction_b:.2%} ({len(cohort_b)}/{len(runs)}) · "
            f"Δ(A−B) = {fraction_a - fraction_b:+.2%}"
        )
    else:
        st.caption("Bar comparison hidden — pick categories for both groups to compare them.")

    sorted_category_ids = sorted(
        (cat.id for cat in ontology.categories),
        key=natural_sort_key,
    )
    _render_justifications_by_category(
        runs=runs,
        ontology=ontology,
        category_summaries=[
            (
                category_id,
                _outcomes_expander_header(
                    category_id=category_id,
                    group_labels=_groups_containing(
                        category_id=category_id,
                        group_a_ids=group_a_ids,
                        group_b_ids=group_b_ids,
                    ),
                    runs=runs,
                    threshold=threshold,
                ),
            )
            for category_id in sorted_category_ids
        ],
    )


def _groups_containing(
    category_id: str,
    group_a_ids: set[str],
    group_b_ids: set[str],
) -> str:
    """Tag for which groups a category is part of (``A``, ``B``, ``A + B``, or empty)."""
    in_a = category_id in group_a_ids
    in_b = category_id in group_b_ids
    if in_a and in_b:
        return "A + B"
    if in_a:
        return "A"
    if in_b:
        return "B"
    return ""


def _outcomes_expander_header(
    category_id: str,
    group_labels: str,
    runs: list[FeaturePresenceRun],
    threshold: float,
) -> str:
    """Header line for one category's justifications expander in the outcomes view."""
    values = [run.scores.get(category_id, 0.0) for run in runs]
    present = sum(1 for v in values if v >= threshold)
    fraction = present / len(values) if values else 0.0
    group_tag = f" [Group {group_labels}]" if group_labels else ""
    return f"{category_id}{group_tag} — {fraction:.0%} of runs ≥ {threshold:g}"


def _render_lookup_section(
    runs: list[FeaturePresenceRun],
    ontology: OntologyView,
    frontend_base: str,
    threshold: float,
    success_threshold: float,
) -> None:
    """Section 3: per-run inspector showing the full 19-category vector + justifications.

    The bar chart marks the confidence threshold with a vertical line so
    it's obvious which categories the run is considered to exhibit. The
    header row tags the run as a win/loss based on the success threshold.
    """
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
    if chosen is None:  # pyright: ignore[reportUnnecessaryComparison]
        return
    st.markdown(
        f"[Open in run viewer]({run_url(frontend_base=frontend_base, run_id=chosen.run_id)})"
    )
    if chosen.in_team_round_success is not None:
        verdict = "Win" if chosen.in_team_round_success >= success_threshold else "Loss"
        st.caption(
            f"round_success: {chosen.in_team_round_success:.3f} → **{verdict}** "
            f"(threshold {success_threshold:g})"
        )
    if chosen.after_resume_round_success is not None:
        st.caption(f"round_success_after_resume: {chosen.after_resume_round_success:.3f}")
    if chosen.notes:
        st.markdown(f"**Judge notes:** {chosen.notes}")

    category_rows = sorted(
        ontology.categories,
        key=lambda cat: -chosen.scores.get(cat.id, 0.0),
    )
    bar_colors = [
        _WIN_COLOR if chosen.scores.get(cat.id, 0.0) >= threshold else "#B0BEC5"
        for cat in category_rows
    ]
    fig = go.Figure(
        go.Bar(
            x=[chosen.scores.get(cat.id, 0.0) for cat in category_rows],
            y=[cat.id for cat in category_rows],
            orientation="h",
            marker={"color": bar_colors},
        )
    )
    fig.add_vline(
        x=threshold,
        line_dash="dash",
        line_color="#444",
        annotation_text=f"threshold {threshold:g}",
        annotation_position="top right",
    )
    fig.update_layout(
        xaxis={"range": [0, 1], "title": "Confidence"},
        yaxis={"autorange": "reversed"},
        height=max(360, 28 * len(category_rows)),
        margin={"l": 220, "r": 20, "t": 20, "b": 40},
    )
    st.plotly_chart(fig, width="stretch")

    st.markdown("### Justifications")
    for cat in category_rows:
        confidence = chosen.scores.get(cat.id, 0.0)
        justification = chosen.justifications.get(cat.id, "")
        if not justification:
            continue
        with st.expander(f"{cat.id} — {confidence:.2f}"):
            st.markdown(f"_{cat.description}_")
            st.write(justification)


_POSTMORTEM_LINE_COLOR = "#F6BD16"
_NO_POSTMORTEM_LINE_COLOR = _WIN_COLOR


def _feature_presence_rate(
    runs: list[FeaturePresenceRun],
    category_id: str,
    threshold: float,
) -> tuple[int, int]:
    """Return ``(present, total)`` runs whose confidence on ``category_id`` is ≥ ``threshold``."""
    present = sum(1 for run in runs if run.scores.get(category_id, 0.0) >= threshold)
    return (present, len(runs))


def _render_knob_correlation_section(
    runs: list[FeaturePresenceRun],
    ontology: OntologyView,
    threshold: float,
) -> None:
    """Section 4: feature emergence vs round budget, split by postmortem on/off.

    The cohort here is the metadata-filtered list *before* the success
    threshold is applied, so the plot reads as "how often this feature
    emerges under each knob setting", independent of whether the run
    succeeded. X = round time budget; one line per postmortem state;
    Y = fraction of bucket runs whose confidence on the picked category
    is ≥ the confidence threshold.
    """
    if not runs:
        st.info("No runs in the current cohort.")
        return
    category_ids = sorted((cat.id for cat in ontology.categories), key=natural_sort_key)
    category_id = st.selectbox(
        label="Language feature",
        options=category_ids,
        key="feature_presence_knob_feature",
    )
    if category_id is None:  # pyright: ignore[reportUnnecessaryComparison]
        return
    category_meta = ontology.by_id.get(category_id)
    if category_meta is not None:
        st.caption(category_meta.description)

    budgeted_runs: list[tuple[FeaturePresenceRun, int]] = []
    for run in runs:
        budget = _budget_of(run=run)
        if budget is not None:
            budgeted_runs.append((run, budget))
    if not budgeted_runs:
        st.info("No runs in the cohort carry a per-round budget (`round_time_budget_seconds`).")
        return

    budget_order = [str(budget) for budget in sorted({budget for _, budget in budgeted_runs})]
    line_specs = [
        (True, "with postmortem", _POSTMORTEM_LINE_COLOR),
        (False, "no postmortem", _NO_POSTMORTEM_LINE_COLOR),
    ]
    fig = go.Figure()
    per_line_counts: dict[str, int] = {}
    for pm_state, label, color in line_specs:
        state_runs = [
            (run, budget)
            for run, budget in budgeted_runs
            if _postmortem_enabled_at_start(run=run) == pm_state
        ]
        per_line_counts[label] = len(state_runs)
        if not state_runs:
            continue
        budgets = sorted({budget for _, budget in state_runs})
        xs: list[str] = []
        ys: list[float] = []
        hovertext: list[str] = []
        for budget in budgets:
            bucket = [run for run, run_budget in state_runs if run_budget == budget]
            present, total = _feature_presence_rate(
                runs=bucket, category_id=category_id, threshold=threshold
            )
            fraction = present / total
            xs.append(str(budget))
            ys.append(fraction)
            hovertext.append(f"{label}<br>budget {budget}<br>{fraction:.0%} ({present}/{total})")
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                name=label,
                marker={"color": color},
                line={"color": color},
                hovertext=hovertext,
                hoverinfo="text",
            )
        )
    fig.update_layout(
        xaxis={
            "title": "Round time budget (seconds)",
            "type": "category",
            "categoryorder": "array",
            "categoryarray": budget_order,
        },
        yaxis={
            "title": f"% of runs with confidence ≥ {threshold:g}",
            "range": [0, 1],
            "tickformat": ".0%",
        },
        height=420,
        margin={"l": 40, "r": 20, "t": 20, "b": 60},
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"n_cohort = {len(budgeted_runs)} runs · "
        f"with-postmortem n={per_line_counts['with postmortem']} · "
        f"no-postmortem n={per_line_counts['no postmortem']} · "
        "round-success threshold intentionally not applied in this view."
    )


def _format_run_picker_option(run: FeaturePresenceRun) -> str:
    """Compact run-picker label: ``run_id (model) [labels]``."""
    label_suffix = f" [{', '.join(run.labels)}]" if run.labels else ""
    return f"{run.run_id} ({run.primary_model}){label_suffix}"


def render(evaluated: list[EvaluatedRun], runs_dir: Path) -> None:
    """Render the "Language features" tab end to end."""
    ratio_map = judge_replay_filter.flip_ratio_by_run_id(evaluated=evaluated)
    run_filter = seed_mode_filter.render_filters(key_prefix="feature_presence")
    evaluated = seed_mode_filter.apply(evaluated=evaluated, run_filter=run_filter)
    all_runs = list_feature_presence_runs(evaluated_runs=evaluated)
    if not all_runs:
        st.info(
            "No `communication_feature_presence.json` sidecars found. Run the "
            "communication-feature pipeline (`scripts/run_communication_pipeline.sh "
            "--scenario <name>`) first."
        )
        return
    scenario_counts: dict[str, int] = {}
    for run in all_runs:
        scenario_counts[run.scenario_name] = scenario_counts.get(run.scenario_name, 0) + 1
    scenario_options = sorted(scenario_counts.keys())
    selected_scenario = st.radio(
        label="Scenario",
        options=scenario_options,
        index=default_scenario_index(options=scenario_options),
        format_func=lambda name: f"{name} ({scenario_counts[name]} runs)",
        key="feature_presence_scenario",
        horizontal=True,
    )
    if selected_scenario is None:  # pyright: ignore[reportUnnecessaryComparison]
        st.info("Select a scenario.")
        return
    runs = [run for run in all_runs if run.scenario_name == selected_scenario]
    if not runs:
        st.info(f"No feature-presence sidecars found for scenario `{selected_scenario}`.")
        return
    ontology = resolve_ontology(
        runs=runs,
        scenario_name=selected_scenario,
        runs_dir=runs_dir,
    )
    if ontology is None:
        scenario_ontology_dir = ontology_dir_for_scenario(
            runs_dir=runs_dir, scenario_name=selected_scenario
        )
        st.error(
            f"No ontology JSON found under `{scenario_ontology_dir}`. "
            f"Run the consolidation phase "
            f"(`scripts/run_communication_pipeline.sh --scenario {selected_scenario} --phase 2`) "
            "first."
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
    threshold_cols = st.columns(2)
    with threshold_cols[0]:
        threshold = st.slider(
            label="Confidence threshold",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            key="feature_presence_threshold",
            help=(
                "Cutoff for the per-category confidence score. A run counts as "
                "exhibiting a category when its confidence is >= this value."
            ),
        )
    with threshold_cols[1]:
        success_threshold = st.slider(
            label="Round-success threshold",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            key="feature_presence_success_threshold",
            help=(
                "Cohort filter: drop runs whose round_success is below this "
                "value (and runs with no round_success score). Every subtab "
                "renders over the surviving cohort, so the per-feature "
                "frequency reads as 'fraction of winning runs that exhibit "
                "this mechanism'."
            ),
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
    metadata_filtered = [
        run
        for run in runs
        if run.primary_model in selected_models
        and _postmortem_enabled_at_start(run=run) in selected_postmortem
        and _kind_of(run=run) in selected_kinds
        and _budget_of(run=run) in selected_budgets
    ]
    filtered_runs = [
        run
        for run in metadata_filtered
        if run.in_team_round_success is not None and run.in_team_round_success >= success_threshold
    ]
    excluded = len(metadata_filtered) - len(filtered_runs)
    st.caption(
        f"Cohort size: {len(filtered_runs)} / {len(runs)} runs match "
        f"(metadata-pass: {len(metadata_filtered)}; "
        f"dropped {excluded} below round_success {success_threshold:g})."
    )
    filtered_runs = judge_replay_filter.render_and_filter(
        items=filtered_runs,
        ratio_of=lambda r: ratio_map.get(r.run_id),
        key="feature_presence",
        item_label="language-feature runs",
    )
    if not filtered_runs:
        st.info("All runs filtered out by judge-replay slider.")
        return
    frequency_panel, outcomes_panel, lookup_panel, knob_panel = st.tabs(
        [
            "Per-feature frequency",
            "Feature-conditioned outcomes",
            "Per-run lookup",
            "Knob correlation",
        ]
    )
    with frequency_panel:
        _render_frequency_section(
            runs=filtered_runs,
            ontology=ontology,
            threshold=threshold,
        )
    with outcomes_panel:
        _render_outcomes_section(
            runs=filtered_runs,
            ontology=ontology,
            threshold=threshold,
            success_threshold=success_threshold,
        )
    with lookup_panel:
        _render_lookup_section(
            runs=filtered_runs,
            ontology=ontology,
            frontend_base=frontend_base,
            threshold=threshold,
            success_threshold=success_threshold,
        )
    with knob_panel:
        _render_knob_correlation_section(
            runs=metadata_filtered,
            ontology=ontology,
            threshold=threshold,
        )
