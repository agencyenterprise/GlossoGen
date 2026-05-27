"""Static export of the Streamlit Multi-swap → Cohort-overlay per-phase chart.

Reproduces a fixed configuration of the cohort-overlay view:

  - budget 250
  - per-phase round success (pooled / micro-average across replicas)
  - replica dots hidden
  - ``all_agents_idle`` rounds excluded from round-success

Three series across the four 10-round phases (A: 1-10, B: 11-20, C: 21-30,
D: 31-40):

  - budget=250 multi-swap, postmortem always on (solid) + its no-swap baseline (dashed)
  - budget=250 multi-swap, postmortem off after Phase A (solid, no baseline)

Cohort selection, colour assignment, idle exclusion, and the pooled per-phase
aggregation all reuse the Streamlit tab's own functions
(``analysis.results_viewer.multi_swap_tab``) so this static plot stays in sync
with what the app renders.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt  # noqa: E402

from analysis.results_viewer import multi_swap_tab as mst  # noqa: E402
from analysis.results_viewer.run_catalog import EvaluatedRun, list_evaluated_runs  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
PHASE_LABELS = [
    "Phase A\nrounds 1–10",
    "Phase B\nrounds 11–20",
    "Phase C\nrounds 21–30",
    "Phase D\nrounds 31–40",
]
SELECTED_BUDGETS = ("budget=250",)


def _concise_label(cohort: mst._EffectiveCohort, n: int) -> str:
    """Readable legend label: experiment/baseline + budget + postmortem schedule."""
    labels = cohort.contributing_label_sets[0]
    budget = next((label for label in labels if label.startswith("budget=")), "budget=?")
    pair_key = mst._cohort_pair_key(labels=labels)
    if pair_key is not None and pair_key.pm_schedule == mst._PM_SCHEDULE_ALWAYS:
        pm = "pm always"
    else:
        pm = "pm off after A"
    kind = "no-swap baseline" if cohort.is_baseline else "multi-swap"
    return f"{kind} · {budget} · {pm} (n={n})"


def _build_round_entries(
    evaluated: list[EvaluatedRun], cohort: mst._EffectiveCohort
) -> list[mst._RunRoundEntry]:
    """Gather finished runs for a cohort, dropping idle-ended rounds."""
    entries: list[mst._RunRoundEntry] = []
    for run in mst._gather_runs_for_effective_cohort(evaluated=evaluated, cohort=cohort):
        jsonl = run.run_dir / f"{run.scenario_name}.jsonl"
        round_data = mst._read_run_round_data(jsonl_path=jsonl)
        if not round_data.simulation_ended:
            continue
        success = mst._drop_idle_rounds(success=round_data.success, triggers=round_data.triggers)
        entries.append(mst._RunRoundEntry(success=success, run_id=run.run_id, url=""))
    return entries


def _experiment_displays(
    display_to_labels: dict[str, frozenset[str]], pm_schedule: str
) -> list[str]:
    """Multi-swap experiment cohort displays for both budgets under one
    postmortem schedule, in budget order."""
    displays: list[str] = []
    for budget in SELECTED_BUDGETS:
        display = mst._find_experiment_display(
            display_to_labels=display_to_labels, budget=budget, pm_schedule=pm_schedule
        )
        if display is not None:
            displays.append(display)
    return displays


def _resolve_cohorts(
    evaluated: list[EvaluatedRun],
) -> list[mst._EffectiveCohort]:
    """Build the plotted cohorts: budgets 250+450 pm-always multi-swap lines
    auto-paired with their no-swap baselines (dashed), plus the budgets 250+450
    pm-off-after-Phase-A multi-swap lines on their own (solid, no baseline)."""
    cohort_label_sets = mst._discover_cohort_label_sets(evaluated=evaluated)
    display_to_labels = {
        mst._label_set_display(labels=labels): labels for labels, _ in cohort_label_sets
    }
    pm_always = _experiment_displays(
        display_to_labels=display_to_labels, pm_schedule=mst._PM_SCHEDULE_ALWAYS
    )
    expanded, _ = mst._expand_with_baseline_pairs(
        selected_displays=pm_always, display_to_labels=display_to_labels
    )
    pm_phase_a = _experiment_displays(
        display_to_labels=display_to_labels, pm_schedule=mst._PM_SCHEDULE_PHASE_A_ONLY
    )
    return mst._resolve_effective_cohorts(
        expanded_displays=expanded + pm_phase_a,
        display_to_labels=display_to_labels,
        merge_budgets=False,
    )


def main() -> None:
    """Resolve the fixed cohort config, compute pooled per-phase stats, save PNG."""
    runs_dir = Path(os.environ.get("SCHMIDT_RUNS_DIR", REPO_ROOT / "runs")).resolve()
    evaluated = [
        run for run in list_evaluated_runs(runs_dir=runs_dir) if run.scenario_name == "veyru"
    ]
    cohorts = _resolve_cohorts(evaluated=evaluated)
    colors = mst._assign_effective_cohort_colors(cohorts=cohorts)

    phase_xs = list(range(len(mst._PHASE_ORDER)))
    _, ax = plt.subplots(figsize=(12, 7.5))
    for index, cohort in enumerate(cohorts):
        entries = _build_round_entries(evaluated=evaluated, cohort=cohort)
        if not entries:
            print(f"  {cohort.display}: no finished runs, skipping")
            continue
        means, ses, ns = mst._per_phase_round_success_stats(cohort=entries)
        offset = (index - (len(cohorts) - 1) / 2) * 0.06
        color = colors[cohort.display]
        if cohort.is_baseline:
            linestyle = "--"
            marker_face = "white"
        else:
            linestyle = "-"
            marker_face = color
        xs = [x + offset for x in phase_xs]
        ax.errorbar(
            xs,
            means,
            yerr=ses,
            color=color,
            linestyle=linestyle,
            marker="o",
            markersize=11,
            linewidth=2.0,
            markeredgecolor=color,
            markeredgewidth=1.5,
            markerfacecolor=marker_face,
            capsize=4,
            label=_concise_label(cohort=cohort, n=len(entries)),
        )
        rounds_per_phase = " ".join(f"{p}:n={n}" for p, n in zip(mst._PHASE_ORDER, ns))
        print(f"{cohort.display}")
        print(
            f"    A={means[0]:.2f} B={means[1]:.2f} C={means[2]:.2f} D={means[3]:.2f}"
            f"  (pooled rounds {rounds_per_phase})"
        )

    ax.set_xticks(phase_xs)
    ax.set_xticklabels(PHASE_LABELS, fontsize=14)
    ax.tick_params(axis="y", labelsize=13)
    ax.set_ylabel("Pooled round success within phase (idle rounds excluded)", fontsize=14)
    ax.set_ylim(0, 1.05)
    ax.set_xlim(-0.5, len(mst._PHASE_ORDER) - 0.5)
    ax.set_title(
        "Multi-swap (solid) vs no-swap baseline (dashed)\n"
        "see legend for budget & postmortem schedule",
        fontsize=15,
    )
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="lower right", frameon=True, fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    out_path = OUT_DIR / "multiswap_rc40_phases.png"
    plt.savefig(out_path, dpi=150)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
