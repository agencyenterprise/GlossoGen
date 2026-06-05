"""Streamlit tab summarising stabilization-judge-replay damage by model.

Reads every ``judge_replay.json`` sidecar attached to an ``EvaluatedRun`` and
aggregates the flip counts grouped by the run's primary model (the first
``agent_registered`` event in the JSONL, which for veyru is the
``field_observer`` — the agent whose ``stabilize_veyru`` calls are judged).

Views:

- A headline pair: the percentage of runs affected (at least one verdict
  flipped) and the count of runs carrying a sidecar.
- A per-run flip-rate distribution: each run's flips ÷ its previously-accepted
  verdicts bucketed into non-zero bands (>0-20%, ... >80-100%; the no-flip
  bucket is omitted), so statements like "20% of runs had more than 80% of
  their verdicts flip" can be read off directly.
- A horizontal bar chart of per-model flip rate (% of previously-accepted
  stabilizations that flip to rejected under the current judge prompt),
  sorted descending so the most damaged models surface first.
- A table with the underlying counts (runs scored, flipped events, old-True
  events, flip%) and a small "max-damage run" cell pointing at the worst
  offender per model.

Only veyru runs carry sidecars today; the tab simply shows an info message
when no sidecars are found rather than trying to be clever.
"""

import json
from dataclasses import dataclass
from typing import NamedTuple

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import render_frontend_base, run_url


@dataclass
class _ModelAccumulator:
    """Mutable rollup state for a single model, used during aggregation."""

    runs: int = 0
    old_true_total: int = 0
    flipped_total: int = 0
    worst_run_id: str = ""
    worst_run_flip_rate: float = -1.0


class _ModelAggregate(NamedTuple):
    """Per-model rollup of stabilization-judge-replay flips."""

    model: str
    runs: int
    old_true_total: int
    flipped_total: int
    flip_rate: float
    worst_run_id: str
    worst_run_flip_rate: float


class _RunFlip(NamedTuple):
    """Per-run stabilization-judge replay flip stats for one run with a sidecar."""

    run_id: str
    scenario: str
    model: str
    old_true: int
    flipped: int
    flip_rate: float


class _FlipBucket(NamedTuple):
    """One band of the per-run flip-rate distribution."""

    label: str
    run_count: int
    pct_of_runs: float


class _ReplayCoverage(NamedTuple):
    """Run counts describing judge-replay coverage across the sidecar-bearing scenarios.

    The four counts nest: ``affected <= scoreable <= replayed <= total``.
    ``never_replayed = total - replayed`` (no sidecar file yet) and
    ``zero_accepted = replayed - scoreable`` (replayed but the original judge
    accepted nothing, so there is no flip rate to compute) are derived for
    display.
    """

    total: int
    replayed: int
    scoreable: int
    affected: int


def _collect_run_flips(evaluated: list[EvaluatedRun]) -> list[_RunFlip]:
    """Read every ``judge_replay.json`` sidecar into per-run flip stats.

    Only runs whose sidecar records at least one previously-accepted verdict
    (``old_true_count > 0``) are included; a run with no accepted verdicts has
    no flip rate to report.
    """
    out: list[_RunFlip] = []
    for run in evaluated:
        sidecar_path = run.run_dir / "judge_replay.json"
        if not sidecar_path.exists():
            continue
        try:
            raw = json.loads(sidecar_path.read_text())
        except Exception:
            continue
        old_true = int(raw.get("old_true_count", 0))
        if old_true == 0:
            continue
        flipped = int(raw.get("flipped_true_to_false", 0))
        out.append(
            _RunFlip(
                run_id=run.run_id,
                scenario=run.scenario_name,
                model=run.metadata.primary_model,
                old_true=old_true,
                flipped=flipped,
                flip_rate=flipped / old_true,
            )
        )
    return out


def _replay_coverage(evaluated: list[EvaluatedRun], run_flips: list[_RunFlip]) -> _ReplayCoverage:
    """Count total / replayed / scoreable / affected runs across sidecar-bearing scenarios.

    ``total`` is scoped to the scenarios that carry at least one sidecar file so
    unrelated scenarios do not inflate the denominator. ``replayed`` counts runs
    with a ``judge_replay.json`` file (including zero-accepted ones), while
    ``scoreable`` is the subset with a measurable flip rate (``run_flips``).
    """
    replayed_scenarios: set[str] = set()
    replayed = 0
    for run in evaluated:
        if (run.run_dir / "judge_replay.json").exists():
            replayed_scenarios.add(run.scenario_name)
            replayed += 1
    total = sum(1 for run in evaluated if run.scenario_name in replayed_scenarios)
    affected = sum(1 for flip in run_flips if flip.flip_rate > 0.0)
    return _ReplayCoverage(
        total=total,
        replayed=replayed,
        scoreable=len(run_flips),
        affected=affected,
    )


_FLIP_RATE_BANDS: tuple[tuple[str, float, float], ...] = (
    (">0-20%", 0.0, 0.2),
    (">20-40%", 0.2, 0.4),
    (">40-60%", 0.4, 0.6),
    (">60-80%", 0.6, 0.8),
    (">80-100%", 0.8, 1.0),
)


def _bucket_distribution(run_flips: list[_RunFlip]) -> list[_FlipBucket]:
    """Bucket each run's flip rate into non-zero bands and report count + % of runs per band.

    The zero-flip runs are intentionally omitted (the no-flip bucket is not
    relevant to the damage view); the remaining bands are half-open
    ``(low, high]`` so a run sits in exactly one band. Percentages stay
    relative to all scoreable runs, so the bands sum to less than 100% by the
    hidden no-flip share.
    """
    total = len(run_flips)
    if total == 0:
        return []
    buckets: list[_FlipBucket] = []
    for label, low, high in _FLIP_RATE_BANDS:
        count = sum(1 for rf in run_flips if low < rf.flip_rate <= high)
        buckets.append(_FlipBucket(label=label, run_count=count, pct_of_runs=100.0 * count / total))
    return buckets


def _aggregate_by_model(run_flips: list[_RunFlip]) -> list[_ModelAggregate]:
    """Group per-run flip stats by ``model`` and sum flip counts."""
    by_model: dict[str, _ModelAccumulator] = {}
    for rf in run_flips:
        acc = by_model.setdefault(rf.model, _ModelAccumulator())
        acc.runs += 1
        acc.old_true_total += rf.old_true
        acc.flipped_total += rf.flipped
        if rf.flip_rate > acc.worst_run_flip_rate:
            acc.worst_run_id = rf.run_id
            acc.worst_run_flip_rate = rf.flip_rate

    rows = [
        _ModelAggregate(
            model=model,
            runs=acc.runs,
            old_true_total=acc.old_true_total,
            flipped_total=acc.flipped_total,
            flip_rate=acc.flipped_total / acc.old_true_total,
            worst_run_id=acc.worst_run_id,
            worst_run_flip_rate=acc.worst_run_flip_rate,
        )
        for model, acc in by_model.items()
        if acc.old_true_total > 0
    ]
    rows.sort(key=lambda r: r.flip_rate, reverse=True)
    return rows


def _build_flip_rate_bar_chart(rows: list[_ModelAggregate]) -> go.Figure:
    """Horizontal bar chart of per-model flip rate, sorted descending by flip rate."""
    models = [row.model for row in rows]
    pct = [100.0 * row.flip_rate for row in rows]
    runs = [row.runs for row in rows]
    text = [
        f"{p:.1f}% ({r.flipped_total}/{r.old_true_total} ev, {n} runs)"
        for p, r, n in zip(pct, rows, runs)
    ]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=pct,
            y=models,
            orientation="h",
            text=text,
            textposition="outside",
            marker=dict(color=pct, colorscale="Reds", cmin=0, cmax=max(pct + [1])),
            hovertemplate=("<b>%{y}</b><br>" "flip rate: %{x:.2f}%<br>" "<extra></extra>"),
        )
    )
    fig.update_layout(
        title="Judge-replay flip rate per primary model",
        xaxis_title="Flip rate (%)",
        yaxis_title="Primary model",
        yaxis=dict(autorange="reversed"),
        height=80 + 50 * len(rows),
        margin=dict(l=10, r=120, t=60, b=40),
    )
    return fig


def _build_distribution_bar_chart(buckets: list[_FlipBucket]) -> go.Figure:
    """Vertical bar chart of the per-run flip-rate distribution (% of runs per band)."""
    labels = [bucket.label for bucket in buckets]
    pct = [bucket.pct_of_runs for bucket in buckets]
    text = [f"{bucket.pct_of_runs:.1f}% ({bucket.run_count})" for bucket in buckets]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=pct,
            text=text,
            textposition="outside",
            marker=dict(color="#c0392b"),
            hovertemplate=("<b>%{x}</b><br>" "%{y:.1f}% of runs<br>" "<extra></extra>"),
        )
    )
    fig.update_layout(
        title="Per-run flip-rate distribution",
        xaxis_title="Per-run flip rate (flipped ÷ previously-accepted verdicts)",
        yaxis_title="% of scoreable runs",
        height=420,
        margin=dict(l=10, r=10, t=60, b=40),
    )
    return fig


def _bucket_distribution_by_model(run_flips: list[_RunFlip]) -> dict[str, list[_FlipBucket]]:
    """Per-model flip-rate distributions; each model's bands are % of that model's runs."""
    by_model: dict[str, list[_RunFlip]] = {}
    for rf in run_flips:
        by_model.setdefault(rf.model, []).append(rf)
    return {model: _bucket_distribution(run_flips=flips) for model, flips in by_model.items()}


def _build_distribution_by_model_chart(by_model: dict[str, list[_FlipBucket]]) -> go.Figure:
    """Grouped bar chart: one bar per model within each flip-rate band.

    Each band's % is of that model's own scoreable run count, so distributions
    stay comparable across models with different run counts. The no-flip bucket
    is omitted, so a model's bars sum to less than 100% by its no-flip share.
    """
    fig = go.Figure()
    for model in sorted(by_model):
        buckets = by_model[model]
        fig.add_trace(
            go.Bar(
                name=model,
                x=[bucket.label for bucket in buckets],
                y=[bucket.pct_of_runs for bucket in buckets],
                text=[str(bucket.run_count) for bucket in buckets],
                textposition="outside",
                hovertemplate=(
                    f"<b>{model}</b><br>"
                    "%{x}<br>"
                    "%{y:.1f}% of this model's runs<br>"
                    "%{text} runs<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        barmode="group",
        title="Per-run flip-rate distribution by model",
        xaxis_title="Per-run flip rate (flipped ÷ previously-accepted verdicts)",
        yaxis_title="% of that model's runs",
        height=460,
        margin=dict(l=10, r=10, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def _render_affected_summary(coverage: _ReplayCoverage) -> None:
    """Headline metrics separating total / replayed / scoreable / affected runs.

    The three populations a run can fall into are kept distinct so a replayed
    run with zero accepted verdicts is no longer reported as "without sidecar":
    ``never_replayed`` (no sidecar file) and ``zero_accepted`` (sidecar present
    but nothing the original judge accepted) are surfaced in the metric helps.
    """
    never_replayed = coverage.total - coverage.replayed
    zero_accepted = coverage.replayed - coverage.scoreable
    total_col, replayed_col, scoreable_col, affected_col = st.columns(4)
    total_col.metric(
        label="Total runs (sidecar scenarios)",
        value=f"{coverage.total:,}",
        help=(
            "All runs in the scenarios that carry `judge_replay.json` sidecars "
            "(veyru), whether or not they were replayed."
        ),
    )
    replayed_col.metric(
        label="Replayed (has sidecar)",
        value=f"{coverage.replayed:,}",
        help=f"{never_replayed:,} runs have no sidecar file yet (never replayed).",
    )
    scoreable_col.metric(
        label="Scoreable (>= 1 accepted verdict)",
        value=f"{coverage.scoreable:,}",
        help=(
            f"{zero_accepted:,} replayed runs had zero verdicts the original judge "
            "accepted, so there is no flip rate to compute."
        ),
    )
    if coverage.scoreable > 0:
        affected_value = f"{100.0 * coverage.affected / coverage.scoreable:.1f}%"
    else:
        affected_value = "n/a"
    affected_col.metric(
        label="Affected (>= 1 flip)",
        value=affected_value,
        help=(
            f"{coverage.affected:,} of {coverage.scoreable:,} scoreable runs had at "
            "least one verdict flip."
        ),
    )


def _render_distribution(run_flips: list[_RunFlip]) -> None:
    """Bucket chart + table of the per-run flip-rate distribution, overall then by model."""
    buckets = _bucket_distribution(run_flips=run_flips)
    st.plotly_chart(_build_distribution_bar_chart(buckets=buckets), width="stretch")
    st.dataframe(
        data=[
            {
                "Flip-rate band": bucket.label,
                "Runs": bucket.run_count,
                "% of runs": f"{bucket.pct_of_runs:.1f}%",
            }
            for bucket in buckets
        ],
        width="stretch",
        hide_index=True,
    )
    by_model = _bucket_distribution_by_model(run_flips=run_flips)
    st.plotly_chart(_build_distribution_by_model_chart(by_model=by_model), width="stretch")


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the "Judge replay" tab."""
    st.header("Stabilization-judge replay damage")
    st.caption(
        "For every run with a `judge_replay.json` sidecar, count how many "
        "stabilizations the original judge accepted but the updated judge "
        "(applying the 'naive reader' test) rejects. Grouped by the run's "
        "primary model — for veyru that's the `field_observer`, whose "
        "`stabilize_veyru` calls feed the judge."
    )
    run_flips = _collect_run_flips(evaluated=evaluated)
    rows = _aggregate_by_model(run_flips=run_flips)
    if not rows:
        st.info(
            "No runs with `judge_replay.json` sidecars found. Run "
            "`python scripts/replay_veyru_judge.py` followed by "
            "`python scripts/write_judge_replay_sidecars.py` to populate them."
        )
        return

    coverage = _replay_coverage(evaluated=evaluated, run_flips=run_flips)
    _render_affected_summary(coverage=coverage)

    st.subheader("Per-run flip-rate distribution")
    _render_distribution(run_flips=run_flips)

    st.subheader("Per-model flip rate")
    st.plotly_chart(_build_flip_rate_bar_chart(rows=rows), width="stretch")

    frontend_base = render_frontend_base(streamlit_key="judge_replay_frontend_base")
    st.subheader("Per-model rollup")
    table_data = []
    for row in rows:
        worst_url = run_url(frontend_base=frontend_base, run_id=row.worst_run_id)
        table_data.append(
            {
                "Model": row.model,
                "Runs scored": row.runs,
                "Old True events": row.old_true_total,
                "Flipped events": row.flipped_total,
                "Flip rate": f"{100 * row.flip_rate:.2f}%",
                "Worst run": f"[{row.worst_run_id}]({worst_url})",
                "Worst run flip rate": f"{100 * row.worst_run_flip_rate:.0f}%",
            }
        )
    st.dataframe(
        data=table_data,
        width="stretch",
        column_config={"Worst run": st.column_config.LinkColumn(display_text=r"(.+)")},
        hide_index=True,
    )

    st.caption(
        f"Aggregated over {sum(r.runs for r in rows):,} runs with sidecars and "
        f"{sum(r.old_true_total for r in rows):,} previously-accepted judge verdicts."
    )
