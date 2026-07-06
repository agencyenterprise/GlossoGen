"""Export the protocol-learnability cohort behind the Streamlit "Protocol learnability" tab.

One merged workbook covers every phase, so it maps 1:1 onto the online spreadsheet's data
tabs. All derived phases share the ``phase=baseline`` runs (the 15-round source teams that
developed the private protocol):

- frontier conditions — ``resume_expected`` (intact team resumed, postmortem on — the
  *expected* ceiling), ``resume_expected_no_postmortem`` (intact team resumed, postmortem
  killed — isolates the no-postmortem effect), ``replace_learned`` (fresh same-model observer
  that learned the protocol from the windowed link transcript), and ``replace_cross_family``
  (fresh *other-family* observer; the ``observer=`` label records its family).
- llama condition — ``replace_llama``: a fresh self-hosted Llama observer swapped onto a
  frontier team's protocol.

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

Four output tables (``run_level`` / ``message_level`` carry every phase, distinguished by the
``phase`` column; the two aggregates differ only in which derived phases they roll up because
their column sets differ):

- ``run_level`` — one row per cohort run.
- ``message_level`` — one row per link-channel message across every round the run played, with
  substage ground truth + per-message gpt2 ``perplexity``, English-char-trigram
  ``english_ngram_surprisal`` (higher = less English-like), ``english_ngram_backoff_surprisal``
  (backoff variant: case-sensitive, digits + punctuation kept), ``message_entropy``
  (within-message character Shannon entropy, bits/char; lower = more repetitive), and
  ``gzip_compression_ratio`` (per-message raw-DEFLATE compressed/original, gzip framing
  excluded; lower = more compressible/repetitive).
- ``baseline_aggregate`` — one row per baseline (``src_id``), frontier columns
  ``expected`` / ``expected_no_pm`` / ``learned`` / ``cross_family`` (means/std/n) with
  ``delta = learned − expected_no_pm``, computed on ``round_success_after_resume``.
- ``baseline_aggregate_llama`` — one row per baseline, llama column ``llama`` with
  ``delta = llama − baseline`` (the fresh Llama observer's post-swap success vs the source
  team's own baseline success).

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
from analysis.run_export.message_backoff_ngram_scorer import MessageBackoffNgramScorer
from analysis.run_export.message_english_ngram_scorer import MessageEnglishNgramScorer
from analysis.run_export.message_perplexity_scorer import MessagePerplexityScorer
from analysis.run_export.run_context_scan import (
    RunContext,
    ScenarioExportSpec,
    label_value,
    model_class,
    model_column_names,
    role_model_columns,
    scan_run_context,
    sender_role,
)
from analysis.run_export.scenario_export_specs import get_export_spec
from analysis.run_export.spreadsheet_writer import write_csvs, write_xlsx
from schmidt.evaluation.metric_core.character_entropy import character_entropy_bits
from schmidt.evaluation.metric_core.gzip_compression import gzip_compression_ratio

logger = logging.getLogger(__name__)

_COHORT_LABEL = "protocol_learnability"
_TOOL_LEAK_LABEL = "tool_leak"
_ROUND_SUCCESS_METRIC = "round_success"
_RANDOM_SEED_LABEL = "random_seed"

_PHASE_BASELINE = "baseline"
_STEM = "protocol_learnability"
# Maps each derived phase to the column prefix used in baseline_aggregate, matching the
# tab's BaselineLearnability field names. The frontier aggregate holds the four
# Anthropic/OpenAI conditions; the llama aggregate holds only the self-hosted Llama observer.
# They carry different column sets, so each gets its own sheet, while run_level /
# message_level carry every phase in one sheet (distinguished by the ``phase`` column).
_FRONTIER_DERIVED_PREFIX = {
    "resume_expected": "expected",
    "resume_expected_no_postmortem": "expected_no_pm",
    "replace_learned": "learned",
    "replace_cross_family": "cross_family",
}
_LLAMA_DERIVED_PREFIX = {
    "replace_llama": "llama",
}


class _CohortSpec(NamedTuple):
    """One ``baseline_aggregate`` definition: its name and the derived phases it rolls up."""

    name: str
    derived_prefix: dict[str, str]


_FRONTIER_AGGREGATE = _CohortSpec(name="frontier", derived_prefix=_FRONTIER_DERIVED_PREFIX)
_LLAMA_AGGREGATE = _CohortSpec(name="llama", derived_prefix=_LLAMA_DERIVED_PREFIX)
# run_level / message_level cover every phase; each aggregate then filters to its own.
_ALLOWED_PHASES = frozenset({_PHASE_BASELINE, *_FRONTIER_DERIVED_PREFIX, *_LLAMA_DERIVED_PREFIX})


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

    Qualifies when the run carries the ``protocol_learnability`` label, is not labeled
    ``tool_leak`` (runs produced under the since-fixed history-builder leak are excluded), a
    ``phase=`` label, a ``round_time_budget_seconds`` knob, and a ``round_success`` measurement.
    """
    labels = read_labels(run_dir=evaluated.run_dir)
    if _COHORT_LABEL not in labels:
        return None
    if _TOOL_LEAK_LABEL in labels:
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
    evaluated_runs: list[EvaluatedRun],
    scenario_name: str,
    allowed_phases: frozenset[str],
    spec: ScenarioExportSpec,
) -> tuple[list[ProtocolRunRecord], dict[str, RunContext]]:
    """Scan every cohort run for ``scenario_name`` into records + per-run context.

    Only runs whose ``phase`` is in ``allowed_phases`` are kept, so the frontier and
    llama spreadsheets each cover their own derived phases (plus the shared baselines).
    """
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
        if record.phase not in allowed_phases:
            continue
        records.append(record)
        contexts[record.run_id] = scan_run_context(
            jsonl_path=run.run_dir / f"{run.scenario_name}.jsonl", spec=spec
        )
    return records, contexts


def _build_run_level_frame(
    records: list[ProtocolRunRecord],
    contexts: dict[str, RunContext],
    spec: ScenarioExportSpec,
    perplexity_by_run: dict[str, float | None],
    english_ngram_by_run: dict[str, float | None],
    english_ngram_backoff_by_run: dict[str, float | None],
    message_entropy_by_run: dict[str, float | None],
    gzip_compression_ratio_by_run: dict[str, float | None],
    mcm_by_run: dict[str, float | None],
) -> pd.DataFrame:
    """One row per cohort run.

    ``perplexity`` (run-wide mean per-message surprisal, nats/gpt2),
    ``english_ngram_surprisal`` (run-wide mean per-message per-char surprisal under an
    English char trigram; higher = less English-like), ``english_ngram_backoff_surprisal``
    (richer variant: case-sensitive, digits + punctuation kept, stupid-backoff smoothing),
    ``message_entropy`` (run-wide mean
    within-message character Shannon entropy, bits/char; lower = more
    repetitive/compressible), ``gzip_compression_ratio`` (run-wide mean per-message raw-DEFLATE
    compressed/original with the constant gzip framing excluded; lower = more
    compressible/repetitive), and ``mcm`` (run-wide mean chars per link message) are rolled up from
    the per-message ``message_level`` scoring, since these runs carry no ``perplexity`` /
    ``mcm`` metric in their reports.
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
                **role_model_columns(context=context, spec=spec),
                "model_class": model_class(role_models=context.role_models),
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
                "english_ngram_surprisal": english_ngram_by_run.get(record.run_id),
                "message_entropy": message_entropy_by_run.get(record.run_id),
                "gzip_compression_ratio": gzip_compression_ratio_by_run.get(record.run_id),
                "mcm": mcm_by_run.get(record.run_id),
                "labels": "|".join(record.labels),
                # Appended last so pre-existing columns don't shift (charts read by position).
                "english_ngram_backoff_surprisal": english_ngram_backoff_by_run.get(record.run_id),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(by=["src_id", "phase", "run_id"]).reset_index(drop=True)


def _build_message_level_frame(
    records: list[ProtocolRunRecord], contexts: dict[str, RunContext], spec: ScenarioExportSpec
) -> pd.DataFrame:
    """One row per link-channel message across every round each cohort run played.

    Reuses the baseline export's message schema (substage ground truth, per-message gpt2
    perplexity, round-level ``success`` / ``note``), plus the cohort identity columns
    ``phase`` / ``src_id`` / ``observer``.
    """
    perplexity_scorer = MessagePerplexityScorer()
    english_ngram_scorer = MessageEnglishNgramScorer()
    backoff_ngram_scorer = MessageBackoffNgramScorer()
    rows: list[dict[str, object]] = []
    for record in records:
        context = contexts[record.run_id]
        run_model_class = model_class(role_models=context.role_models)
        model_columns = role_model_columns(context=context, spec=spec)
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
                            **model_columns,
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
                            "message_agent": sender_role(agent_id=message.agent, spec=spec),
                            "message_text": message.message,
                            "chars": len(message.message),
                            "success": int(round(value)),
                            "note": note,
                        }
                    )
        jsonl_path = record.run_dir / f"{record.scenario}.jsonl"
        message_texts = [str(row["message_text"]) for row in run_rows]
        perplexities = perplexity_scorer.score_run(jsonl_path=jsonl_path, texts=message_texts)
        english_ngram_surprisals = english_ngram_scorer.score_run(
            jsonl_path=jsonl_path, texts=message_texts
        )
        backoff_ngram_surprisals = backoff_ngram_scorer.score_run(
            jsonl_path=jsonl_path, texts=message_texts
        )
        message_entropies = [
            character_entropy_bits(text=text) if text.strip() else None for text in message_texts
        ]
        gzip_ratios = [
            gzip_compression_ratio(text=text) if text.strip() else None for text in message_texts
        ]
        for row, perplexity, english_ngram, backoff_ngram, entropy, gzip_ratio in zip(
            run_rows,
            perplexities,
            english_ngram_surprisals,
            backoff_ngram_surprisals,
            message_entropies,
            gzip_ratios,
        ):
            row["perplexity"] = perplexity
            row["english_ngram_surprisal"] = english_ngram
            row["message_entropy"] = entropy
            row["gzip_compression_ratio"] = gzip_ratio
            # Appended last so it never shifts pre-existing columns (charts reference by position).
            row["english_ngram_backoff_surprisal"] = backoff_ngram
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
    spec: ScenarioExportSpec,
    cohort: _CohortSpec,
) -> pd.DataFrame:
    """One row per baseline mirroring the tab's BaselineLearnability, on after-resume score.

    Derived runs are joined to their baseline directly by ``src_id``. The ``delta`` column is
    cohort-specific: for the frontier cohort it is ``learned - expected_no_pm`` (the
    fresh-observer transmission gap); for the llama cohort it is ``llama - baseline`` (the
    fresh Llama observer's post-swap success vs the source team's own baseline success).
    """
    baselines = {record.run_id: record for record in records if record.phase == _PHASE_BASELINE}
    rows: list[dict[str, object]] = []
    for src_id in sorted(baselines):
        baseline = baselines[src_id]
        context = contexts[baseline.run_id]
        row: dict[str, object] = {
            "src_id": src_id,
            **role_model_columns(context=context, spec=spec),
            "model_class": model_class(role_models=context.role_models),
            "round_time_budget_seconds": baseline.round_time_budget_seconds,
            "baseline_round_success_fraction": baseline.round_success_fraction,
            "cross_family_observer": None,
        }
        means: dict[str, float | None] = {}
        for phase, prefix in cohort.derived_prefix.items():
            stats, observer = _phase_after_resume(records=records, head_src_id=src_id, phase=phase)
            row[f"n_{prefix}"] = stats.n
            row[f"{prefix}_mean"] = stats.mean
            row[f"{prefix}_std"] = stats.std
            means[prefix] = stats.mean
            if prefix == "cross_family" and observer is not None:
                row["cross_family_observer"] = observer
        if cohort.name == "llama":
            row["delta"] = _delta(learned=means["llama"], baseline=baseline.round_success_fraction)
        else:
            row["delta"] = _delta(learned=means["learned"], baseline=means["expected_no_pm"])
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(by=[*model_column_names(spec=spec), "src_id"]).reset_index(drop=True)


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for the exporter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--scenario", type=str, default="veyru")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("analysis/protocol_learnability_export/output")
    )
    parser.add_argument("--stem", type=str, default=_STEM)
    return parser.parse_args()


def main() -> None:
    """Build the four frames and write the merged workbook + CSVs."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    spec = get_export_spec(scenario_name=args.scenario)
    evaluated_runs = list_evaluated_runs(runs_dir=args.runs_dir)
    records, contexts = _collect_records(
        evaluated_runs=evaluated_runs,
        scenario_name=args.scenario,
        allowed_phases=_ALLOWED_PHASES,
        spec=spec,
    )
    baseline_count = sum(1 for record in records if record.phase == _PHASE_BASELINE)
    logger.info(
        "scenario=%s: %d protocol_learnability runs (%d baselines, %d derived).",
        args.scenario,
        len(records),
        baseline_count,
        len(records) - baseline_count,
    )

    message_level = _build_message_level_frame(records=records, contexts=contexts, spec=spec)
    run_level = _build_run_level_frame(
        records=records,
        contexts=contexts,
        spec=spec,
        perplexity_by_run=_run_means(message_level=message_level, column="perplexity"),
        english_ngram_by_run=_run_means(
            message_level=message_level, column="english_ngram_surprisal"
        ),
        english_ngram_backoff_by_run=_run_means(
            message_level=message_level, column="english_ngram_backoff_surprisal"
        ),
        message_entropy_by_run=_run_means(message_level=message_level, column="message_entropy"),
        gzip_compression_ratio_by_run=_run_means(
            message_level=message_level, column="gzip_compression_ratio"
        ),
        mcm_by_run=_run_means(message_level=message_level, column="chars"),
    )
    baseline_aggregate = _build_baseline_aggregate_frame(
        records=records, contexts=contexts, spec=spec, cohort=_FRONTIER_AGGREGATE
    )
    baseline_aggregate_llama = _build_baseline_aggregate_frame(
        records=records, contexts=contexts, spec=spec, cohort=_LLAMA_AGGREGATE
    )
    frames = {
        "run_level": run_level,
        "message_level": message_level,
        "baseline_aggregate": baseline_aggregate,
        "baseline_aggregate_llama": baseline_aggregate_llama,
    }

    csv_paths = write_csvs(frames=frames, output_dir=args.output_dir, stem=args.stem)
    xlsx_path = write_xlsx(frames=frames, output_dir=args.output_dir, stem=args.stem)

    logger.info(
        "Wrote %d runs, %d message-rows, %d frontier-baselines, %d llama-baselines. CSVs: %s%s",
        len(run_level),
        len(message_level),
        len(baseline_aggregate),
        len(baseline_aggregate_llama),
        ", ".join(str(p) for p in csv_paths),
        f"; workbook: {xlsx_path}" if xlsx_path is not None else "",
    )


if __name__ == "__main__":
    main()
