"""Compare repo-stewardship arms on simulation-level outcomes.

The simulation is the experimental unit, so every outcome here is one value per
run and the tests permute run labels, never rounds. Permuting rounds would treat
correlated observations inside a run as independent — a defect repaired in round
3 stays repaired, and budget spent early constrains every later round — and would
inflate significance.

Reports, for each outcome and each pairwise contrast, the observed difference in
means, a two-sided permutation p-value, and a bootstrap confidence interval for
the difference.

Usage:
    VIRTUAL_ENV= uv run --no-sync python -m \
        glossogen.scenarios.repo_stewardship.scripts.compare_arms ./runs/repo_stewardship \
        --since 1787000000
"""

import argparse
import random
import statistics
from pathlib import Path
from typing import NamedTuple

from glossogen.scenarios.repo_stewardship.scripts.summarize_runs import RunSummary, summarize_run

PERMUTATIONS = 20000
BOOTSTRAP_SAMPLES = 20000
RNG_SEED = 20260817

OUTCOMES = (
    ("developer_releases", "known critical defects shipped by the developer"),
    ("reviewer_releases", "known critical defects approved by the reviewer"),
    ("joint_breaches", "both agents releasing the same defect"),
    ("repairs", "defects repaired"),
    ("disclosures", "defects formally disclosed"),
    ("false_blocks", "acceptable changes blocked"),
    ("false_approvals", "unacceptable changes approved"),
    ("unreviewed_tickets", "tickets that never received a decision"),
    ("tickets_completed", "tickets delivered"),
    ("critical_defects_remaining", "critical defects left in the repository"),
    ("final_integrity_score", "final integrity score"),
)


class ContrastResult(NamedTuple):
    """One pairwise comparison on one outcome."""

    outcome: str
    arm_a: str
    arm_b: str
    mean_a: float
    mean_b: float
    difference: float
    p_value: float
    ci_low: float
    ci_high: float


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean, or 0.0 for an empty sample."""
    if not values:
        return 0.0
    return statistics.fmean(values)


def permutation_p_value(
    sample_a: list[float],
    sample_b: list[float],
    rng: random.Random,
) -> float:
    """Return the two-sided permutation p-value for a difference in means."""
    observed = abs(_mean(values=sample_a) - _mean(values=sample_b))
    pooled = sample_a + sample_b
    split = len(sample_a)
    at_least_as_extreme = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(pooled)
        difference = abs(_mean(values=pooled[:split]) - _mean(values=pooled[split:]))
        if difference >= observed:
            at_least_as_extreme += 1
    return (at_least_as_extreme + 1) / (PERMUTATIONS + 1)


def bootstrap_interval(
    sample_a: list[float],
    sample_b: list[float],
    rng: random.Random,
) -> tuple[float, float]:
    """Return a percentile bootstrap interval for the difference in means."""
    differences: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        draw_a = [rng.choice(sample_a) for _ in sample_a]
        draw_b = [rng.choice(sample_b) for _ in sample_b]
        differences.append(_mean(values=draw_a) - _mean(values=draw_b))
    differences.sort()
    low = differences[int(0.025 * len(differences))]
    high = differences[int(0.975 * len(differences)) - 1]
    return (low, high)


def compare(
    summaries: list[RunSummary],
    arm_a: str,
    arm_b: str,
    outcome: str,
    rng: random.Random,
) -> ContrastResult | None:
    """Return one contrast, or None when either arm has no completed runs."""
    sample_a = [float(getattr(s, outcome)) for s in summaries if s.condition == arm_a]
    sample_b = [float(getattr(s, outcome)) for s in summaries if s.condition == arm_b]
    if not sample_a or not sample_b:
        return None
    return ContrastResult(
        outcome=outcome,
        arm_a=arm_a,
        arm_b=arm_b,
        mean_a=_mean(values=sample_a),
        mean_b=_mean(values=sample_b),
        difference=_mean(values=sample_a) - _mean(values=sample_b),
        p_value=permutation_p_value(sample_a=sample_a, sample_b=sample_b, rng=rng),
        ci_low=bootstrap_interval(sample_a=sample_a, sample_b=sample_b, rng=rng)[0],
        ci_high=bootstrap_interval(sample_a=sample_a, sample_b=sample_b, rng=rng)[1],
    )


def main() -> None:
    """Print per-arm means and pairwise contrasts for the selected runs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_dir", type=Path)
    parser.add_argument(
        "--since",
        type=int,
        help="only include runs whose directory name (a unix timestamp) is at least this",
    )
    args = parser.parse_args()

    summaries: list[RunSummary] = []
    for run_dir in sorted(args.scenario_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        if args.since is not None and run_dir.name.isdigit() and int(run_dir.name) < args.since:
            continue
        summary = summarize_run(run_dir=run_dir)
        # An incomplete run is a missing observation, not a zero: including it
        # would score an interrupted simulation as a well-behaved one.
        if summary is None or not summary.completed or summary.rounds_played == 0:
            continue
        summaries.append(summary)

    arms = sorted({s.condition for s in summaries})
    print(f"runs included: {len(summaries)}")
    for arm in arms:
        print(f"  {arm}: n={sum(1 for s in summaries if s.condition == arm)}")
    print()

    header = f"{'outcome':<28} " + " ".join(f"{arm:>12}" for arm in arms)
    print(header)
    print("-" * len(header))
    for outcome, _ in OUTCOMES:
        cells: list[str] = []
        for arm in arms:
            values = [float(getattr(s, outcome)) for s in summaries if s.condition == arm]
            cells.append(f"{_mean(values=values):>12.2f}")
        print(f"{outcome:<28} " + " ".join(cells))

    # Derive contrasts from the arms actually present rather than a fixed list, so
    # adding a cell (a retrieval-off variant, a mechanism arm) does not silently
    # drop its comparisons.
    contrasts = [(arm_a, arm_b) for index, arm_a in enumerate(arms) for arm_b in arms[index + 1 :]]
    for arm_a, arm_b in contrasts:
        print(f"\n=== {arm_a} vs {arm_b} ===")
        print(f"{'outcome':<28} {'mean_a':>8} {'mean_b':>8} {'diff':>8} {'p':>8}  95% CI")
        rng = random.Random(RNG_SEED)
        for outcome, _ in OUTCOMES:
            result = compare(
                summaries=summaries, arm_a=arm_a, arm_b=arm_b, outcome=outcome, rng=rng
            )
            if result is None:
                continue
            print(
                f"{result.outcome:<28} {result.mean_a:>8.2f} {result.mean_b:>8.2f} "
                f"{result.difference:>8.2f} {result.p_value:>8.4f}  "
                f"[{result.ci_low:.2f}, {result.ci_high:.2f}]"
            )


if __name__ == "__main__":
    main()
