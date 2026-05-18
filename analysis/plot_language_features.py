"""Plot per-feature presence frequency for Veyru and container_yard side by side.

Both scenarios are scored against Veyru's consolidated ontology
(``20260511T142136Z_full``), so the 19 category IDs are identical and
the bars are directly comparable. For each category, the bar height is
the fraction of cohort runs whose confidence score is at or above the
confidence threshold. Bars are sorted by their max prevalence across
the two scenarios so the most-shared mechanisms cluster on the left.

Cohorts:

* **Veyru** — runs labelled ``random_seed`` + ``no_ordered_easy_rounds`` (90 runs).
* **Container yard** — every ``baseline`` run (74 runs), re-scored against Veyru's
  ontology by ``analysis/plot_language_features.py``'s sibling pass-3 batch.

No win-filter is applied — every cohort run is included.
"""

import json
from pathlib import Path
from typing import NamedTuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import PercentFormatter

_VEYRU_COLOR = "#1f3a93"
_CONTAINER_COLOR = "#c1440e"
_CONFIDENCE_THRESHOLD = 0.5
_ONTOLOGY_PATH = Path("runs/veyru/_ontology/20260511T142136Z_full.json")
_OUTPUT_PATH = Path("analysis/language_features.png")
_SIDECAR_FILENAME = "communication_feature_presence.json"
_LABELS_FILENAME = "labels.json"
# Drop categories whose max prevalence across cohorts is below this threshold
# so the chart can breathe at presentation-scale fonts. At 0.5, the chart
# keeps the strongly-shared mechanisms (both cohorts ≥ 50% on at least one
# side) and drops the long tail that's rare in both.
_MIN_PREVALENCE_TO_SHOW = 0.5


def _humanize_category_id(category_id: str) -> str:
    """Convert ``snake_case_category_id`` into a sentence-case display label."""
    spaced = category_id.replace("_", " ").strip()
    if not spaced:
        return category_id
    return spaced[0].upper() + spaced[1:]


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
    labels_path = run_dir / _LABELS_FILENAME
    if not labels_path.exists():
        return []
    try:
        raw = json.loads(labels_path.read_text())
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _load_ontology_category_ids(path: Path) -> list[str]:
    """Return the ontology's category IDs in their declared order."""
    data = json.loads(path.read_text())
    categories = data.get("categories", [])
    return [
        category["id"]
        for category in categories
        if isinstance(category, dict) and isinstance(category.get("id"), str)
    ]


def _load_run_scores(run_dir: Path) -> dict[str, float] | None:
    """Load one run's ``communication_feature_presence.json`` as ``category_id -> confidence``."""
    sidecar_path = run_dir / _SIDECAR_FILENAME
    if not sidecar_path.exists():
        return None
    try:
        raw = json.loads(sidecar_path.read_text())
    except json.JSONDecodeError:
        return None
    scores: dict[str, float] = {}
    for entry in raw.get("scores", []):
        if not isinstance(entry, dict):
            continue
        category_id = entry.get("category_id")
        confidence = entry.get("confidence")
        if isinstance(category_id, str) and isinstance(confidence, (int, float)):
            scores[category_id] = float(confidence)
    return scores


def _qualifying_run_dirs(runs_root: Path, cohort: _ScenarioCohort) -> list[Path]:
    """List every run dir matching a cohort's label filter and carrying a sidecar."""
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
        if not (entry / _SIDECAR_FILENAME).exists():
            continue
        out.append(entry)
    return out


def _cohort_prevalence(run_dirs: list[Path], category_ids: list[str]) -> dict[str, float]:
    """Fraction of runs with confidence >= threshold per category."""
    if not run_dirs:
        return {category_id: 0.0 for category_id in category_ids}
    counts = {category_id: 0 for category_id in category_ids}
    n_total = 0
    for run_dir in run_dirs:
        scores = _load_run_scores(run_dir=run_dir)
        if scores is None:
            continue
        n_total += 1
        for category_id in category_ids:
            if scores.get(category_id, 0.0) >= _CONFIDENCE_THRESHOLD:
                counts[category_id] += 1
    if n_total == 0:
        return {category_id: 0.0 for category_id in category_ids}
    return {category_id: counts[category_id] / n_total for category_id in category_ids}


def _plot(
    category_ids: list[str],
    prevalence_by_cohort: dict[str, dict[str, float]],
    cohort_run_counts: dict[str, int],
) -> None:
    """Render the grouped horizontal bar chart and write it to ``_OUTPUT_PATH``.

    Categories are sorted by max prevalence across cohorts (most-shared
    mechanisms on top). Veyru bars are nudged up, container bars down,
    so each pair reads as a horizontal H. Y labels are humanized
    (snake_case → sentence case) so the chart reads without source-code
    fluency.
    """
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#4a4a4a",
            "axes.labelcolor": "#222222",
            "axes.titlecolor": "#222222",
            "xtick.color": "#222222",
            "ytick.color": "#222222",
            "font.size": 26,
            "axes.titlesize": 34,
            "axes.labelsize": 28,
            "xtick.labelsize": 24,
            "ytick.labelsize": 24,
            "legend.fontsize": 24,
        }
    )

    max_per_category = {
        category_id: max(prevalence_by_cohort[cohort.name][category_id] for cohort in _COHORTS)
        for category_id in category_ids
    }
    visible_categories = [
        category_id
        for category_id in category_ids
        if max_per_category[category_id] >= _MIN_PREVALENCE_TO_SHOW
    ]
    ordered_categories = sorted(
        visible_categories, key=lambda category_id: max_per_category[category_id]
    )
    y_positions = np.arange(len(ordered_categories))
    bar_height = 0.4
    fig, ax = plt.subplots(figsize=(20, max(10, len(ordered_categories) * 0.95)))
    fig.patch.set_facecolor("white")
    for offset, cohort in zip((bar_height / 2, -bar_height / 2), _COHORTS):
        widths = [
            prevalence_by_cohort[cohort.name][category_id] for category_id in ordered_categories
        ]
        label = f"{cohort.display_name} (n={cohort_run_counts[cohort.name]})"
        ax.barh(
            y_positions + offset,
            widths,
            height=bar_height,
            color=cohort.color,
            edgecolor="white",
            linewidth=0.8,
            label=label,
        )
        for y_pos, width in zip(y_positions + offset, widths):
            if width <= 0.0:
                continue
            ax.text(
                width + 0.012,
                y_pos,
                f"{width:.0%}",
                va="center",
                ha="left",
                fontsize=18,
                color=cohort.color,
            )

    ax.set_xlim(0, 1.08)
    ax.set_yticks(y_positions)
    ax.set_yticklabels([_humanize_category_id(c) for c in ordered_categories])
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax.set_xlabel(f"Share of cohort runs with confidence ≥ {_CONFIDENCE_THRESHOLD:g}")
    ax.grid(axis="x", alpha=0.25, linestyle="--", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)

    ax.set_title(
        "Shared language-emergence mechanisms\nacross scenarios",
        loc="center",
        pad=22,
        fontweight="semibold",
    )

    legend = ax.legend(
        loc="lower right",
        frameon=True,
        framealpha=0.95,
        edgecolor="#cccccc",
    )
    legend.get_frame().set_linewidth(0.8)
    fig.tight_layout()
    fig.savefig(
        _OUTPUT_PATH,
        dpi=200,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.1,
    )
    plt.close(fig)
    print(f"Wrote {_OUTPUT_PATH} ({len(ordered_categories)} of {len(category_ids)} categories)")


def main() -> None:
    runs_root = Path("runs")
    category_ids = _load_ontology_category_ids(path=_ONTOLOGY_PATH)
    prevalence_by_cohort: dict[str, dict[str, float]] = {}
    cohort_run_counts: dict[str, int] = {}
    for cohort in _COHORTS:
        run_dirs = _qualifying_run_dirs(runs_root=runs_root, cohort=cohort)
        cohort_run_counts[cohort.name] = len(run_dirs)
        prevalence_by_cohort[cohort.name] = _cohort_prevalence(
            run_dirs=run_dirs, category_ids=category_ids
        )
        print(f"{cohort.display_name}: {len(run_dirs)} runs")
    _plot(
        category_ids=category_ids,
        prevalence_by_cohort=prevalence_by_cohort,
        cohort_run_counts=cohort_run_counts,
    )


if __name__ == "__main__":
    main()
