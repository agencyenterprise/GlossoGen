"""Plot round_success vs per-round time budget for Veyru baseline runs.

Two vertically stacked panels:

* **Closed models** (top) — every run carrying the ``baseline`` label
  (opus-4.7, gpt-5.4).
* **Open models** (bottom) — every run carrying the ``baseline_oss`` label
  (Llama-3.3-70B, Qwen3-32B).

Each panel has one line per ``(model, postmortem_enabled)`` series with replica
dots, a mean trace, and ±1 std error bars. X axis is the per-round
``round_time_budget_seconds`` in log scale; Y axis is the ``round_success``
rate (fraction of rounds stabilized out of ``round_count``).

Uses the doubled-font rcParams from ``plot_round_success_with_mcm.py`` so the
chart text reads at presentation scale.
"""

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.ticker import PercentFormatter

_SCENARIO_NAME = "veyru"
_BASELINE_LABEL = "baseline"
_BASELINE_OSS_LABEL = "baseline_oss"
_ROUND_SUCCESS_METRIC = "round_success"
_EXCLUDED_MODELS = frozenset({"claude-sonnet-4-6"})
_OUTPUT_PATH = Path(__file__).resolve().parent / "output" / "baseline_budget_sweep.png"

_LARGE_FONT_RCPARAMS = {
    "font.size": 29,
    "axes.titlesize": 35,
    "axes.labelsize": 31,
    "xtick.labelsize": 29,
    "ytick.labelsize": 29,
    "legend.fontsize": 24,
    "figure.titlesize": 41,
}

# Per-model brand colors. New models added here cycle through matplotlib's
# tab10 palette via _model_color_map (alphabetical fallback).
_MODEL_COLORS: dict[str, str] = {
    "claude-opus-4-7": "#1f3a93",
    "claude-sonnet-4-6": "#c1440e",
    "gpt-5.4": "#2ecc71",
    "meta-llama/Llama-3.3-70B-Instruct": "#8e44ad",
    "Qwen/Qwen3-32B": "#b87333",
}

_FALLBACK_COLOR_CYCLE = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
)


class _RunRecord(NamedTuple):
    """One baseline-cohort run with everything needed for the plot."""

    run_dir: Path
    model: str
    postmortem_enabled: bool
    budget: int
    total_rounds: int
    round_success_count: int


def _read_labels(run_dir: Path) -> list[str]:
    """Load ``labels.json`` as a list of strings (empty if missing/malformed)."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return []
    try:
        raw = json.loads(labels_path.read_text())
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _scan_run_meta(run_dir: Path) -> tuple[str, int, bool, int] | None:
    """Return ``(model, budget, postmortem_enabled, round_count)`` from the run's JSONL.

    Returns ``None`` when any field is missing.
    """
    jsonl_path = run_dir / f"{_SCENARIO_NAME}.jsonl"
    if not jsonl_path.exists():
        return None
    model: str | None = None
    budget: int | None = None
    pm: bool | None = None
    round_count: int | None = None
    with jsonl_path.open() as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("event_type")
            if event_type == "agent_registered" and model is None:
                candidate = event.get("model")
                if isinstance(candidate, str):
                    model = candidate
            elif event_type == "simulation_started":
                config = event.get("scenario_config", {})
                if isinstance(config, dict):
                    budget_value = config.get("round_time_budget_seconds")
                    pm_value = config.get("postmortem_enabled")
                    round_count_value = config.get("round_count")
                    if isinstance(budget_value, (int, float)):
                        budget = int(budget_value)
                    if isinstance(pm_value, bool):
                        pm = pm_value
                    if isinstance(round_count_value, int):
                        round_count = round_count_value
            if (
                model is not None
                and budget is not None
                and pm is not None
                and round_count is not None
            ):
                break
    if model is None or budget is None or pm is None or round_count is None:
        return None
    return (model, budget, pm, round_count)


def _round_success_count(report_path: Path) -> int | None:
    """Return the number of per-round observations with ``value > 0`` for ``round_success``."""
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text())
    except json.JSONDecodeError:
        return None
    for measurement in report.get("measurements", []):
        if not isinstance(measurement, dict):
            continue
        if measurement.get("metric_name") != _ROUND_SUCCESS_METRIC:
            continue
        per_round = measurement.get("per_round", [])
        if not isinstance(per_round, list):
            return None
        return sum(
            1
            for obs in per_round
            if isinstance(obs, dict)
            and isinstance(obs.get("value"), (int, float))
            and obs["value"] > 0
        )
    return None


def _collect_runs(required_label: str) -> list[_RunRecord]:
    """Walk ``runs/veyru/<ts>`` dirs and return everyone carrying ``required_label``."""
    out: list[_RunRecord] = []
    scenario_dir = Path("runs") / _SCENARIO_NAME
    if not scenario_dir.is_dir():
        return out
    for entry in sorted(scenario_dir.iterdir()):
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        labels = _read_labels(run_dir=entry)
        if required_label not in labels:
            continue
        meta = _scan_run_meta(run_dir=entry)
        if meta is None:
            continue
        model, budget, pm, round_count = meta
        if model in _EXCLUDED_MODELS:
            continue
        success = _round_success_count(report_path=entry / f"{_SCENARIO_NAME}_report.json")
        if success is None:
            continue
        out.append(
            _RunRecord(
                run_dir=entry,
                model=model,
                postmortem_enabled=pm,
                budget=budget,
                total_rounds=round_count,
                round_success_count=success,
            )
        )
    return out


def _model_color_map(models: list[str]) -> dict[str, str]:
    """Assign one color per model from the preset map, falling back to the cycle."""
    out: dict[str, str] = {}
    cycle_index = 0
    for model in sorted(models):
        if model in _MODEL_COLORS:
            out[model] = _MODEL_COLORS[model]
        else:
            out[model] = _FALLBACK_COLOR_CYCLE[cycle_index % len(_FALLBACK_COLOR_CYCLE)]
            cycle_index += 1
    return out


class _SeriesAggregate(NamedTuple):
    """Aggregated per-budget statistics for one ``(model, postmortem)`` series."""

    budgets: list[int]
    means: list[float]
    stds: list[float]
    replica_xs: list[float]
    replica_ys: list[float]


def _short_model_label(model: str) -> str:
    """Return a compact display label for ``model`` (strip vendor prefixes)."""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def _series_label(model: str, postmortem_enabled: bool) -> str:
    """Legend label for a ``(model, postmortem)`` series."""
    suffix = "postmortem" if postmortem_enabled else "no postmortem"
    return f"{_short_model_label(model=model)} · {suffix}"


def _aggregate_series(
    runs: list[_RunRecord], model: str, postmortem_enabled: bool
) -> _SeriesAggregate:
    """Build per-budget mean/std + jittered replica points for one series."""
    by_budget: dict[int, list[float]] = defaultdict(list)
    for run in runs:
        if run.model != model or run.postmortem_enabled != postmortem_enabled:
            continue
        by_budget[run.budget].append(run.round_success_count / run.total_rounds)
    budgets = sorted(by_budget.keys())
    means: list[float] = []
    stds: list[float] = []
    replica_xs: list[float] = []
    replica_ys: list[float] = []
    for budget in budgets:
        values = by_budget[budget]
        mean = sum(values) / len(values)
        variance = (
            sum((v - mean) ** 2 for v in values) / (len(values) - 1) if len(values) > 1 else 0.0
        )
        means.append(mean)
        stds.append(math.sqrt(variance))
        for index, value in enumerate(values):
            replica_xs.append(_jittered_log_x(base_x=budget, index=index, count=len(values)))
            replica_ys.append(value)
    return _SeriesAggregate(
        budgets=budgets,
        means=means,
        stds=stds,
        replica_xs=replica_xs,
        replica_ys=replica_ys,
    )


def _jittered_log_x(base_x: int, index: int, count: int) -> float:
    """Return a small symmetric jitter around ``base_x`` in log-space."""
    if count <= 1:
        return float(base_x)
    spread = 0.06  # log10 units
    offset = -spread + (2 * spread) * (index / (count - 1))
    return float(base_x) * (10**offset)


def _plot_panel(
    ax: Axes,
    runs: list[_RunRecord],
    title: str,
    color_by_model: dict[str, str],
    x_tickvals: list[int],
) -> None:
    """Render one panel: replica dots + mean traces with ±1 std error bars."""
    models_present = sorted({run.model for run in runs})
    for model in models_present:
        color = color_by_model[model]
        for postmortem_enabled in (True, False):
            agg = _aggregate_series(runs=runs, model=model, postmortem_enabled=postmortem_enabled)
            if not agg.budgets:
                continue
            linestyle = "-" if postmortem_enabled else "--"
            marker = "o" if postmortem_enabled else "s"
            ax.scatter(
                agg.replica_xs,
                agg.replica_ys,
                color=color,
                alpha=0.22,
                s=40,
                zorder=1,
            )
            ax.errorbar(
                agg.budgets,
                agg.means,
                yerr=agg.stds,
                marker=marker,
                markersize=10,
                linewidth=2.5,
                capsize=6,
                color=color,
                linestyle=linestyle,
                label=_series_label(model=model, postmortem_enabled=postmortem_enabled),
                zorder=3,
            )
    ax.set_xscale("log")
    ax.set_xticks(x_tickvals)
    ax.set_xticklabels([str(b) for b in x_tickvals])
    ax.set_xlim(min(x_tickvals) / 1.25, max(x_tickvals) * 1.25)
    ax.set_ylim(-0.05, 1.05)
    ax.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax.set_ylabel("Round success")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)


def main() -> None:
    plt.rcParams.update(_LARGE_FONT_RCPARAMS)
    closed_runs = _collect_runs(required_label=_BASELINE_LABEL)
    open_runs = _collect_runs(required_label=_BASELINE_OSS_LABEL)
    print(f"Closed-model runs: {len(closed_runs)}")
    print(f"Open-model runs: {len(open_runs)}")
    if not closed_runs and not open_runs:
        raise SystemExit("No baseline/baseline_oss runs found.")
    all_models = sorted({run.model for run in closed_runs + open_runs})
    color_by_model = _model_color_map(models=all_models)
    all_budgets = sorted({run.budget for run in closed_runs + open_runs})

    fig, (ax_closed, ax_open) = plt.subplots(
        2, 1, figsize=(16, 14), sharex=True, gridspec_kw={"hspace": 0.45}
    )
    _plot_panel(
        ax=ax_closed,
        runs=closed_runs,
        title="Closed models",
        color_by_model=color_by_model,
        x_tickvals=all_budgets,
    )
    ax_closed.tick_params(axis="x", labelbottom=True)
    ax_closed.set_xlabel("Round budget")
    _plot_panel(
        ax=ax_open,
        runs=open_runs,
        title="Open models",
        color_by_model=color_by_model,
        x_tickvals=all_budgets,
    )
    ax_open.set_xlabel("Round budget")
    fig.align_ylabels((ax_closed, ax_open))
    fig.savefig(_OUTPUT_PATH, dpi=200, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
