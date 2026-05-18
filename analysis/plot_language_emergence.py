"""Plot per-round perplexity and mean-chars-per-message across Veyru and container_yard.

Two side-by-side panels, two lines per panel (one per scenario). Shows that
language emergence — rising per-token surprisal and compressing message length
— occurs in both scenarios. Veyru is filtered to the
``random_seed`` + ``no_ordered_easy_rounds`` cohort; container_yard_stacking
uses every ``baseline`` run.
"""

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import matplotlib.pyplot as plt
from matplotlib.axes import Axes

_PERPLEXITY_METRIC = "perplexity"
_MCM_METRIC = "mean_chars_per_message"
_OUTPUT_PATH = Path("analysis/language_emergence.png")

_VEYRU_COLOR = "#1f3a93"
_CONTAINER_COLOR = "#c1440e"


class _ScenarioCohort(NamedTuple):
    """One scenario's run-filter spec + display style."""

    name: str
    display_name: str
    required_labels: tuple[str, ...]
    color: str


_COHORTS: tuple[_ScenarioCohort, ...] = (
    _ScenarioCohort(
        name="veyru",
        display_name="Veyru",
        required_labels=("random_seed", "no_ordered_easy_rounds"),
        color=_VEYRU_COLOR,
    ),
    _ScenarioCohort(
        name="container_yard_stacking",
        display_name="Container yard",
        required_labels=("baseline",),
        color=_CONTAINER_COLOR,
    ),
)


def _read_labels(run_dir: Path) -> list[str]:
    """Return the run's ``labels.json`` as a list of strings (empty if missing/malformed)."""
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


def _qualifying_run_dirs(runs_root: Path, cohort: _ScenarioCohort) -> list[Path]:
    """List every run dir matching a cohort's label filter and carrying a report."""
    out: list[Path] = []
    scenario_dir = runs_root / cohort.name
    if not scenario_dir.is_dir():
        return out
    for entry in sorted(scenario_dir.iterdir()):
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        labels = _read_labels(run_dir=entry)
        if not all(required in labels for required in cohort.required_labels):
            continue
        if not (entry / f"{cohort.name}_report.json").exists():
            continue
        out.append(entry)
    return out


def _mean_and_std(values: list[float]) -> tuple[float, float]:
    """Return ``(mean, sample_standard_deviation)`` from a list of numbers."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance)


class _RoundStat(NamedTuple):
    """One round's aggregated mean + standard deviation across runs."""

    mean: float
    std: float


def _aggregate_per_round(
    run_dirs: list[Path], scenario_name: str, metric_name: str
) -> dict[int, _RoundStat]:
    """Aggregate per-round mean + std across every supplied run."""
    raw_by_round: dict[int, list[float]] = defaultdict(list)
    for run_dir in run_dirs:
        report_path = run_dir / f"{scenario_name}_report.json"
        try:
            report = json.loads(report_path.read_text())
        except json.JSONDecodeError:
            continue
        for round_number, value in _per_round_observations(report=report, metric_name=metric_name):
            raw_by_round[round_number].append(value)
    out: dict[int, _RoundStat] = {}
    for round_number, values in raw_by_round.items():
        mean, std = _mean_and_std(values=values)
        out[round_number] = _RoundStat(mean=mean, std=std)
    return out


def _plot_metric_panel(
    ax: Axes,
    metric_name: str,
    ylabel: str,
    panel_title: str,
    stats_by_cohort: dict[str, dict[int, _RoundStat]],
) -> None:
    """Render one panel: a line+std-band per cohort over rounds."""
    for cohort in _COHORTS:
        stats = stats_by_cohort[cohort.name]
        rounds = sorted(stats.keys())
        if not rounds:
            continue
        means = [stats[r].mean for r in rounds]
        stds = [stats[r].std for r in rounds]
        lower = [m - s for m, s in zip(means, stds)]
        upper = [m + s for m, s in zip(means, stds)]
        ax.fill_between(rounds, lower, upper, color=cohort.color, alpha=0.15)
        ax.plot(
            rounds,
            means,
            marker="o",
            linewidth=2,
            color=cohort.color,
            label=cohort.display_name,
        )
    ax.set_xlabel("Round")
    ax.set_ylabel(ylabel, color="black")
    ax.tick_params(axis="y", labelcolor="black")
    ax.set_title(panel_title)
    ax.grid(axis="y", alpha=0.3)
    all_rounds: set[int] = set()
    for stats in stats_by_cohort.values():
        all_rounds.update(stats.keys())
    if all_rounds:
        ax.set_xticks(sorted(all_rounds))
    if metric_name == _MCM_METRIC:
        ax.set_ylim(bottom=0)
    ax.legend(loc="best")


def main() -> None:
    runs_root = Path("runs")
    perplexity_by_cohort: dict[str, dict[int, _RoundStat]] = {}
    mcm_by_cohort: dict[str, dict[int, _RoundStat]] = {}
    for cohort in _COHORTS:
        run_dirs = _qualifying_run_dirs(runs_root=runs_root, cohort=cohort)
        print(f"{cohort.display_name}: {len(run_dirs)} qualifying runs")
        perplexity_by_cohort[cohort.name] = _aggregate_per_round(
            run_dirs=run_dirs,
            scenario_name=cohort.name,
            metric_name=_PERPLEXITY_METRIC,
        )
        mcm_by_cohort[cohort.name] = _aggregate_per_round(
            run_dirs=run_dirs, scenario_name=cohort.name, metric_name=_MCM_METRIC
        )

    fig, (ax_perplexity, ax_mcm) = plt.subplots(1, 2, figsize=(14, 5))
    _plot_metric_panel(
        ax=ax_perplexity,
        metric_name=_PERPLEXITY_METRIC,
        ylabel="Perplexity (nats per token, gpt2)",
        panel_title="Per-token perplexity rises",
        stats_by_cohort=perplexity_by_cohort,
    )
    _plot_metric_panel(
        ax=ax_mcm,
        metric_name=_MCM_METRIC,
        ylabel="Mean chars per message",
        panel_title="Message length compresses",
        stats_by_cohort=mcm_by_cohort,
    )
    fig.tight_layout()
    fig.savefig(_OUTPUT_PATH, dpi=200)
    plt.close(fig)
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
