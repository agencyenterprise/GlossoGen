"""Streamlit tab visualising in-run agent swaps.

Two subtabs:

- **Per-run**: bar chart of round-success per phase for one selected run, with
  per-round green/red strip and a phase breakdown table.
- **Cohort overlay**: aggregate label-defined cohorts on a shared per-round
  success curve and per-phase probe-similarity chart. Multi-swap experiment
  cohorts pair automatically with their matching no-swap baseline (same budget,
  same postmortem schedule); baselines render as dashed lines that share the
  experiment colour for direct visual comparison.
"""

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import NamedTuple

import plotly.graph_objects as go
import streamlit as st
from rapidfuzz.distance import Levenshtein

from analysis.results_viewer import seed_mode_filter
from analysis.results_viewer.multi_swap_data import MultiSwapRun, PhaseScore, list_multi_swap_runs
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import maybe_open_clicked_run, render_frontend_base, run_url

_REPLICA_DOT_OPACITY = 0.35
_REPLICA_DOT_SIZE = 6
_REPLICA_JITTER_AMPLITUDE_ROUND = 0.18
_REPLICA_JITTER_AMPLITUDE_PHASE = 0.04
_PHASE_BAR_COLOR = "#4F46E5"
_DELTA_POSITIVE_COLOR = "#15803D"
_DELTA_NEGATIVE_COLOR = "#B91C1C"
_DELTA_ZERO_COLOR = "#475569"
_COHORT_PALETTE = ["#1E40AF", "#B91C1C", "#15803D", "#7C3AED", "#EA580C"]
_BASELINE_DOT_PALETTE = ["#93C5FD", "#FCA5A5", "#86EFAC", "#C4B5FD", "#FED7AA"]
_BASELINE_FALLBACK_COLOR = "#737373"
_BASELINE_DOT_FALLBACK_COLOR = "#D1D5DB"
_DOTS_VISIBLE = "Show"
_DOTS_HIDDEN = "Hide"
_PHASE_BY_CUTOFF = {11: "A", 21: "B", 31: "C", 41: "D"}
_PHASE_ORDER = ["A", "B", "C", "D"]
_PM_SCHEDULE_ALWAYS = "pm_always"
_PM_SCHEDULE_PHASE_A_ONLY = "pm_phase_a_only"
_EXPERIMENT_TYPE_MULTI_SWAP = "multi_swap"
_EXPERIMENT_TYPE_NO_SWAP_BASELINE = "no_swap_baseline"
_VIEW_PER_ROUND = "Per round"
_VIEW_PER_PHASE = "Per phase"
_BUDGET_SPLIT = "Split by budget"
_BUDGET_MERGE = "Merge across budgets"


class _CohortPairKey(NamedTuple):
    """Identifies a (budget, postmortem schedule) experiment cell.

    A multi-swap cohort and its matching no-swap baseline share the same
    pair-key so they can be coloured identically in the overlay charts.
    """

    budget: str
    pm_schedule: str


class _MergeKey(NamedTuple):
    """Budget-independent grouping key used in merge-across-budgets mode."""

    experiment_type: str
    pm_schedule: str


class _ColorPairKey(NamedTuple):
    """Identifies the colour-sharing pair (one experiment + one baseline).

    In split-by-budget mode this includes the budget; in merge-across-budgets
    mode the budget is the empty string so cohorts pooled across budgets share
    a colour with their matching baseline pool.
    """

    budget: str
    pm_schedule: str


class _EffectiveCohort(NamedTuple):
    """A cohort to actually plot. May pool multiple label-sets (e.g. all budgets)."""

    display: str
    contributing_label_sets: list[frozenset[str]]
    is_baseline: bool
    color_pair_key: _ColorPairKey


class _RunRoundEntry(NamedTuple):
    """One run's per-round success outcomes plus its identity for clickable dots."""

    success: dict[int, bool]
    run_id: str
    url: str


class _RunProbeEntry(NamedTuple):
    """One run's per-phase probe drift plus its identity for clickable dots."""

    drift: dict[str, float]
    run_id: str
    url: str


class _CohortRoundSeries(NamedTuple):
    """Per-round success data for one cohort, plus styling metadata."""

    display: str
    runs: list[_RunRoundEntry]
    is_baseline: bool
    color: str


class _CohortProbeSeries(NamedTuple):
    """Per-phase probe drift data for one cohort, plus styling metadata."""

    display: str
    runs: list[_RunProbeEntry]
    is_baseline: bool
    color: str


def _format_swap_text(phase: PhaseScore, multi_swap: MultiSwapRun) -> str:
    """One-line description of who swapped at the boundary opening this phase."""
    if phase.swap is None:
        agent_models = ", ".join(
            f"{agent_id}={model}"
            for agent_id, model in sorted(multi_swap.initial_agent_models.items())
        )
        return f"initial agents: {agent_models}"
    return (
        f"swapped {phase.swap.agent_id} → {phase.swap.new_model} "
        f"({phase.swap.new_provider}) at round {phase.swap.round_number}"
    )


def _delta_label(current: PhaseScore, previous: PhaseScore | None) -> str:
    """Δ pp from previous phase to current; empty string when no previous phase."""
    if previous is None:
        return ""
    delta_pp = round((current.score - previous.score) * 100)
    if delta_pp > 0:
        return f"+{delta_pp} pp"
    if delta_pp < 0:
        return f"{delta_pp} pp"
    return "0 pp"


def _delta_color(current: PhaseScore, previous: PhaseScore | None) -> str:
    """Annotation colour based on whether the phase improved over the previous."""
    if previous is None:
        return _DELTA_ZERO_COLOR
    delta = current.score - previous.score
    if delta > 0:
        return _DELTA_POSITIVE_COLOR
    if delta < 0:
        return _DELTA_NEGATIVE_COLOR
    return _DELTA_ZERO_COLOR


def _build_phase_chart(multi_swap: MultiSwapRun) -> go.Figure:
    """One Plotly bar chart with phases on X and round_success on Y."""
    phases = multi_swap.phases
    bar_x = [phase.label for phase in phases]
    bar_y = [phase.score for phase in phases]
    bar_text = [f"{phase.won}/{phase.total}<br>({round(phase.score * 100)}%)" for phase in phases]
    hover_text = [
        f"{phase.label}<br>Rounds {phase.round_start}–{phase.round_end}<br>"
        f"{_format_swap_text(phase=phase, multi_swap=multi_swap)}<br>"
        f"Score: {phase.won}/{phase.total} ({round(phase.score * 100)}%)"
        for phase in phases
    ]

    fig = go.Figure(
        data=[
            go.Bar(
                x=bar_x,
                y=bar_y,
                text=bar_text,
                textposition="inside",
                marker_color=_PHASE_BAR_COLOR,
                hovertext=hover_text,
                hoverinfo="text",
                name="Phase score",
            )
        ]
    )
    for index, phase in enumerate(phases):
        previous = phases[index - 1] if index > 0 else None
        delta_text = _delta_label(current=phase, previous=previous)
        if not delta_text:
            continue
        fig.add_annotation(
            x=phase.label,
            y=phase.score,
            yshift=24,
            text=f"<b>{delta_text}</b>",
            showarrow=False,
            font=dict(color=_delta_color(current=phase, previous=previous), size=13),
        )
    fig.update_layout(
        title=f"Round-success per phase — {multi_swap.run_id}",
        xaxis_title="Phase",
        yaxis_title="Fraction of phase rounds stabilized",
        yaxis=dict(range=[0.0, 1.05], tickformat=".0%"),
        height=440,
        margin=dict(t=70, b=40, l=60, r=20),
        showlegend=False,
    )
    return fig


def _render_phase_table(multi_swap: MultiSwapRun) -> None:
    """Tabular breakdown matching the bar chart, including round outcomes."""
    rows = []
    previous: PhaseScore | None = None
    for phase in multi_swap.phases:
        rows.append(
            {
                "Phase": phase.label,
                "Rounds": f"{phase.round_start}–{phase.round_end}",
                "Boundary event": _format_swap_text(phase=phase, multi_swap=multi_swap),
                "Score": f"{phase.won}/{phase.total} ({round(phase.score * 100)}%)",
                "Δ vs prev": _delta_label(current=phase, previous=previous),
            }
        )
        previous = phase
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_round_strip(multi_swap: MultiSwapRun) -> None:
    """Compact per-round green/red strip across all phases for at-a-glance reading."""
    phase_outcomes = []
    for phase in multi_swap.phases:
        for round_number in sorted(phase.round_outcomes):
            phase_outcomes.append(
                {
                    "round": round_number,
                    "phase": phase.label,
                    "won": phase.round_outcomes[round_number],
                }
            )
    if not phase_outcomes:
        return
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=[entry["round"] for entry in phase_outcomes],
            y=[1 for _ in phase_outcomes],
            marker_color=["#15803D" if entry["won"] else "#B91C1C" for entry in phase_outcomes],
            hovertext=[
                f"Round {entry['round']} — {entry['phase']} — "
                f"{'stabilized' if entry['won'] else 'lost'}"
                for entry in phase_outcomes
            ],
            hoverinfo="text",
            name="round outcome",
        )
    )
    for phase in multi_swap.phases:
        if phase.swap is None:
            continue
        fig.add_vline(
            x=phase.round_start - 0.5,
            line_color="#1E293B",
            line_dash="dash",
            line_width=1,
        )
        fig.add_annotation(
            x=phase.round_start - 0.5,
            y=1.05,
            text=f"swap {phase.swap.agent_id}",
            showarrow=False,
            font=dict(size=10, color="#1E293B"),
            yanchor="bottom",
        )
    fig.update_layout(
        title="Per-round outcomes (green = stabilized, red = lost)",
        height=160,
        margin=dict(t=40, b=20, l=40, r=20),
        showlegend=False,
        xaxis_title="Round",
        yaxis=dict(visible=False, range=[0, 1.1]),
        bargap=0.05,
    )
    st.plotly_chart(fig, use_container_width=True)


def _run_picker_label(multi_swap: MultiSwapRun) -> str:
    """Picker label combining run id, primary model, swap count, and labels."""
    label_suffix = f" [{', '.join(multi_swap.labels)}]" if multi_swap.labels else ""
    return (
        f"{multi_swap.run_id} • {multi_swap.primary_model} • "
        f"{len(multi_swap.swaps)} swap(s){label_suffix}"
    )


def _render_per_run(evaluated: list[EvaluatedRun]) -> None:
    """Per-run bar chart, per-round strip, and phase breakdown table."""
    run_filter = seed_mode_filter.render_filters(key_prefix="multi_swap")
    evaluated = seed_mode_filter.apply(evaluated=evaluated, run_filter=run_filter)
    st.markdown(
        "Visualise per-phase round-success for runs with one or more in-run "
        "agent swaps. Each bar is one phase between adjacent swaps; Δ pp "
        "above the bar shows change vs the previous phase."
    )
    runs = list_multi_swap_runs(evaluated_runs=evaluated)
    if not runs:
        st.info(
            "No runs with `AgentSwappedMidRun` events found. Multi-swap runs "
            "are produced by the in-run scheduler (`scheduled_events` in knobs)."
        )
        return
    frontend_base = render_frontend_base(streamlit_key="multi_swap_frontend_base")
    options = {_run_picker_label(multi_swap=run): run for run in runs}
    chosen_label = st.selectbox(
        label="Run",
        options=list(options.keys()),
        index=0,
        key="multi_swap_run_picker",
    )
    multi_swap = options[chosen_label]
    target_url = run_url(frontend_base=frontend_base, run_id=multi_swap.run_id)
    st.markdown(f"[Open run in frontend ↗]({target_url})")
    st.plotly_chart(_build_phase_chart(multi_swap=multi_swap), use_container_width=True)
    _render_round_strip(multi_swap=multi_swap)
    st.markdown("**Phase breakdown**")
    _render_phase_table(multi_swap=multi_swap)


_IDLE_TRIGGER = "all_agents_idle"


class _FileStatKey(NamedTuple):
    """Cache invalidation key derived from file size + mtime_ns. Matches the
    pattern used by ``run_catalog._RunCacheKey``."""

    size: int
    mtime_ns: int


class _RunRoundData(NamedTuple):
    """Per-run round outcomes extracted from one JSONL pass."""

    success: dict[int, bool]
    triggers: dict[int, str]
    simulation_ended: bool


def _stat_key(path: Path) -> _FileStatKey | None:
    """Return ``_FileStatKey`` for ``path``, or ``None`` if it doesn't exist."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return _FileStatKey(size=stat.st_size, mtime_ns=stat.st_mtime_ns)


_ROUND_DATA_CACHE: dict[Path, tuple[_FileStatKey, _RunRoundData]] = {}
_LABELS_CACHE: dict[Path, tuple[_FileStatKey, frozenset[str]]] = {}


def _read_run_labels(labels_path: Path) -> frozenset[str] | None:
    """Stat-keyed cache of a run's parsed ``labels.json``. Returns ``None``
    if the file is missing or unparseable. Both ``_gather_cohort`` and
    ``_discover_cohort_label_sets`` would otherwise re-read every run's
    labels file on every Streamlit interaction (~6000 reads per render at
    the current scale)."""
    key = _stat_key(path=labels_path)
    if key is None:
        return None
    cached = _LABELS_CACHE.get(labels_path)
    if cached is not None and cached[0] == key:
        return cached[1]
    try:
        labels = frozenset(json.loads(labels_path.read_text()))
    except (OSError, json.JSONDecodeError):
        return None
    _LABELS_CACHE[labels_path] = (key, labels)
    return labels


def _read_run_round_data(jsonl_path: Path) -> _RunRoundData:
    """Single JSONL pass extracting per-round success, per-round trigger, and
    the ``simulation_ended`` flag in one read.

    Cached by ``(size, mtime_ns)`` so repeat reads of a stable completed run
    hit memory; in-flight sims invalidate naturally when the JSONL grows."""
    key = _stat_key(path=jsonl_path)
    if key is None:
        return _RunRoundData(success={}, triggers={}, simulation_ended=False)
    cached = _ROUND_DATA_CACHE.get(jsonl_path)
    if cached is not None and cached[0] == key:
        return cached[1]
    success: dict[int, bool] = {}
    triggers: dict[int, str] = {}
    simulation_ended = False
    with jsonl_path.open() as fh:
        for line in fh:
            if (
                '"round_result_recorded"' not in line
                and '"round_ended"' not in line
                and '"simulation_ended"' not in line
            ):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("event_type")
            if event_type == "round_result_recorded":
                success[event["round_number"]] = bool(event["success"])
            elif event_type == "round_ended":
                trigger = event.get("trigger")
                if isinstance(trigger, str):
                    triggers[event["round_number"]] = trigger
            elif event_type == "simulation_ended":
                simulation_ended = True
    result = _RunRoundData(success=success, triggers=triggers, simulation_ended=simulation_ended)
    _ROUND_DATA_CACHE[jsonl_path] = (key, result)
    return result


def _drop_idle_rounds(success: dict[int, bool], triggers: dict[int, str]) -> dict[int, bool]:
    """Return ``success`` with idle-ended rounds removed so downstream
    aggregation skips them entirely."""
    return {r: w for r, w in success.items() if triggers.get(r) != _IDLE_TRIGGER}


_PHASE_A_CUTOFF = 11
_PROBE_DRIFT_CACHE: dict[Path, tuple[_FileStatKey, dict[str, float]]] = {}


def _cached_run_drift_from_phase_a(probe_jsonl_path: Path) -> dict[str, float]:
    """Stat-keyed cache around ``_run_drift_from_phase_a``. The probe JSONL is
    only ever appended to within a run; once a run is complete, ``(size,
    mtime_ns)`` is stable, so the Levenshtein similarity computations need to
    happen only once per process."""
    key = _stat_key(path=probe_jsonl_path)
    if key is None:
        return {}
    cached = _PROBE_DRIFT_CACHE.get(probe_jsonl_path)
    if cached is not None and cached[0] == key:
        return cached[1]
    result = _run_drift_from_phase_a(probe_jsonl_path=probe_jsonl_path)
    _PROBE_DRIFT_CACHE[probe_jsonl_path] = (key, result)
    return result


def _run_drift_from_phase_a(probe_jsonl_path: Path) -> dict[str, float]:
    """Per phase, mean similarity between this phase's replica answers and the
    Phase-A (cutoff=11) replica answers for the same (agent, question).

    For Phase A (cutoff=11) the comparison is degenerate (reference vs itself),
    so we plot the off-diagonal pairwise similarity of the 3 Phase-A replicas
    — i.e. the agent's intra-replica noise floor at Phase A. For Phase B/C/D
    we compute the mean similarity over all 9 cross-cutoff pairs (3 Phase-A
    replicas × 3 current-phase replicas) and average across (agent, question).
    """
    # texts[(agent_id, question_id)][cutoff_round] = list of response_texts sorted by replica_index
    texts: dict[tuple[str, str], dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    raw_rows: dict[tuple[str, str, int], list[tuple[int, str]]] = defaultdict(list)
    with probe_jsonl_path.open() as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            agent_id = row.get("agent_id")
            question_id = row.get("question_id")
            cutoff = row.get("cutoff_round")
            replica = row.get("replica_index")
            response = row.get("response_text", "")
            if agent_id is None or question_id is None or cutoff is None or replica is None:
                continue
            raw_rows[(agent_id, question_id, int(cutoff))].append((int(replica), response))
    for (agent_id, question_id, cutoff), rows in raw_rows.items():
        rows.sort(key=lambda x: x[0])
        texts[(agent_id, question_id)][cutoff] = [text for _, text in rows]

    by_phase: dict[str, list[float]] = {p: [] for p in _PHASE_ORDER}
    for _, per_cutoff in texts.items():
        reference = per_cutoff.get(_PHASE_A_CUTOFF)
        if not reference:
            continue
        for cutoff, phase in _PHASE_BY_CUTOFF.items():
            current = per_cutoff.get(cutoff)
            if not current:
                continue
            pair_values: list[float] = []
            if cutoff == _PHASE_A_CUTOFF:
                # Off-diagonal within Phase A — the noise floor.
                n = len(current)
                for i in range(n):
                    for j in range(i + 1, n):
                        pair_values.append(
                            Levenshtein.normalized_similarity(current[i], current[j])
                        )
            else:
                # All cross-cutoff pairs: every Phase-A replica vs every current-phase replica.
                for ref_text in reference:
                    for cur_text in current:
                        pair_values.append(Levenshtein.normalized_similarity(ref_text, cur_text))
            if pair_values:
                by_phase[phase].append(mean(pair_values))
    return {phase: (mean(values) if values else float("nan")) for phase, values in by_phase.items()}


def _gather_cohort(
    evaluated: list[EvaluatedRun], required_labels: frozenset[str]
) -> list[EvaluatedRun]:
    """Filter ``evaluated`` to runs whose labels.json is a superset of
    ``required_labels``. Reads labels.json directly so the cohort filter is
    robust against any label-shape changes elsewhere."""
    out: list[EvaluatedRun] = []
    for run in evaluated:
        labels = _read_run_labels(labels_path=run.run_dir / "labels.json")
        if labels is None:
            continue
        if not required_labels.issubset(labels):
            continue
        out.append(run)
    return out


def _per_round_rate(
    cohort: list[_RunRoundEntry], total_rounds: int
) -> tuple[list[float], list[float], list[int]]:
    means: list[float] = []
    ses: list[float] = []
    ns: list[int] = []
    for round_number in range(1, total_rounds + 1):
        values = [
            1.0 if entry.success[round_number] else 0.0
            for entry in cohort
            if round_number in entry.success
        ]
        if values:
            mean_value = mean(values)
            se_value = stdev(values) / (len(values) ** 0.5) if len(values) > 1 else 0.0
        else:
            mean_value = 0.0
            se_value = 0.0
        means.append(mean_value)
        ses.append(se_value)
        ns.append(len(values))
    return means, ses, ns


def _phase_for_round(round_number: int) -> str:
    """Map a round number to its phase label (A/B/C/D) using the 10-round
    boundaries shared with the rest of the multi-swap visualisation. Returns
    an empty string for rounds outside 1–40."""
    if 1 <= round_number <= 10:
        return "A"
    if 11 <= round_number <= 20:
        return "B"
    if 21 <= round_number <= 30:
        return "C"
    if 31 <= round_number <= 40:
        return "D"
    return ""


def _per_phase_round_means(per_round: dict[int, bool]) -> dict[str, float]:
    """For one run, compute mean round-success per phase (A/B/C/D)."""
    by_phase: dict[str, list[float]] = defaultdict(list)
    for round_number, won in per_round.items():
        phase = _phase_for_round(round_number=round_number)
        if phase == "":
            continue
        by_phase[phase].append(1.0 if won else 0.0)
    return {phase: mean(values) for phase, values in by_phase.items() if values}


def _per_phase_round_success_stats(
    cohort: list[_RunRoundEntry],
) -> tuple[list[float], list[float], list[int]]:
    """Per phase (A/B/C/D): mean of per-run phase means, SE, and N runs."""
    per_run_phase_means = [_per_phase_round_means(per_round=entry.success) for entry in cohort]
    means: list[float] = []
    ses: list[float] = []
    ns: list[int] = []
    for phase in _PHASE_ORDER:
        values = [run[phase] for run in per_run_phase_means if phase in run]
        if values:
            means.append(mean(values))
            ses.append(stdev(values) / (len(values) ** 0.5) if len(values) > 1 else 0.0)
        else:
            means.append(float("nan"))
            ses.append(0.0)
        ns.append(len(values))
    return means, ses, ns


def _per_phase_similarity_stats(
    cohort: list[_RunProbeEntry],
) -> tuple[list[float], list[float], list[int]]:
    means: list[float] = []
    ses: list[float] = []
    ns: list[int] = []
    for phase in _PHASE_ORDER:
        values = [
            entry.drift[phase]
            for entry in cohort
            if phase in entry.drift and entry.drift[phase] == entry.drift[phase]  # filter NaN
        ]
        if values:
            mean_value = mean(values)
            se_value = stdev(values) / (len(values) ** 0.5) if len(values) > 1 else 0.0
        else:
            mean_value = float("nan")
            se_value = 0.0
        means.append(mean_value)
        ses.append(se_value)
        ns.append(len(values))
    return means, ses, ns


def _discover_cohort_label_sets(
    evaluated: list[EvaluatedRun],
) -> list[tuple[frozenset[str], int]]:
    """Return distinct frozen label-sets seen on ≥2 evaluated runs, with their counts.

    Each returned `(labels, count)` tuple represents a natural cohort defined
    by the full labels.json content. Runs with identical label-sets share a
    cohort; runs with different label-sets belong to different cohorts.
    Sorted by count descending then label-set string for stable display.
    """
    counts: dict[frozenset[str], int] = defaultdict(int)
    for run in evaluated:
        labels = _read_run_labels(labels_path=run.run_dir / "labels.json")
        if labels is None:
            continue
        counts[labels] += 1
    return sorted(
        [(labels, n) for labels, n in counts.items() if n >= 2],
        key=lambda item: (-item[1], _label_set_display(item[0])),
    )


def _label_set_display(labels: frozenset[str]) -> str:
    """Stable human-readable joined label-set for a cohort."""
    return " + ".join(sorted(labels))


def _is_baseline_labels(labels: frozenset[str]) -> bool:
    """A cohort is a 'baseline' iff its labels include ``baseline_no_swap``."""
    return "baseline_no_swap" in labels


def _cohort_pair_key(labels: frozenset[str]) -> _CohortPairKey | None:
    """Return the ``(budget, pm_schedule)`` pair-key for any experiment or
    baseline cohort, or ``None`` if the cohort doesn't fit the pattern.

    The pair-key groups together an experiment cohort (e.g. ``multi_swap_baseline``
    at b=450) with its matching no-swap baseline (``baseline_no_swap`` +
    ``pm=phase_a_only`` at b=450). Both cohorts share the same pair-key, so
    they can be coloured identically in the overlay charts.
    """
    budget = next((label for label in labels if label.startswith("budget=")), None)
    if budget is None:
        return None
    if "multi_swap_baseline_postmortem_on" in labels:
        return _CohortPairKey(budget=budget, pm_schedule=_PM_SCHEDULE_ALWAYS)
    if "multi_swap_baseline" in labels:
        return _CohortPairKey(budget=budget, pm_schedule=_PM_SCHEDULE_PHASE_A_ONLY)
    if _is_baseline_labels(labels):
        if "pm=always" in labels:
            return _CohortPairKey(budget=budget, pm_schedule=_PM_SCHEDULE_ALWAYS)
        if "pm=phase_a_only" in labels:
            return _CohortPairKey(budget=budget, pm_schedule=_PM_SCHEDULE_PHASE_A_ONLY)
    return None


def _find_baseline_pair_display(
    experiment_labels: frozenset[str],
    display_to_labels: dict[str, frozenset[str]],
) -> str | None:
    """Find the no-swap baseline cohort display string matching this
    experiment cohort, if any."""
    pair_key = _cohort_pair_key(labels=experiment_labels)
    if pair_key is None:
        return None
    for display, labels in display_to_labels.items():
        if not _is_baseline_labels(labels=labels):
            continue
        if _cohort_pair_key(labels=labels) == pair_key:
            return display
    return None


def _merge_key(labels: frozenset[str]) -> _MergeKey | None:
    """Identify the budget-independent grouping key (experiment_type, pm_schedule).

    Multi-swap and no-swap cohorts that differ only in budget share the same
    merge key, so they can be pooled into one effective cohort when the user
    enables ``Merge across budgets``."""
    if "multi_swap_baseline_postmortem_on" in labels:
        return _MergeKey(
            experiment_type=_EXPERIMENT_TYPE_MULTI_SWAP, pm_schedule=_PM_SCHEDULE_ALWAYS
        )
    if "multi_swap_baseline" in labels:
        return _MergeKey(
            experiment_type=_EXPERIMENT_TYPE_MULTI_SWAP, pm_schedule=_PM_SCHEDULE_PHASE_A_ONLY
        )
    if _is_baseline_labels(labels=labels):
        if "pm=always" in labels:
            return _MergeKey(
                experiment_type=_EXPERIMENT_TYPE_NO_SWAP_BASELINE,
                pm_schedule=_PM_SCHEDULE_ALWAYS,
            )
        if "pm=phase_a_only" in labels:
            return _MergeKey(
                experiment_type=_EXPERIMENT_TYPE_NO_SWAP_BASELINE,
                pm_schedule=_PM_SCHEDULE_PHASE_A_ONLY,
            )
    return None


def _merge_display_name(merge_key: _MergeKey) -> str:
    """Human-readable cohort name for a budget-pooled effective cohort."""
    exp_text = (
        "multi-swap"
        if merge_key.experiment_type == _EXPERIMENT_TYPE_MULTI_SWAP
        else "no-swap baseline"
    )
    pm_text = "pm=always" if merge_key.pm_schedule == _PM_SCHEDULE_ALWAYS else "pm=phase_a_only"
    return f"{exp_text} · {pm_text} · all budgets"


def _resolve_effective_cohorts(
    expanded_displays: list[str],
    display_to_labels: dict[str, frozenset[str]],
    merge_budgets: bool,
) -> list[_EffectiveCohort]:
    """Convert the user's selected displays into effective cohorts to plot.

    In ``Split by budget`` mode each display maps 1:1 to one effective cohort.
    In ``Merge across budgets`` mode displays sharing
    (experiment_type, pm_schedule) are pooled into a single cohort named via
    ``_merge_display_name``. Cohorts that don't fit the multi-swap / no-swap
    pattern fall through as singletons in either mode.
    """
    if not merge_budgets:
        cohorts: list[_EffectiveCohort] = []
        for display in expanded_displays:
            labels = display_to_labels[display]
            pair_key = _cohort_pair_key(labels=labels)
            if pair_key is None:
                color_key = _ColorPairKey(budget="", pm_schedule=display)
            else:
                color_key = _ColorPairKey(budget=pair_key.budget, pm_schedule=pair_key.pm_schedule)
            cohorts.append(
                _EffectiveCohort(
                    display=display,
                    contributing_label_sets=[labels],
                    is_baseline=_is_baseline_labels(labels=labels),
                    color_pair_key=color_key,
                )
            )
        return cohorts
    grouped: dict[_MergeKey, list[frozenset[str]]] = {}
    group_order: list[_MergeKey] = []
    singletons: list[str] = []
    for display in expanded_displays:
        labels = display_to_labels[display]
        merge = _merge_key(labels=labels)
        if merge is None:
            singletons.append(display)
            continue
        if merge not in grouped:
            grouped[merge] = []
            group_order.append(merge)
        grouped[merge].append(labels)
    cohorts = []
    for merge in group_order:
        is_baseline = merge.experiment_type == _EXPERIMENT_TYPE_NO_SWAP_BASELINE
        cohorts.append(
            _EffectiveCohort(
                display=_merge_display_name(merge_key=merge),
                contributing_label_sets=grouped[merge],
                is_baseline=is_baseline,
                color_pair_key=_ColorPairKey(budget="", pm_schedule=merge.pm_schedule),
            )
        )
    for display in singletons:
        labels = display_to_labels[display]
        cohorts.append(
            _EffectiveCohort(
                display=display,
                contributing_label_sets=[labels],
                is_baseline=_is_baseline_labels(labels=labels),
                color_pair_key=_ColorPairKey(budget="", pm_schedule=display),
            )
        )
    return cohorts


def _assign_effective_cohort_colors(cohorts: list[_EffectiveCohort]) -> dict[str, str]:
    """Assign palette colours to experiment cohorts in order; baselines inherit
    the colour of the experiment they pair with (same ``color_pair_key``).
    Unpaired baselines fall back to neutral grey."""
    pair_to_color: dict[_ColorPairKey, str] = {}
    colors: dict[str, str] = {}
    palette_index = 0
    for cohort in cohorts:
        if cohort.is_baseline:
            continue
        color = _COHORT_PALETTE[palette_index % len(_COHORT_PALETTE)]
        palette_index += 1
        colors[cohort.display] = color
        pair_to_color[cohort.color_pair_key] = color
    for cohort in cohorts:
        if not cohort.is_baseline:
            continue
        if cohort.color_pair_key in pair_to_color:
            colors[cohort.display] = pair_to_color[cohort.color_pair_key]
        else:
            colors[cohort.display] = _BASELINE_FALLBACK_COLOR
    return colors


def _gather_runs_for_effective_cohort(
    evaluated: list[EvaluatedRun],
    cohort: _EffectiveCohort,
) -> list[EvaluatedRun]:
    """Pool the runs matching every contributing label-set in this effective
    cohort, deduplicating by run directory."""
    seen: set[Path] = set()
    pooled: list[EvaluatedRun] = []
    for labels in cohort.contributing_label_sets:
        runs = _gather_cohort(evaluated=evaluated, required_labels=labels)
        for run in runs:
            if run.run_dir in seen:
                continue
            seen.add(run.run_dir)
            pooled.append(run)
    return pooled


def _legend_name(display: str, n: int, is_baseline: bool) -> str:
    """Cohort label as it appears in the chart legend."""
    if is_baseline:
        return f"{display} (baseline, n={n})"
    return f"{display} (n={n})"


def _dot_color(line_color: str, is_baseline: bool) -> str:
    """Pick the replica-dot colour for a cohort. Experiment cohorts use the
    cohort's full line colour; baseline cohorts use the matching lighter tint
    from the parallel ``_BASELINE_DOT_PALETTE`` so they read as the same hue
    but visually distinct from the experiment dots."""
    if not is_baseline:
        return line_color
    if line_color in _COHORT_PALETTE:
        index = _COHORT_PALETTE.index(line_color)
        return _BASELINE_DOT_PALETTE[index]
    return _BASELINE_DOT_FALLBACK_COLOR


def _jittered_offset(index: int, count: int, amplitude: float) -> float:
    """Deterministic small horizontal offset for the ``index``-th replica out of
    ``count`` so overlapping per-run dots resolve into a visible cloud."""
    if count <= 1:
        return 0.0
    return amplitude * ((index / (count - 1)) - 0.5) * 2.0


def _add_replica_scatter_per_round(
    fig: go.Figure,
    series: _CohortRoundSeries,
    total_rounds: int,
) -> None:
    """Per-run, per-round dots at y=0 / y=1 with horizontal jitter so 0/1
    outcomes spread visibly across each integer round tick."""
    if not series.runs:
        return
    xs: list[float] = []
    ys: list[float] = []
    hover: list[str] = []
    urls: list[str] = []
    n = len(series.runs)
    for run_index, entry in enumerate(series.runs):
        offset = _jittered_offset(
            index=run_index, count=n, amplitude=_REPLICA_JITTER_AMPLITUDE_ROUND
        )
        for round_number in range(1, total_rounds + 1):
            if round_number not in entry.success:
                continue
            xs.append(round_number + offset)
            ys.append(1.0 if entry.success[round_number] else 0.0)
            outcome = "stabilized" if entry.success[round_number] else "lost"
            hover.append(f"{entry.run_id}<br>round {round_number}: {outcome}<br>click to open ↗")
            urls.append(entry.url)
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            name=f"{series.display} · replicas",
            marker=dict(
                color=_dot_color(line_color=series.color, is_baseline=series.is_baseline),
                size=_REPLICA_DOT_SIZE,
                opacity=_REPLICA_DOT_OPACITY,
            ),
            hovertext=hover,
            hoverinfo="text",
            customdata=urls,
            showlegend=False,
        )
    )


def _add_replica_scatter_per_phase(
    fig: go.Figure,
    series: _CohortRoundSeries,
    phase_x_by_label: dict[str, float],
    cohort_offset: float,
) -> None:
    """Per-run, per-phase dots placed at the cohort's offset phase x-position
    with small horizontal jitter."""
    if not series.runs:
        return
    xs: list[float] = []
    ys: list[float] = []
    hover: list[str] = []
    urls: list[str] = []
    n = len(series.runs)
    for run_index, entry in enumerate(series.runs):
        offset = _jittered_offset(
            index=run_index, count=n, amplitude=_REPLICA_JITTER_AMPLITUDE_PHASE
        )
        phase_means = _per_phase_round_means(per_round=entry.success)
        for phase, value in phase_means.items():
            if phase not in phase_x_by_label:
                continue
            xs.append(phase_x_by_label[phase] + cohort_offset + offset)
            ys.append(value)
            hover.append(f"{entry.run_id}<br>Phase {phase}: {value:.1%}<br>click to open ↗")
            urls.append(entry.url)
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            name=f"{series.display} · replicas",
            marker=dict(
                color=_dot_color(line_color=series.color, is_baseline=series.is_baseline),
                size=_REPLICA_DOT_SIZE,
                opacity=_REPLICA_DOT_OPACITY,
            ),
            hovertext=hover,
            hoverinfo="text",
            customdata=urls,
            showlegend=False,
        )
    )


def _add_replica_scatter_probe_phase(
    fig: go.Figure,
    series: _CohortProbeSeries,
    phase_x_by_label: dict[str, float],
    cohort_offset: float,
) -> None:
    """Per-run, per-phase probe-similarity dots at the cohort's offset phase
    x-position with small horizontal jitter."""
    if not series.runs:
        return
    xs: list[float] = []
    ys: list[float] = []
    hover: list[str] = []
    urls: list[str] = []
    n = len(series.runs)
    for run_index, entry in enumerate(series.runs):
        offset = _jittered_offset(
            index=run_index, count=n, amplitude=_REPLICA_JITTER_AMPLITUDE_PHASE
        )
        for phase, value in entry.drift.items():
            if phase not in phase_x_by_label:
                continue
            if value != value:
                continue
            xs.append(phase_x_by_label[phase] + cohort_offset + offset)
            ys.append(value)
            hover.append(
                f"{entry.run_id}<br>Phase {phase}: similarity {value:.3f}<br>click to open ↗"
            )
            urls.append(entry.url)
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            name=f"{series.display} · replicas",
            marker=dict(
                color=_dot_color(line_color=series.color, is_baseline=series.is_baseline),
                size=_REPLICA_DOT_SIZE,
                opacity=_REPLICA_DOT_OPACITY,
            ),
            hovertext=hover,
            hoverinfo="text",
            customdata=urls,
            showlegend=False,
        )
    )


def _build_round_success_chart(
    series_list: list[_CohortRoundSeries],
    total_rounds: int,
    show_dots: bool,
) -> go.Figure:
    """Per-round success curve with one line per cohort, ± SE bars + phase shading.

    Baseline cohorts render as dashed lines in the same colour as their paired
    experiment cohort; experiment cohorts render as solid lines. When
    ``show_dots`` is true, per-run 0/1 outcomes are scattered at each round
    with light jitter so the underlying distribution is visible behind the
    means.
    """
    fig = go.Figure()
    phase_spans = [
        ("Phase A", 1, 10, "rgba(254, 226, 226, 0.45)"),
        ("Phase B", 11, 20, "rgba(254, 243, 199, 0.45)"),
        ("Phase C", 21, 30, "rgba(220, 252, 231, 0.45)"),
        ("Phase D", 31, 40, "rgba(219, 234, 254, 0.45)"),
    ]
    for name, start, end, colour in phase_spans:
        fig.add_vrect(x0=start - 0.5, x1=end + 0.5, fillcolor=colour, line_width=0, layer="below")
        fig.add_annotation(
            x=(start + end) / 2,
            y=1.05,
            text=name,
            showarrow=False,
            font=dict(size=11),
            xref="x",
            yref="paper",
        )
    rounds = list(range(1, total_rounds + 1))
    if show_dots:
        for series in series_list:
            _add_replica_scatter_per_round(fig=fig, series=series, total_rounds=total_rounds)
    for series in series_list:
        if not series.runs:
            continue
        means, ses, _ = _per_round_rate(cohort=series.runs, total_rounds=total_rounds)
        if series.is_baseline:
            line_style = dict(color=series.color, width=2, dash="dash")
            marker_symbol = "circle-open"
        else:
            line_style = dict(color=series.color, width=2.5)
            marker_symbol = "circle"
        fig.add_trace(
            go.Scatter(
                x=rounds,
                y=means,
                error_y=dict(type="data", array=ses, visible=True),
                mode="lines+markers",
                name=_legend_name(
                    display=series.display, n=len(series.runs), is_baseline=series.is_baseline
                ),
                line=line_style,
                marker=dict(color=series.color, size=7, symbol=marker_symbol),
            )
        )
    fig.update_layout(
        title="Per-round success across the 4-phase timeline",
        xaxis=dict(title="Round", range=[0.5, total_rounds + 0.5]),
        yaxis=dict(
            title="Round success rate (mean across replicas)", range=[-0.05, 1.1], tickformat=".0%"
        ),
        height=460,
        margin=dict(t=70, b=50, l=60, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="left", x=0),
    )
    return fig


def _build_round_success_per_phase_chart(
    series_list: list[_CohortRoundSeries],
    show_dots: bool,
) -> go.Figure:
    """Phase-mean round success: one point per (cohort, phase). Baselines
    render with dashed lines + open markers sharing the experiment colour.
    When ``show_dots`` is true, per-run phase means are scattered around each
    cohort's offset position."""
    fig = go.Figure()
    x_positions = list(range(len(_PHASE_ORDER)))
    phase_x_by_label = {phase: float(x) for phase, x in zip(_PHASE_ORDER, x_positions)}
    plotted = [series for series in series_list if series.runs]
    if show_dots:
        for index, series in enumerate(plotted):
            offset = (index - (len(plotted) - 1) / 2) * 0.12
            _add_replica_scatter_per_phase(
                fig=fig,
                series=series,
                phase_x_by_label=phase_x_by_label,
                cohort_offset=offset,
            )
    for index, series in enumerate(plotted):
        means, ses, _ = _per_phase_round_success_stats(cohort=series.runs)
        offset = (index - (len(plotted) - 1) / 2) * 0.12
        if series.is_baseline:
            line_style = dict(color=series.color, width=2, dash="dash")
            marker_symbol = "circle-open"
        else:
            line_style = dict(color=series.color, width=2.5)
            marker_symbol = "circle"
        fig.add_trace(
            go.Scatter(
                x=[x + offset for x in x_positions],
                y=means,
                error_y=dict(type="data", array=ses, visible=True),
                mode="lines+markers",
                name=_legend_name(
                    display=series.display, n=len(series.runs), is_baseline=series.is_baseline
                ),
                line=line_style,
                marker=dict(color=series.color, size=11, symbol=marker_symbol),
            )
        )
    fig.update_layout(
        title="Phase-mean round success",
        xaxis=dict(
            title="Phase",
            tickmode="array",
            tickvals=x_positions,
            ticktext=[f"Phase {p}" for p in _PHASE_ORDER],
        ),
        yaxis=dict(title="Mean round success rate", range=[-0.05, 1.05], tickformat=".0%"),
        height=460,
        margin=dict(t=70, b=50, l=60, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="left", x=0),
    )
    return fig


def _build_phase_similarity_chart(
    series_list: list[_CohortProbeSeries],
    show_dots: bool,
) -> go.Figure:
    """Per-phase probe-answer drift with one series per cohort.

    Baseline cohorts render with open markers in the paired experiment colour;
    experiment cohorts render with filled markers.
    """
    fig = go.Figure()
    x_positions = list(range(len(_PHASE_ORDER)))
    phase_x_by_label = {phase: float(x) for phase, x in zip(_PHASE_ORDER, x_positions)}
    plotted = [series for series in series_list if series.runs]
    if show_dots:
        for index, series in enumerate(plotted):
            offset = (index - (len(plotted) - 1) / 2) * 0.12
            _add_replica_scatter_probe_phase(
                fig=fig,
                series=series,
                phase_x_by_label=phase_x_by_label,
                cohort_offset=offset,
            )
    for index, series in enumerate(plotted):
        means, ses, _ = _per_phase_similarity_stats(cohort=series.runs)
        offset = (index - (len(plotted) - 1) / 2) * 0.12
        marker_symbol = "circle-open" if series.is_baseline else "circle"
        fig.add_trace(
            go.Scatter(
                x=[x + offset for x in x_positions],
                y=means,
                error_y=dict(type="data", array=ses, visible=True),
                mode="markers",
                name=_legend_name(
                    display=series.display, n=len(series.runs), is_baseline=series.is_baseline
                ),
                marker=dict(
                    color=series.color,
                    size=12,
                    symbol=marker_symbol,
                    line=dict(color=series.color, width=2),
                ),
            )
        )
    fig.update_layout(
        title="Probe-answer drift from end of Phase A",
        xaxis=dict(
            title="Phase (probe cutoff at phase end)",
            tickmode="array",
            tickvals=x_positions,
            ticktext=[f"Phase {p}" for p in _PHASE_ORDER],
        ),
        yaxis=dict(title="Mean similarity to end-of-Phase-A answers (Levenshtein)"),
        height=430,
        margin=dict(t=70, b=80, l=60, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="left", x=0),
    )
    return fig


_RECENT_BUDGETS = ("budget=250", "budget=450")
_PM_SCHEDULE_CHOICES: tuple[tuple[str, str], ...] = (
    (_PM_SCHEDULE_PHASE_A_ONLY, "postmortem off after Phase A"),
    (_PM_SCHEDULE_ALWAYS, "postmortem always on"),
)


def _find_experiment_display(
    display_to_labels: dict[str, frozenset[str]],
    budget: str,
    pm_schedule: str,
) -> str | None:
    """Find the multi-swap experiment cohort display matching a given
    (budget, pm_schedule) cell, or None if no such cohort exists."""
    for display, labels in display_to_labels.items():
        if _is_baseline_labels(labels=labels):
            continue
        pair_key = _cohort_pair_key(labels=labels)
        if pair_key is None:
            continue
        if pair_key.budget == budget and pair_key.pm_schedule == pm_schedule:
            return display
    return None


def _render_cohort_checkboxes(
    display_to_labels: dict[str, frozenset[str]],
) -> list[str]:
    """Render two checkbox columns (Budget × Postmortem schedule) restricted
    to the recent multi-swap cohorts, and return the experiment cohort displays
    corresponding to the (budget, pm) cross-product of the checked cells."""
    st.markdown("**Experiment cohorts to compare**")
    column_budget, column_pm = st.columns(2)
    selected_budgets: list[str] = []
    with column_budget:
        st.caption("Budget")
        for budget in _RECENT_BUDGETS:
            if st.checkbox(label=budget, value=True, key=f"multi_swap_cohort_budget_{budget}"):
                selected_budgets.append(budget)
    selected_pm_schedules: list[str] = []
    with column_pm:
        st.caption("Postmortem schedule")
        for pm_value, pm_label in _PM_SCHEDULE_CHOICES:
            if st.checkbox(label=pm_label, value=True, key=f"multi_swap_cohort_pm_{pm_value}"):
                selected_pm_schedules.append(pm_value)
    selected: list[str] = []
    for budget in selected_budgets:
        for pm in selected_pm_schedules:
            display = _find_experiment_display(
                display_to_labels=display_to_labels, budget=budget, pm_schedule=pm
            )
            if display is not None:
                selected.append(display)
    return selected


def _expand_with_baseline_pairs(
    selected_displays: list[str],
    display_to_labels: dict[str, frozenset[str]],
) -> tuple[list[str], list[str]]:
    """For each non-baseline cohort in ``selected_displays``, add the matching
    baseline cohort if one exists and isn't already selected.

    Returns ``(expanded_selection_in_render_order, auto_added_displays)``.
    The render order interleaves each experiment with its matching baseline so
    paired series appear adjacent in the legend.
    """
    already_selected = set(selected_displays)
    expanded: list[str] = []
    auto_added: list[str] = []
    for display in selected_displays:
        expanded.append(display)
        labels = display_to_labels[display]
        if _is_baseline_labels(labels=labels):
            continue
        pair_display = _find_baseline_pair_display(
            experiment_labels=labels, display_to_labels=display_to_labels
        )
        if pair_display is None:
            continue
        if pair_display in already_selected:
            continue
        if pair_display in expanded:
            continue
        expanded.append(pair_display)
        auto_added.append(pair_display)
    return expanded, auto_added


def _render_cohort_overlay(evaluated: list[EvaluatedRun]) -> None:
    """Multi-cohort overlay: per-round success curve + per-phase probe similarity.

    Multi-swap experiment cohorts auto-pair with their matching no-swap baseline
    (same budget, same postmortem schedule) so each experiment is plotted next
    to its reference baseline. Experiment cohorts render as solid lines;
    baselines render as dashed lines sharing the experiment colour.
    """
    st.markdown(
        "Compare the recent multi-swap cohorts (budgets 250 / 450, both "
        "postmortem schedules) against their matching no-swap baselines. Each "
        "checked (budget × postmortem) cell becomes one experiment line; the "
        "matching no-swap baseline (same budget + postmortem schedule) is "
        "automatically overlaid as a dashed line."
    )
    cohort_label_sets = _discover_cohort_label_sets(evaluated=evaluated)
    if not cohort_label_sets:
        st.info("No cohort label-sets found (need ≥2 runs sharing the exact same labels.json).")
        return
    display_to_labels: dict[str, frozenset[str]] = {
        _label_set_display(labels): labels for labels, _ in cohort_label_sets
    }
    selected_displays = _render_cohort_checkboxes(display_to_labels=display_to_labels)
    if not selected_displays:
        st.info("Check at least one (budget × postmortem schedule) cell.")
        return
    expanded_displays, auto_added = _expand_with_baseline_pairs(
        selected_displays=selected_displays, display_to_labels=display_to_labels
    )
    if auto_added:
        st.caption(f"Auto-paired baselines: {', '.join(auto_added)}")

    control_left, control_mid, control_right = st.columns(3)
    with control_left:
        view_mode = st.radio(
            label="Round-success view",
            options=[_VIEW_PER_ROUND, _VIEW_PER_PHASE],
            index=1,
            horizontal=True,
            key="multi_swap_cohort_view_mode",
        )
    with control_mid:
        budget_mode = st.radio(
            label="Budget treatment",
            options=[_BUDGET_SPLIT, _BUDGET_MERGE],
            index=0,
            horizontal=True,
            key="multi_swap_cohort_budget_mode",
        )
    with control_right:
        dots_mode = st.radio(
            label="Replica dots",
            options=[_DOTS_VISIBLE, _DOTS_HIDDEN],
            index=0,
            horizontal=True,
            key="multi_swap_cohort_dots_mode",
        )
    show_dots = dots_mode == _DOTS_VISIBLE
    exclude_idle = st.checkbox(
        label=(
            "Exclude `all_agents_idle` rounds from round-success "
            "(only count rounds where the engineer committed a procedure)"
        ),
        value=False,
        key="multi_swap_cohort_exclude_idle",
    )
    frontend_base = render_frontend_base(streamlit_key="multi_swap_cohort_frontend_base")

    if view_mode == _VIEW_PER_ROUND:
        total_rounds = int(
            st.number_input(
                label="Total rounds (x-axis range for the round-success curve)",
                min_value=10,
                max_value=200,
                value=40,
                step=5,
                key="multi_swap_cohort_total_rounds",
            )
        )
    else:
        total_rounds = 40

    effective_cohorts = _resolve_effective_cohorts(
        expanded_displays=expanded_displays,
        display_to_labels=display_to_labels,
        merge_budgets=(budget_mode == _BUDGET_MERGE),
    )
    colors = _assign_effective_cohort_colors(cohorts=effective_cohorts)
    round_series: list[_CohortRoundSeries] = []
    probe_series: list[_CohortProbeSeries] = []
    for cohort in effective_cohorts:
        runs = _gather_runs_for_effective_cohort(evaluated=evaluated, cohort=cohort)
        color = colors[cohort.display]
        round_data: list[_RunRoundEntry] = []
        for run in runs:
            jsonl = run.run_dir / f"{run.scenario_name}.jsonl"
            rd = _read_run_round_data(jsonl_path=jsonl)
            if not rd.simulation_ended:
                continue
            success = rd.success
            if exclude_idle:
                success = _drop_idle_rounds(success=success, triggers=rd.triggers)
            round_data.append(
                _RunRoundEntry(
                    success=success,
                    run_id=run.run_id,
                    url=run_url(frontend_base=frontend_base, run_id=run.run_id),
                )
            )
        round_series.append(
            _CohortRoundSeries(
                display=cohort.display,
                runs=round_data,
                is_baseline=cohort.is_baseline,
                color=color,
            )
        )
        probe_data: list[_RunProbeEntry] = []
        for run in runs:
            probe_path = run.run_dir / "protocol_probe_responses.jsonl"
            if probe_path.exists():
                probe_data.append(
                    _RunProbeEntry(
                        drift=_cached_run_drift_from_phase_a(probe_jsonl_path=probe_path),
                        run_id=run.run_id,
                        url=run_url(frontend_base=frontend_base, run_id=run.run_id),
                    )
                )
        probe_series.append(
            _CohortProbeSeries(
                display=cohort.display,
                runs=probe_data,
                is_baseline=cohort.is_baseline,
                color=color,
            )
        )

    if all(not series.runs for series in round_series) and all(
        not series.runs for series in probe_series
    ):
        st.warning("Selected cohorts have no finished runs or probe data yet.")
        return
    st.markdown("---")
    if view_mode == _VIEW_PER_PHASE:
        st.subheader("Phase-mean round success")
        fig_rounds = _build_round_success_per_phase_chart(
            series_list=round_series, show_dots=show_dots
        )
    else:
        st.subheader("Per-round success curve")
        fig_rounds = _build_round_success_chart(
            series_list=round_series, total_rounds=total_rounds, show_dots=show_dots
        )
    rounds_event = st.plotly_chart(
        fig_rounds,
        use_container_width=True,
        key="multi_swap_cohort_rounds_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    maybe_open_clicked_run(
        chart_event=rounds_event, session_key="multi_swap_cohort_rounds_last_opened_url"
    )

    st.markdown("---")
    st.subheader("Probe-answer drift from end of Phase A")
    st.caption(
        "At each phase boundary we ask each agent the same probe question 3 times "
        "(3 replicas under temperature). For Phase B/C/D we then compare **the 3 "
        "current-phase replica answers against the 3 end-of-Phase-A replica "
        "answers for the same (agent, question)** — every cross pair (9 total) "
        "scored with normalized Levenshtein similarity, then averaged per "
        "(agent, question) and across (agent, question) within the run. The "
        "Phase A point itself is the **noise floor**: off-diagonal pairwise "
        "similarity among the 3 Phase-A replicas (no cross-phase reference yet). "
        "**Higher = the agent still gives the same answer it gave at end of "
        "Phase A → protocol unchanged**; lower = the agent's answer has drifted "
        "since Phase A → language has shifted. Probe cutoffs 11/21/31/41 map "
        "to the end of phases A/B/C/D respectively (an exclusive round cutoff, "
        "so cutoff=11 means the agent has seen rounds 1–10)."
    )
    fig_sim = _build_phase_similarity_chart(series_list=probe_series, show_dots=show_dots)
    sim_event = st.plotly_chart(
        fig_sim,
        use_container_width=True,
        key="multi_swap_cohort_similarity_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    maybe_open_clicked_run(
        chart_event=sim_event, session_key="multi_swap_cohort_similarity_last_opened_url"
    )


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the multi-swap tab body: Cohort overlay (default) + Per-run subtabs."""
    cohort_panel, per_run_panel = st.tabs(["Cohort overlay", "Per-run"])
    with cohort_panel:
        _render_cohort_overlay(evaluated=evaluated)
    with per_run_panel:
        _render_per_run(evaluated=evaluated)
