"""Export the protocol-learnability cohort behind the Streamlit "Protocol learnability" tab.

The cohort is every ``protocol_learnability`` run, in five phases:

- ``phase=baseline`` — the 15-round source team that developed the private protocol.
- ``phase=resume_expected`` — the intact team resumed at the swap boundary, postmortem on
  (the *expected* ceiling).
- ``phase=resume_expected_no_postmortem`` — intact team resumed, postmortem killed going
  forward (isolates the no-postmortem effect from the fresh-observer effect).
- ``phase=replace_learned`` — a fresh same-model field observer that learned the protocol
  from the windowed link transcript alone.
- ``phase=replace_cross_family`` — a fresh *other-family* observer (the ``observer=`` label
  records its family).

Each derived run links to its baseline through the ``src=<scenario>/<ts>`` label and carries
a ``replace_manifest.json`` (``rounds_after_swap``).

The tables reuse the baseline round-success export's schema (``run_level`` / ``message_level``)
unchanged, plus a handful of cohort columns: ``phase``, ``src_id``, ``observer_model``
(cross-family observer family; blank on the other phases), ``history`` (the ``history=``
link-window label), ``rounds_after_swap``, and the one new metric the tab couldn't show —
``round_success_after_resume``
(the stored metric's ``score``: the fraction of post-resume rounds won over rounds
``round_start``–(``round_start`` + ``rounds_after_swap``); blank on baselines, which carry no
swap manifest).

Three output tables:

- ``run_level`` — one row per cohort run.
- ``message_level`` — one row per link-channel message across every round the run played, with
  substage ground truth + per-message gpt2 ``perplexity``.
- ``baseline_aggregate`` — one row per baseline (``src_id``), mirroring the tab's
  ``BaselineLearnability`` per-phase means/std/n (``expected`` / ``expected_no_pm`` / ``learned``
  / ``cross_family``) and ``delta`` (learned − expected_no_pm), computed on
  ``round_success_after_resume``.

Writes one CSV per table, and (when ``openpyxl`` is importable) a single multi-sheet ``.xlsx``
workbook.
"""

import argparse
import logging
import statistics
from pathlib import Path
from typing import NamedTuple

import orjson
import pandas as pd

from analysis.results_viewer.measurement_scores import read_labels, round_success_after_resume_score
from analysis.results_viewer.run_catalog import EvaluatedRun, list_evaluated_runs
from analysis.veyru_run_export.message_perplexity_scorer import MessagePerplexityScorer
from analysis.veyru_run_export.run_context_scan import (
    RunContext,
    label_value,
    model_class,
    scan_run_context,
    sender_role,
)
from analysis.veyru_run_export.spreadsheet_writer import write_csvs, write_xlsx

logger = logging.getLogger(__name__)

_COHORT_LABEL = "protocol_learnability"
_ROUND_SUCCESS_METRIC = "round_success"
_RANDOM_SEED_LABEL = "random_seed"

_PHASE_BASELINE = "baseline"
# Maps each derived phase to the column prefix used in baseline_aggregate, matching the
# tab's BaselineLearnability field names.
_DERIVED_PHASE_PREFIX = {
    "resume_expected": "expected",
    "resume_expected_no_postmortem": "expected_no_pm",
    "replace_learned": "learned",
    "replace_cross_family": "cross_family",
}


class ProtocolRunRecord(NamedTuple):
    """The run-level facts the export needs for one protocol-learnability cohort run."""

    run_id: str
    run_dir: Path
    scenario: str
    phase: str
    src_id: str
    observer: str | None
    history: str | None
    rounds_after_swap: int | None
    round_time_budget_seconds: int
    postmortem: bool
    random_seed: bool
    total_rounds: int
    round_success_count: int
    round_success_fraction: float | None
    round_success_after_resume: float | None
    per_round: list[tuple[int, float, str]]
    labels: list[str]


class _PhaseStats(NamedTuple):
    """Per-(baseline, phase) replica aggregate of round_success_after_resume."""

    n: int
    mean: float | None
    std: float | None


def _round_success_per_round(evaluated: EvaluatedRun) -> list[tuple[int, float, str]]:
    """Return ``(round_number, value, note)`` from the run's ``round_success`` measurement."""
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == _ROUND_SUCCESS_METRIC:
            return [(obs.round_number, obs.value, obs.note) for obs in measurement.per_round]
    return []


def _read_rounds_after_swap(run_dir: Path) -> int | None:
    """Read ``rounds_after_swap`` from the run's replace manifest, or ``None`` for baselines.

    Checks ``replace_manifest.json`` then ``cross_run_replace_manifest.json``.
    """
    for name in ("replace_manifest.json", "cross_run_replace_manifest.json"):
        path = run_dir / name
        if not path.exists():
            continue
        payload = orjson.loads(path.read_bytes())
        value = payload.get("rounds_after_swap")
        return value if isinstance(value, int) else None
    return None


def _build_record(evaluated: EvaluatedRun) -> ProtocolRunRecord | None:
    """Build a ``ProtocolRunRecord`` for a cohort run, or ``None`` if it doesn't qualify.

    Qualifies when the run carries the ``protocol_learnability`` label, a ``phase=`` label, a
    ``round_time_budget_seconds`` knob, and a ``round_success`` measurement.
    """
    labels = read_labels(run_dir=evaluated.run_dir)
    if _COHORT_LABEL not in labels:
        return None
    phase = label_value(labels=labels, prefix="phase=")
    if phase is None:
        return None
    src = label_value(labels=labels, prefix="src=")
    if phase == _PHASE_BASELINE:
        src_id = evaluated.run_id
    elif src is not None:
        src_id = src
    else:
        return None
    config = evaluated.metadata.scenario_config
    budget = config.get("round_time_budget_seconds")
    if not isinstance(budget, (int, float)):
        return None
    per_round = _round_success_per_round(evaluated=evaluated)
    if not per_round:
        return None
    total_rounds = int(config.get("round_count", 0))
    round_success_count = sum(1 for _, value, _ in per_round if value > 0)
    fraction = None
    if total_rounds > 0:
        fraction = round_success_count / total_rounds
    return ProtocolRunRecord(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        scenario=evaluated.scenario_name,
        phase=phase,
        src_id=src_id,
        observer=label_value(labels=labels, prefix="observer="),
        history=label_value(labels=labels, prefix="history="),
        rounds_after_swap=_read_rounds_after_swap(run_dir=evaluated.run_dir),
        round_time_budget_seconds=int(budget),
        postmortem=bool(config.get("postmortem_enabled", False)),
        random_seed=_RANDOM_SEED_LABEL in labels,
        total_rounds=total_rounds,
        round_success_count=round_success_count,
        round_success_fraction=fraction,
        round_success_after_resume=round_success_after_resume_score(evaluated=evaluated),
        per_round=per_round,
        labels=labels,
    )


def _collect_records(
    evaluated_runs: list[EvaluatedRun], scenario_name: str
) -> tuple[list[ProtocolRunRecord], dict[str, RunContext]]:
    """Scan every cohort run for ``scenario_name`` into records + per-run context."""
    records: list[ProtocolRunRecord] = []
    contexts: dict[str, RunContext] = {}
    for run in evaluated_runs:
        if run.scenario_name != scenario_name:
            continue
        if _COHORT_LABEL not in read_labels(run_dir=run.run_dir):
            continue
        record = _build_record(evaluated=run)
        if record is None:
            continue
        records.append(record)
        contexts[record.run_id] = scan_run_context(
            jsonl_path=run.run_dir / f"{run.scenario_name}.jsonl"
        )
    return records, contexts


def _build_run_level_frame(
    records: list[ProtocolRunRecord],
    contexts: dict[str, RunContext],
    perplexity_by_run: dict[str, float | None],
    mcm_by_run: dict[str, float | None],
) -> pd.DataFrame:
    """One row per cohort run.

    ``perplexity`` (run-wide mean per-message surprisal, nats/gpt2) and ``mcm`` (run-wide
    mean chars per link message) are rolled up from the per-message ``message_level``
    scoring, since these runs carry no ``perplexity`` / ``mcm`` metric in their reports.
    """
    rows: list[dict[str, object]] = []
    for record in records:
        context = contexts[record.run_id]
        rows.append(
            {
                "run_id": record.run_id,
                "scenario": record.scenario,
                "phase": record.phase,
                "src_id": record.src_id,
                "field_observer_model": context.field_observer_model,
                "engineer_model": context.engineer_model,
                "model_class": model_class(
                    field_observer_model=context.field_observer_model,
                    engineer_model=context.engineer_model,
                ),
                "observer_model": record.observer,
                "postmortem": record.postmortem,
                "round_time_budget_seconds": record.round_time_budget_seconds,
                "random_seed": record.random_seed,
                "history": record.history,
                "rounds_after_swap": record.rounds_after_swap,
                "total_rounds": record.total_rounds,
                "round_success_count": record.round_success_count,
                "round_success_after_resume": record.round_success_after_resume,
                "perplexity": perplexity_by_run.get(record.run_id),
                "mcm": mcm_by_run.get(record.run_id),
                "labels": "|".join(record.labels),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(by=["src_id", "phase", "run_id"]).reset_index(drop=True)


def _build_message_level_frame(
    records: list[ProtocolRunRecord], contexts: dict[str, RunContext]
) -> pd.DataFrame:
    """One row per link-channel message across every round each cohort run played.

    Reuses the baseline export's message schema (substage ground truth, per-message gpt2
    perplexity, round-level ``success`` / ``note``), plus the cohort identity columns
    ``phase`` / ``src_id`` / ``observer``.
    """
    perplexity_scorer = MessagePerplexityScorer()
    rows: list[dict[str, object]] = []
    for record in records:
        context = contexts[record.run_id]
        run_model_class = model_class(
            field_observer_model=context.field_observer_model,
            engineer_model=context.engineer_model,
        )
        run_rows: list[dict[str, object]] = []
        for round_number, value, note in record.per_round:
            round_ctx = context.rounds.get(round_number)
            if round_ctx is None:
                continue
            for substage in range(1, round_ctx.stages_reached + 1):
                stage = round_ctx.stages[substage - 1]
                messages = round_ctx.link_messages_by_substage.get(substage, [])
                for message_index, message in enumerate(messages, start=1):
                    run_rows.append(
                        {
                            "run_id": record.run_id,
                            "scenario": record.scenario,
                            "phase": record.phase,
                            "src_id": record.src_id,
                            "field_observer_model": context.field_observer_model,
                            "engineer_model": context.engineer_model,
                            "model_class": run_model_class,
                            "observer_model": record.observer,
                            "postmortem": record.postmortem,
                            "round_time_budget_seconds": record.round_time_budget_seconds,
                            "random_seed": record.random_seed,
                            "round_number": round_number,
                            "substage": substage,
                            "symptoms": stage.symptoms,
                            "actions": stage.actions,
                            "substage_stabilized": int(substage <= round_ctx.stabilized_stages),
                            "message_index_in_substage": message_index,
                            "message_agent": sender_role(agent_id=message.agent),
                            "message_text": message.message,
                            "chars": len(message.message),
                            "success": int(round(value)),
                            "note": note,
                        }
                    )
        jsonl_path = record.run_dir / f"{record.scenario}.jsonl"
        perplexities = perplexity_scorer.score_run(
            jsonl_path=jsonl_path, texts=[str(row["message_text"]) for row in run_rows]
        )
        for row, perplexity in zip(run_rows, perplexities):
            row["perplexity"] = perplexity
        rows.extend(run_rows)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        by=["src_id", "phase", "run_id", "round_number", "substage", "message_index_in_substage"]
    ).reset_index(drop=True)


def _run_means(message_level: pd.DataFrame, column: str) -> dict[str, float | None]:
    """Map ``run_id`` to the mean of ``column`` over that run's message rows (NaN -> None).

    Runs with no message rows are absent from the map (callers ``.get`` to ``None``).
    """
    if message_level.empty:
        return {}
    series = message_level.groupby("run_id")[column].mean()
    return {
        str(run_id): (None if pd.isna(value) else float(value)) for run_id, value in series.items()
    }


def _phase_stats(values: list[float]) -> _PhaseStats:
    """Aggregate one phase's replica values into ``n`` + mean + sample std (tab semantics).

    Sample standard deviation (``ddof=1``) when ``n >= 2``, else ``0.0``; mean/std are
    ``None`` only when the phase has no replicas.
    """
    if not values:
        return _PhaseStats(n=0, mean=None, std=None)
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) >= 2 else 0.0
    return _PhaseStats(n=len(values), mean=mean, std=std)


def _phase_after_resume(
    records: list[ProtocolRunRecord], head_src_id: str, phase: str
) -> tuple[_PhaseStats, str | None]:
    """Aggregate one baseline's phase replicas of ``round_success_after_resume`` (+ observer).

    Derived runs join their baseline directly by ``src_id``.
    """
    values: list[float] = []
    observer: str | None = None
    for record in records:
        if record.phase != phase:
            continue
        if record.src_id != head_src_id:
            continue
        if record.round_success_after_resume is not None:
            values.append(record.round_success_after_resume)
        if record.observer is not None:
            observer = record.observer
    return _phase_stats(values=values), observer


def _delta(learned: float | None, baseline: float | None) -> float | None:
    """``learned - baseline`` transmission gap, or ``None`` when either mean is missing."""
    if learned is None or baseline is None:
        return None
    return learned - baseline


def _build_baseline_aggregate_frame(
    records: list[ProtocolRunRecord],
    contexts: dict[str, RunContext],
) -> pd.DataFrame:
    """One row per baseline mirroring the tab's BaselineLearnability, on after-resume score.

    Derived runs are joined to their baseline directly by ``src_id``.
    """
    baselines = {record.run_id: record for record in records if record.phase == _PHASE_BASELINE}
    rows: list[dict[str, object]] = []
    for src_id in sorted(baselines):
        baseline = baselines[src_id]
        context = contexts[baseline.run_id]
        row: dict[str, object] = {
            "src_id": src_id,
            "field_observer_model": context.field_observer_model,
            "engineer_model": context.engineer_model,
            "model_class": model_class(
                field_observer_model=context.field_observer_model,
                engineer_model=context.engineer_model,
            ),
            "round_time_budget_seconds": baseline.round_time_budget_seconds,
            "baseline_round_success_fraction": baseline.round_success_fraction,
            "cross_family_observer": None,
        }
        means: dict[str, float | None] = {}
        for phase, prefix in _DERIVED_PHASE_PREFIX.items():
            stats, observer = _phase_after_resume(records=records, head_src_id=src_id, phase=phase)
            row[f"n_{prefix}"] = stats.n
            row[f"{prefix}_mean"] = stats.mean
            row[f"{prefix}_std"] = stats.std
            means[prefix] = stats.mean
            if prefix == "cross_family" and observer is not None:
                row["cross_family_observer"] = observer
        row["delta"] = _delta(learned=means["learned"], baseline=means["expected_no_pm"])
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(by=["field_observer_model", "engineer_model", "src_id"]).reset_index(
        drop=True
    )


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for the exporter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--scenario", type=str, default="veyru")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("analysis/protocol_learnability_export/output")
    )
    parser.add_argument("--stem", type=str, default="protocol_learnability")
    return parser.parse_args()


def main() -> None:
    """Build the three frames and write outputs."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    evaluated_runs = list_evaluated_runs(runs_dir=args.runs_dir)
    records, contexts = _collect_records(evaluated_runs=evaluated_runs, scenario_name=args.scenario)
    baseline_count = sum(1 for record in records if record.phase == _PHASE_BASELINE)
    logger.info(
        "scenario=%s: %d protocol_learnability runs (%d baselines, %d derived).",
        args.scenario,
        len(records),
        baseline_count,
        len(records) - baseline_count,
    )

    message_level = _build_message_level_frame(records=records, contexts=contexts)
    run_level = _build_run_level_frame(
        records=records,
        contexts=contexts,
        perplexity_by_run=_run_means(message_level=message_level, column="perplexity"),
        mcm_by_run=_run_means(message_level=message_level, column="chars"),
    )
    baseline_aggregate = _build_baseline_aggregate_frame(records=records, contexts=contexts)
    frames = {
        "run_level": run_level,
        "message_level": message_level,
        "baseline_aggregate": baseline_aggregate,
    }

    csv_paths = write_csvs(frames=frames, output_dir=args.output_dir, stem=args.stem)
    xlsx_path = write_xlsx(frames=frames, output_dir=args.output_dir, stem=args.stem)

    logger.info(
        "Wrote %d runs, %d message-rows, %d baselines. CSVs: %s%s",
        len(run_level),
        len(message_level),
        len(baseline_aggregate),
        ", ".join(str(p) for p in csv_paths),
        f"; workbook: {xlsx_path}" if xlsx_path is not None else "",
    )


if __name__ == "__main__":
    main()
