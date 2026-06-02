"""Streamlit tab summarising stabilization-judge-replay damage by model.

Reads every ``judge_replay.json`` sidecar attached to an ``EvaluatedRun`` and
aggregates the flip counts grouped by the run's primary model (the first
``agent_registered`` event in the JSONL, which for veyru is the
``field_observer`` — the agent whose ``stabilize_veyru`` calls are judged).

Two views:

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


def _aggregate_by_model(evaluated: list[EvaluatedRun]) -> list[_ModelAggregate]:
    """Group runs with a sidecar by ``primary_model`` and sum flip counts."""
    by_model: dict[str, _ModelAccumulator] = {}
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
        run_flip_rate = flipped / old_true
        model = run.metadata.primary_model
        acc = by_model.setdefault(model, _ModelAccumulator())
        acc.runs += 1
        acc.old_true_total += old_true
        acc.flipped_total += flipped
        if run_flip_rate > acc.worst_run_flip_rate:
            acc.worst_run_id = run.run_id
            acc.worst_run_flip_rate = run_flip_rate

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
    rows = _aggregate_by_model(evaluated=evaluated)
    if not rows:
        st.info(
            "No runs with `judge_replay.json` sidecars found. Run "
            "`python scripts/replay_veyru_judge.py` followed by "
            "`python scripts/write_judge_replay_sidecars.py` to populate them."
        )
        return

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
