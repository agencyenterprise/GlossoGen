"""Test whether a partner's shortfall affects the two governance arms differently.

The quantity of interest is a difference of differences: how much the outcome
moves when the scripted partner falls short, under covenant, minus how much it
moves under rule. A main-effect comparison cannot answer this — covenant and
rule can look identical overall while responding oppositely to a partner who
breaks the obligation, which is exactly what the covenant's persistence clause
predicts.

The null is that a run's cell label carries no information, so labels are
permuted across all four cells and the interaction recomputed. Permutation is at
the run level: rounds inside a run are correlated and permuting them would
inflate significance.

Usage:
    VIRTUAL_ENV= uv run --no-sync python -m \
        glossogen.scenarios.repo_stewardship.scripts.interaction_test \
        ./runs/repo_stewardship --since 1787023800
"""

import argparse
import random
import statistics
from pathlib import Path
from typing import NamedTuple

from glossogen.scenarios.repo_stewardship.scripts.summarize_runs import RunSummary, summarize_run

PERMUTATIONS = 20000
RNG_SEED = 20260818

OUTCOMES = (
    "developer_releases",
    "repairs",
    "disclosures",
    "critical_defects_remaining",
    "tickets_completed",
    "final_integrity_score",
)

RULE_UPHOLD = "rule_puphold"
RULE_DEFECT = "rule_pdefect"
COVENANT_UPHOLD = "covenant_puphold"
COVENANT_DEFECT = "covenant_pdefect"


class InteractionResult(NamedTuple):
    """One outcome's difference-of-differences across the 2x2."""

    outcome: str
    rule_shift: float
    covenant_shift: float
    interaction: float
    p_value: float


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean, or 0.0 for an empty sample."""
    if not values:
        return 0.0
    return statistics.fmean(values)


def _interaction(cells: dict[str, list[float]]) -> tuple[float, float, float]:
    """Return (rule shift, covenant shift, their difference)."""
    rule_shift = _mean(values=cells[RULE_DEFECT]) - _mean(values=cells[RULE_UPHOLD])
    covenant_shift = _mean(values=cells[COVENANT_DEFECT]) - _mean(values=cells[COVENANT_UPHOLD])
    return (rule_shift, covenant_shift, covenant_shift - rule_shift)


def test_outcome(
    summaries: list[RunSummary],
    outcome: str,
    rng: random.Random,
) -> InteractionResult | None:
    """Return the interaction and its permutation p-value for one outcome."""
    cells: dict[str, list[float]] = {
        name: [float(getattr(s, outcome)) for s in summaries if s.condition == name]
        for name in (RULE_UPHOLD, RULE_DEFECT, COVENANT_UPHOLD, COVENANT_DEFECT)
    }
    if any(not values for values in cells.values()):
        return None
    rule_shift, covenant_shift, observed = _interaction(cells=cells)
    labels = [s.condition for s in summaries if s.condition in cells]
    values = [float(getattr(s, outcome)) for s in summaries if s.condition in cells]
    extreme = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(labels)
        shuffled: dict[str, list[float]] = {name: [] for name in cells}
        for label, value in zip(labels, values, strict=True):
            shuffled[label].append(value)
        if abs(_interaction(cells=shuffled)[2]) >= abs(observed):
            extreme += 1
    return InteractionResult(
        outcome=outcome,
        rule_shift=rule_shift,
        covenant_shift=covenant_shift,
        interaction=observed,
        p_value=(extreme + 1) / (PERMUTATIONS + 1),
    )


def main() -> None:
    """Print the difference-of-differences for every outcome in the 2x2."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_dir", type=Path)
    parser.add_argument("--since", type=int)
    args = parser.parse_args()

    summaries: list[RunSummary] = []
    for run_dir in sorted(args.scenario_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        if args.since is not None and run_dir.name.isdigit() and int(run_dir.name) < args.since:
            continue
        summary = summarize_run(run_dir=run_dir)
        if summary is None or not summary.completed or summary.rounds_played == 0:
            continue
        summaries.append(summary)

    for name in (RULE_UPHOLD, RULE_DEFECT, COVENANT_UPHOLD, COVENANT_DEFECT):
        print(f"  {name}: n={sum(1 for s in summaries if s.condition == name)}")
    print()
    header = f"{'outcome':<28}{'rule shift':>12}{'cov shift':>12}" f"{'interaction':>13}{'p':>9}"
    print(header)
    print("-" * len(header))
    rng = random.Random(RNG_SEED)
    for outcome in OUTCOMES:
        result = test_outcome(summaries=summaries, outcome=outcome, rng=rng)
        if result is None:
            continue
        print(
            f"{result.outcome:<28}{result.rule_shift:>12.2f}{result.covenant_shift:>12.2f}"
            f"{result.interaction:>13.2f}{result.p_value:>9.4f}"
        )
    print()
    print("shift = defecting-partner cell minus upholding-partner cell")
    print("interaction = covenant shift minus rule shift")


if __name__ == "__main__":
    main()
