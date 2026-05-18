"""Plot per-round success rate and mean chars per message across Veyru runs.

Reads every Veyru run carrying every label in ``_REQUIRED_LABELS``, pulls each
run's per-round observations from ``round_success`` and
``mean_chars_per_message``, aggregates by round across runs, and writes three
PNGs to the current working directory:

* ``round_success_with_mcm.png`` — dual-Y combined chart.
* ``round_success.png`` — single-Y success-rate-only chart.
* ``mean_chars_per_message.png`` — single-Y MCM-only chart.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.ticker import PercentFormatter

_SCENARIO_NAME = "veyru"
_REQUIRED_LABELS = ("random_seed", "no_ordered_easy_rounds")
_ROUND_SUCCESS_METRIC = "round_success"
_MCM_METRIC = "mean_chars_per_message"
_COMBINED_PATH = Path("analysis/round_success_with_mcm.png")
_SUCCESS_PATH = Path("analysis/round_success.png")
_MCM_PATH = Path("analysis/mean_chars_per_message.png")
_RUN_TIMESTAMP_FLOOR = 1778877800  # first launch of the no_ordered_easy_rounds cohort

_COMBINED_TITLE = "Success holds up across rounds while messages get shorter"
_MCM_TITLE = "Message length compresses across rounds"

_SUCCESS_COLOR = "#1f3a93"
_MCM_COLOR = "#c1440e"


def _read_labels(run_dir: Path) -> list[str]:
    """Load the run's ``labels.json`` as a list of strings (empty if missing/malformed)."""
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


def _per_round_observations(report: dict[str, object], metric_name: str) -> list[tuple[int, float]]:
    """Pull ``(round_number, value)`` pairs for one metric from a run's report."""
    measurements = report.get("measurements")
    if not isinstance(measurements, list):
        return []
    for measurement in measurements:
        if not isinstance(measurement, dict):
            continue
        if measurement.get("metric_name") != metric_name:
            continue
        per_round = measurement.get("per_round")
        if not isinstance(per_round, list):
            return []
        out: list[tuple[int, float]] = []
        for obs in per_round:
            if not isinstance(obs, dict):
                continue
            round_number = obs.get("round_number")
            value = obs.get("value")
            if isinstance(round_number, int) and isinstance(value, (int, float)):
                out.append((round_number, float(value)))
        return out
    return []


def _qualifying_run_dirs(runs_root: Path) -> list[Path]:
    """List every random-seed Veyru run dir that has both metrics evaluated."""
    out: list[Path] = []
    scenario_dir = runs_root / _SCENARIO_NAME
    if not scenario_dir.is_dir():
        return out
    for entry in sorted(scenario_dir.iterdir()):
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        if int(entry.name) < _RUN_TIMESTAMP_FLOOR:
            continue
        labels = _read_labels(run_dir=entry)
        if not all(required in labels for required in _REQUIRED_LABELS):
            continue
        if not (entry / f"{_SCENARIO_NAME}_report.json").exists():
            continue
        out.append(entry)
    return out


def _scan_run_cell(run_dir: Path) -> tuple[str, int, bool] | None:
    """Read each run's ``(model, budget, postmortem_enabled)`` cell key from its JSONL.

    Returns ``None`` when any of the three fields is missing.
    """
    jsonl_path = run_dir / f"{_SCENARIO_NAME}.jsonl"
    if not jsonl_path.exists():
        return None
    model: str | None = None
    budget: int | None = None
    pm: bool | None = None
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
                    if isinstance(budget_value, (int, float)):
                        budget = int(budget_value)
                    if isinstance(pm_value, bool):
                        pm = pm_value
            if model is not None and budget is not None and pm is not None:
                break
    if model is None or budget is None or pm is None:
        return None
    return (model, budget, pm)


class _RoundAggregate(NamedTuple):
    """Per-round aggregation pulled from raw runs and from cell-level means.

    ``raw_values`` is the list of every raw run's per-round value (used for
    mean + std error bars; matches streamlit's std-over-replicas convention).
    ``cell_means`` is the list of per-cell means at that round (used only for
    the replica-dot scatter, which would land on a 0/1 binary band otherwise).
    """

    raw_values: list[float]
    cell_means: list[float]


def _aggregate_per_round(run_dirs: list[Path], metric_name: str) -> dict[int, _RoundAggregate]:
    """Return raw-run values + cell-level means for every round."""
    by_cell_round: dict[tuple[str, int, bool], dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    raw_by_round: dict[int, list[float]] = defaultdict(list)
    for run_dir in run_dirs:
        cell = _scan_run_cell(run_dir=run_dir)
        if cell is None:
            continue
        report_path = run_dir / f"{_SCENARIO_NAME}_report.json"
        try:
            report = json.loads(report_path.read_text())
        except json.JSONDecodeError:
            continue
        for round_number, value in _per_round_observations(report=report, metric_name=metric_name):
            raw_by_round[round_number].append(value)
            by_cell_round[cell][round_number].append(value)
    rounds = set(raw_by_round.keys())
    for cell_buckets in by_cell_round.values():
        rounds.update(cell_buckets.keys())
    out: dict[int, _RoundAggregate] = {}
    for round_number in sorted(rounds):
        cell_means = [
            sum(values) / len(values)
            for values in (
                cell_buckets.get(round_number, []) for cell_buckets in by_cell_round.values()
            )
            if values
        ]
        out[round_number] = _RoundAggregate(
            raw_values=raw_by_round.get(round_number, []),
            cell_means=cell_means,
        )
    return out


def _mean_and_std(values: list[float]) -> tuple[float, float]:
    """Return ``(mean, sample_standard_deviation)`` from a list of numbers."""
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance)


# z value for two-sided 95% normal-approximation CI; Wilson uses the same.
_WILSON_Z = 1.96


def _wilson_ci(values: list[float]) -> tuple[float, float, float]:
    """Wilson 95% CI for a list of 0/1 binary outcomes.

    Returns ``(p_hat, lower_half_width, upper_half_width)`` where the half-widths
    are absolute distances from ``p_hat`` to the CI bounds (matplotlib expects
    asymmetric yerr in that form). Bounded to ``[0, 1]`` by construction, so the
    bars never escape the plot's proportion axis.
    """
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = sum(values) / n
    z = _WILSON_Z
    denom = 1.0 + z * z / n
    center = (p_hat + z * z / (2.0 * n)) / denom
    spread = z * math.sqrt(p_hat * (1.0 - p_hat) / n + z * z / (4.0 * n * n)) / denom
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return p_hat, p_hat - lower, upper - p_hat


def _jittered_xs(base_x: int, count: int) -> list[float]:
    """Spread ``count`` markers symmetrically around ``base_x`` with linear jitter."""
    if count <= 1:
        return [float(base_x)]
    width = 0.4
    return [base_x - width / 2 + (i / (count - 1)) * width for i in range(count)]


def _plot_replica_dots(
    ax: Axes, rounds: list[int], values_by_round: dict[int, list[float]], color: str
) -> None:
    """Scatter per-run values at each round with linear x-jitter (baseline-tab style)."""
    xs: list[float] = []
    ys: list[float] = []
    for round_number in rounds:
        values = values_by_round.get(round_number, [])
        if not values:
            continue
        xs.extend(_jittered_xs(base_x=round_number, count=len(values)))
        ys.extend(values)
    ax.scatter(xs, ys, color=color, alpha=0.25, s=18, zorder=1)


def _plot_success_axis(
    ax: Axes,
    rounds: list[int],
    means: list[float],
    yerr_low: list[float],
    yerr_high: list[float],
    values_by_round: dict[int, list[float]],
) -> None:
    """Render success-rate replica dots + mean trace with Wilson 95% CI bars."""
    _plot_replica_dots(ax=ax, rounds=rounds, values_by_round=values_by_round, color=_SUCCESS_COLOR)
    ax.errorbar(
        rounds,
        means,
        yerr=[yerr_low, yerr_high],
        marker="o",
        linewidth=2,
        capsize=4,
        color=_SUCCESS_COLOR,
        label="round success rate (95% CI)",
        zorder=3,
    )
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Round")
    ax.set_ylabel("Round success rate", color=_SUCCESS_COLOR)
    ax.tick_params(axis="y", labelcolor=_SUCCESS_COLOR)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax.grid(axis="y", alpha=0.3)
    ax.set_xticks(rounds)


def _plot_mcm_axis(
    ax: Axes,
    rounds: list[int],
    means: list[float],
    stds: list[float],
    values_by_round: dict[int, list[float]],
    line_color: str,
    label_color: str,
) -> None:
    """Render the MCM replica dots + mean trace with std error bars.

    ``line_color`` colors the line, markers, error bars, and replica dots;
    ``label_color`` colors the axis ylabel and tick labels.
    """
    _plot_replica_dots(ax=ax, rounds=rounds, values_by_round=values_by_round, color=line_color)
    ax.errorbar(
        rounds,
        means,
        yerr=stds,
        marker="s",
        linewidth=2,
        capsize=4,
        color=line_color,
        label="mean chars / message",
        zorder=3,
    )
    ax.set_ylabel("Mean chars per message", color=label_color)
    ax.tick_params(axis="y", labelcolor=label_color)
    ax.set_ylim(bottom=0)


def _write_combined_plot(
    rounds: list[int],
    success_means: list[float],
    success_ci_low: list[float],
    success_ci_high: list[float],
    success_by_round: dict[int, list[float]],
    mcm_means: list[float],
    mcm_stds: list[float],
    mcm_by_round: dict[int, list[float]],
) -> None:
    """Dual-Y chart: success rate (left) + MCM (right). Both axes carry replica dots."""
    fig, ax_success = plt.subplots(figsize=(12, 5))
    _plot_success_axis(
        ax=ax_success,
        rounds=rounds,
        means=success_means,
        yerr_low=success_ci_low,
        yerr_high=success_ci_high,
        values_by_round=success_by_round,
    )
    ax_mcm = ax_success.twinx()
    _plot_mcm_axis(
        ax=ax_mcm,
        rounds=rounds,
        means=mcm_means,
        stds=mcm_stds,
        values_by_round=mcm_by_round,
        line_color=_MCM_COLOR,
        label_color=_MCM_COLOR,
    )
    fig.suptitle(_COMBINED_TITLE, fontsize=14, color=_SUCCESS_COLOR, y=0.98)
    lines = []
    labels = []
    for ax in (ax_success, ax_mcm):
        line_objs, line_labels = ax.get_legend_handles_labels()
        lines.extend(line_objs)
        labels.extend(line_labels)
    ax_success.legend(lines, labels, loc="lower right")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(_COMBINED_PATH, dpi=200)
    plt.close(fig)
    print(f"Wrote {_COMBINED_PATH}")


def _write_success_plot(
    rounds: list[int],
    means: list[float],
    ci_low: list[float],
    ci_high: list[float],
    values_by_round: dict[int, list[float]],
) -> None:
    """Single-Y chart: round success rate only, with replica dots."""
    fig, ax = plt.subplots(figsize=(12, 5))
    _plot_success_axis(
        ax=ax,
        rounds=rounds,
        means=means,
        yerr_low=ci_low,
        yerr_high=ci_high,
        values_by_round=values_by_round,
    )
    ax.set_ylabel("Round success rate", color="black")
    ax.tick_params(axis="y", labelcolor="black")
    fig.tight_layout()
    fig.savefig(_SUCCESS_PATH, dpi=200)
    plt.close(fig)
    print(f"Wrote {_SUCCESS_PATH}")


def _write_mcm_plot(
    rounds: list[int],
    means: list[float],
    stds: list[float],
    values_by_round: dict[int, list[float]],
) -> None:
    """Single-Y chart: mean chars per message only, blue trace, black labels."""
    fig, ax = plt.subplots(figsize=(12, 5))
    _plot_mcm_axis(
        ax=ax,
        rounds=rounds,
        means=means,
        stds=stds,
        values_by_round=values_by_round,
        line_color=_SUCCESS_COLOR,
        label_color="black",
    )
    ax.set_xlabel("Round")
    ax.grid(axis="y", alpha=0.3)
    ax.set_xticks(rounds)
    fig.suptitle(_MCM_TITLE, fontsize=14, color="black", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(_MCM_PATH, dpi=200)
    plt.close(fig)
    print(f"Wrote {_MCM_PATH}")


def main() -> None:
    runs_root = Path("runs")
    run_dirs = _qualifying_run_dirs(runs_root=runs_root)
    print(f"Loaded {len(run_dirs)} qualifying runs.")
    # Per-round aggregation: mean/std are computed over RAW runs (matches
    # streamlit's std-over-replicas convention); replica dots use cell-level
    # means (so the binary per-run round_success outcome becomes a continuous
    # cloud at 0/0.33/0.67/1.0 levels instead of just 0/1).
    success_by_round = _aggregate_per_round(run_dirs=run_dirs, metric_name=_ROUND_SUCCESS_METRIC)
    mcm_by_round = _aggregate_per_round(run_dirs=run_dirs, metric_name=_MCM_METRIC)
    rounds = sorted(set(success_by_round.keys()) | set(mcm_by_round.keys()))
    if not rounds:
        raise SystemExit("No per-round data found.")

    success_means: list[float] = []
    success_ci_low: list[float] = []
    success_ci_high: list[float] = []
    success_dots: dict[int, list[float]] = {}
    mcm_means: list[float] = []
    mcm_stds: list[float] = []
    mcm_dots: dict[int, list[float]] = {}
    for round_number in rounds:
        agg = success_by_round.get(round_number, _RoundAggregate(raw_values=[], cell_means=[]))
        p_hat, ci_low_v, ci_high_v = _wilson_ci(values=agg.raw_values)
        success_means.append(p_hat)
        success_ci_low.append(ci_low_v)
        success_ci_high.append(ci_high_v)
        success_dots[round_number] = agg.cell_means
        agg = mcm_by_round.get(round_number, _RoundAggregate(raw_values=[], cell_means=[]))
        mean_v, std_v = _mean_and_std(values=agg.raw_values)
        mcm_means.append(mean_v)
        mcm_stds.append(std_v)
        mcm_dots[round_number] = agg.cell_means

    _write_combined_plot(
        rounds=rounds,
        success_means=success_means,
        success_ci_low=success_ci_low,
        success_ci_high=success_ci_high,
        success_by_round=success_dots,
        mcm_means=mcm_means,
        mcm_stds=mcm_stds,
        mcm_by_round=mcm_dots,
    )
    _write_success_plot(
        rounds=rounds,
        means=success_means,
        ci_low=success_ci_low,
        ci_high=success_ci_high,
        values_by_round=success_dots,
    )
    _write_mcm_plot(rounds=rounds, means=mcm_means, stds=mcm_stds, values_by_round=mcm_dots)


if __name__ == "__main__":
    main()
