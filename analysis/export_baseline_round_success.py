"""Export the baseline round-success-vs-budget data behind the Streamlit baseline tab.

Reproduces exactly the cohort the baseline tab plots — scenario runs labeled
``baseline`` (closed-model frontier) or ``baseline_oss`` (open-weight), carrying
a ``round_time_budget_seconds`` knob and a ``round_success`` measurement — and
writes it in a shape suited to mixed-effects modelling.

Judge-mismatch filter: applies only to runs launched before
``--corrected-judge-cutoff`` (default 2026-06-02). Those older runs were scored
by the pre-correction judge, so each is gated on its ``judge_replay.json``
sidecar — any run with at least one previously-accepted stabilization that flips
to rejected under the corrected prompt is dropped (mirrors the baseline tab's
judge-replay slider at 0%), and runs without a sidecar are dropped unless
``--allow-missing-sidecar`` is set. Runs launched on/after the cutoff were scored
by the corrected judge live during the simulation, so they need no replay
validation and are included without a sidecar.

Three output tables:

- ``run_level`` — one row per run (the replica dots on the chart). The Bernoulli
  numerator/denominator (``round_success_count`` / ``total_rounds``) supports a
  binomial GLMM ``cbind(successes, failures) ~ ...`` and the fraction supports a
  beta/linear model.
- ``round_level`` — one row per (run, round); ``success`` is the 0/1 outcome the
  round-success metric recorded. This is the unit for a logistic mixed model
  ``success ~ log_budget * model_class * postmortem + (1 | model) + (1 | run_id)``.
- ``budget_aggregate`` — per (model, postmortem, kind, budget) mean ± std of the
  success fraction; a sanity check against the plotted mean ± std bands.

Writes one CSV per table, and (when ``openpyxl`` is importable) a single
multi-sheet ``.xlsx`` workbook.
"""

import argparse
import importlib.util
import logging
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from analysis.results_viewer.baseline_data import build_baseline_run
from analysis.results_viewer.judge_replay_filter import flip_ratio_by_run_id
from analysis.results_viewer.run_catalog import EvaluatedRun, list_evaluated_runs

logger = logging.getLogger(__name__)

_ROUND_SUCCESS_METRIC = "round_success"
_RANDOM_SEED_LABEL = "random_seed"
_NO_ORDERED_EASY_ROUNDS_LABEL = "no_ordered_easy_rounds"
_KIND_TO_MODEL_CLASS = {"baseline": "closed", "baseline_oss": "open"}


class JoinedRun(NamedTuple):
    """A baseline run paired with its source ``EvaluatedRun`` and judge-replay ratio.

    ``flip_ratio`` is ``None`` when the run has no ``judge_replay.json`` sidecar
    (the slider treats that as passing); otherwise it is
    ``flipped_true_to_false / old_true_count``.
    """

    evaluated: EvaluatedRun
    flip_ratio: float | None


def _collect_joined_runs(evaluated_runs: list[EvaluatedRun], scenario_name: str) -> list[JoinedRun]:
    """Return the baseline/baseline_oss runs for ``scenario_name`` with their flip ratios.

    A run is included only when ``build_baseline_run`` accepts it — i.e. it
    carries a baseline label, a budget knob, and a ``round_success`` measurement.
    """
    ratio_map = flip_ratio_by_run_id(evaluated=evaluated_runs)
    joined: list[JoinedRun] = []
    for run in evaluated_runs:
        if run.scenario_name != scenario_name:
            continue
        if build_baseline_run(evaluated=run) is None:
            continue
        joined.append(JoinedRun(evaluated=run, flip_ratio=ratio_map.get(run.run_id)))
    return joined


def _passes_judge_filter(flip_ratio: float | None, threshold: float) -> bool:
    """Mirror the judge-replay slider: pass when no sidecar or flip ratio <= threshold."""
    if flip_ratio is None:
        return True
    return flip_ratio <= threshold


def _is_canonical(labels: list[str]) -> bool:
    """True for the canonical-design cohort: fixed seed and default easy-round skeleton.

    Canonical runs carry neither the ``random_seed`` label (so they used the
    fixed ``seed=42``) nor the ``no_ordered_easy_rounds`` label (so rounds
    1/2/3/6/13 are the default forced single-stage warmups).
    """
    if _RANDOM_SEED_LABEL in labels:
        return False
    return _NO_ORDERED_EASY_ROUNDS_LABEL not in labels


def _executed_with_corrected_judge(evaluated: EvaluatedRun, cutoff: date) -> bool:
    """True when the run was launched on/after ``cutoff`` (local date).

    The stabilization judge runs live during the simulation, so a run launched
    on/after the date the judge prompt was corrected was scored with the
    corrected prompt and needs no judge-replay validation. The run directory
    name is the launch unix timestamp; its local date is the execution date.
    """
    return datetime.fromtimestamp(evaluated.run_timestamp).date() >= cutoff


def _apply_cohort_filters(
    joined_runs: list[JoinedRun],
    judge_flip_threshold: float,
    require_sidecar: bool,
    canonical_only: bool,
    corrected_judge_cutoff: date,
) -> list[JoinedRun]:
    """Filter by judge soundness and canonical design.

    Runs launched on/after ``corrected_judge_cutoff`` were scored with the
    corrected judge prompt at execution time, so they bypass the judge-replay
    flip filter and the sidecar requirement entirely. Older runs must clear the
    flip threshold (and, when ``require_sidecar``, carry a replay sidecar).
    """
    out: list[JoinedRun] = []
    for joined in joined_runs:
        if not _executed_with_corrected_judge(
            evaluated=joined.evaluated, cutoff=corrected_judge_cutoff
        ):
            if not _passes_judge_filter(joined.flip_ratio, judge_flip_threshold):
                continue
            if require_sidecar and joined.flip_ratio is None:
                continue
        if canonical_only:
            baseline = build_baseline_run(evaluated=joined.evaluated)
            if baseline is None or not _is_canonical(labels=baseline.labels):
                continue
        out.append(joined)
    return out


def _round_success_per_round(evaluated: EvaluatedRun) -> list[tuple[int, float, str]]:
    """Return ``(round_number, value, note)`` from the run's ``round_success`` measurement."""
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == _ROUND_SUCCESS_METRIC:
            return [(obs.round_number, obs.value, obs.note) for obs in measurement.per_round]
    return []


def _build_run_level_frame(joined_runs: list[JoinedRun]) -> pd.DataFrame:
    """One row per run: covariates plus the Bernoulli numerator/denominator."""
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        baseline = build_baseline_run(evaluated=joined.evaluated)
        if baseline is None:
            continue
        fraction = None
        if baseline.total_rounds > 0:
            fraction = baseline.round_success / baseline.total_rounds
        rows.append(
            {
                "run_id": baseline.run_id,
                "scenario": joined.evaluated.scenario_name,
                "model": baseline.model,
                "model_class": _KIND_TO_MODEL_CLASS[baseline.kind],
                "postmortem": baseline.postmortem_enabled,
                "round_time_budget_seconds": baseline.budget,
                "total_rounds": baseline.total_rounds,
                "round_success_count": baseline.round_success,
                "round_success_fraction": fraction,
                "labels": "|".join(baseline.labels),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        by=["model_class", "model", "postmortem", "round_time_budget_seconds", "run_id"]
    ).reset_index(drop=True)


def _build_round_level_frame(joined_runs: list[JoinedRun]) -> pd.DataFrame:
    """Long format: one row per (run, round) with the 0/1 success outcome."""
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        baseline = build_baseline_run(evaluated=joined.evaluated)
        if baseline is None:
            continue
        for round_number, value, note in _round_success_per_round(evaluated=joined.evaluated):
            rows.append(
                {
                    "run_id": baseline.run_id,
                    "scenario": joined.evaluated.scenario_name,
                    "model": baseline.model,
                    "model_class": _KIND_TO_MODEL_CLASS[baseline.kind],
                    "postmortem": baseline.postmortem_enabled,
                    "round_time_budget_seconds": baseline.budget,
                    "round_number": round_number,
                    "success": int(round(value)),
                    "success_raw": value,
                    "note": note,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(by=["run_id", "round_number"]).reset_index(drop=True)


def _build_budget_aggregate_frame(run_level: pd.DataFrame) -> pd.DataFrame:
    """Per (model, postmortem, kind, budget) mean ± std of the success fraction."""
    if run_level.empty:
        return run_level
    grouped = run_level.groupby(
        ["model_class", "model", "postmortem", "round_time_budget_seconds"],
        as_index=False,
    ).agg(
        n=("round_success_fraction", "size"),
        mean_success_fraction=("round_success_fraction", "mean"),
        # population std (ddof=0) to match the chart's n=1 -> 0.0 error bars.
        std_success_fraction=("round_success_fraction", lambda s: s.std(ddof=0)),
        min_success_fraction=("round_success_fraction", "min"),
        max_success_fraction=("round_success_fraction", "max"),
        mean_success_count=("round_success_count", "mean"),
    )
    return grouped.sort_values(
        by=["model_class", "model", "postmortem", "round_time_budget_seconds"]
    ).reset_index(drop=True)


def _write_csvs(frames: dict[str, pd.DataFrame], output_dir: Path, stem: str) -> list[Path]:
    """Write one CSV per frame under ``output_dir``; return the written paths."""
    written: list[Path] = []
    for name, frame in frames.items():
        path = output_dir / f"{stem}_{name}.csv"
        frame.to_csv(path, index=False)
        written.append(path)
    return written


def _write_xlsx(frames: dict[str, pd.DataFrame], output_dir: Path, stem: str) -> Path | None:
    """Write all frames to one multi-sheet workbook; return path or ``None`` if no engine."""
    if importlib.util.find_spec("openpyxl") is None:
        logger.warning("openpyxl not importable — skipping .xlsx, CSVs were written.")
        return None
    path = output_dir / f"{stem}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in frames.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for the exporter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--scenario", type=str, default="veyru")
    parser.add_argument("--output-dir", type=Path, default=Path("analysis/exports"))
    parser.add_argument("--stem", type=str, default="baseline_round_success")
    parser.add_argument(
        "--judge-flip-threshold",
        type=float,
        default=0.0,
        help=(
            "Maximum judge-replay flip ratio a run may have to be kept "
            "(0.0 mirrors the slider at 0%: drop any run with >=1 flip)."
        ),
    )
    parser.add_argument(
        "--allow-missing-sidecar",
        action="store_true",
        help="Keep runs without a judge_replay.json sidecar (default: require one).",
    )
    parser.add_argument(
        "--all-designs",
        action="store_true",
        help=(
            "Keep every seed mode / easy-round skeleton (default: canonical only "
            "— fixed seed and default easy-round warmups)."
        ),
    )
    parser.add_argument(
        "--corrected-judge-cutoff",
        type=date.fromisoformat,
        default=date(2026, 6, 2),
        help=(
            "Local date (YYYY-MM-DD) on/after which runs were executed with the "
            "corrected judge prompt; these bypass the judge-replay flip filter and "
            "sidecar requirement. Defaults to 2026-06-02."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Build the three frames, apply the judge-mismatch filter, and write outputs."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    evaluated_runs = list_evaluated_runs(runs_dir=args.runs_dir)
    joined = _collect_joined_runs(evaluated_runs=evaluated_runs, scenario_name=args.scenario)
    kept = _apply_cohort_filters(
        joined_runs=joined,
        judge_flip_threshold=args.judge_flip_threshold,
        require_sidecar=not args.allow_missing_sidecar,
        canonical_only=not args.all_designs,
        corrected_judge_cutoff=args.corrected_judge_cutoff,
    )
    corrected = sum(
        1
        for j in kept
        if _executed_with_corrected_judge(evaluated=j.evaluated, cutoff=args.corrected_judge_cutoff)
    )
    logger.info(
        "scenario=%s: %d baseline runs found, %d kept "
        "(judge flip<=%.2f, require_sidecar=%s, canonical_only=%s, "
        "corrected-judge cutoff>=%s: %d kept runs ran with the corrected judge).",
        args.scenario,
        len(joined),
        len(kept),
        args.judge_flip_threshold,
        not args.allow_missing_sidecar,
        not args.all_designs,
        args.corrected_judge_cutoff.isoformat(),
        corrected,
    )

    run_level = _build_run_level_frame(joined_runs=kept)
    round_level = _build_round_level_frame(joined_runs=kept)
    budget_aggregate = _build_budget_aggregate_frame(run_level=run_level)
    frames = {
        "run_level": run_level,
        "round_level": round_level,
        "budget_aggregate": budget_aggregate,
    }

    csv_paths = _write_csvs(frames=frames, output_dir=args.output_dir, stem=args.stem)
    xlsx_path = _write_xlsx(frames=frames, output_dir=args.output_dir, stem=args.stem)

    logger.info(
        "Wrote %d runs, %d round-rows. CSVs: %s%s",
        len(run_level),
        len(round_level),
        ", ".join(str(p) for p in csv_paths),
        f"; workbook: {xlsx_path}" if xlsx_path is not None else "",
    )


if __name__ == "__main__":
    main()
