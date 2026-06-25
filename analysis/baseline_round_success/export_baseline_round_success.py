"""Export the baseline round-success-vs-budget data behind the Streamlit baseline tab.

Covers scenario runs labeled ``baseline`` (closed-model frontier), ``baseline_oss``
(open-weight), or ``oss_frontier`` (cross-family teams pairing an open-weight with a
closed model), as long as they carry a ``round_time_budget_seconds`` knob and a
``round_success`` measurement. Written in a shape suited to mixed-effects modelling.

By default every seed mode is included; the ``random_seed`` column marks each run's
design so it can be modelled or subset downstream:

- ``random_seed`` — True when the run used a per-launch random seed, False for the
  canonical fixed ``seed=42``. Pass ``--canonical-only`` to keep just the fixed-seed runs.

Per-agent models come from the run's ``AgentRegistered`` events: every table carries
``field_observer_model`` and ``engineer_model`` instead of a single ``model`` column.
``model_class`` is derived from the two agents' model families: ``closed`` (both
claude/gpt), ``open`` (both llama/qwen), or ``mixed`` (one open, one closed).

Four output tables:

- ``run_level`` — one row per run (the replica dots on the chart). The Bernoulli
  numerator/denominator (``round_success_count`` / ``total_rounds``) supports a
  binomial GLMM ``cbind(successes, failures) ~ ...`` and the fraction supports a
  beta/linear model. Also carries the run's headline ``perplexity`` (overall mean
  per-token surprisal), ``english_ngram_surprisal`` (overall mean per-char surprisal
  under an English char trigram; higher = less English-like), ``message_entropy`` (overall
  mean within-message character Shannon entropy in bits/char; lower = more
  repetitive/compressible), ``gzip_compression_ratio`` (overall mean per-message raw-DEFLATE
  compressed/original with the constant gzip framing excluded; lower = more
  compressible/repetitive), and ``mcm`` (overall mean chars per message) from the report.
- ``message_level`` — one row per link-channel message. Each row carries its substage
  context (``substage``, ``symptoms`` / ``actions``, ``substage_stabilized``),
  ``message_index_in_substage``, ``message_agent`` (sender role, normalized to
  ``field_observer`` or ``stabilization_engineer``), ``message_text``, ``chars``
  (``len(message_text)``), ``perplexity`` (per-message mean per-token surprisal in nats
  under gpt2; blank for empty/single-token messages), ``english_ngram_surprisal``
  (per-message mean per-char surprisal under an English char trigram; higher = less
  English-like; blank for empty messages), ``message_entropy`` (per-message within-message
  character Shannon entropy in bits/char; lower = more repetitive; blank for empty
  messages), ``gzip_compression_ratio`` (per-message raw-DEFLATE compressed/original, gzip
  framing excluded; lower = more compressible; blank for empty messages), and the round-level
  ``success`` (0/1 whole-round outcome) / ``note``. Messages are walked over the substages the
  team reached (``min(stabilized_stages + 1, total_stages)``); substages with no link
  traffic produce no rows.
- ``round_context`` — one row per (run, round) holding the large round-start briefings
  (``field_observer_round_event`` / ``engineer_round_event``). Kept separate (join on
  ``run_id`` + ``round_number``) so the briefing text is stored once per round rather
  than duplicated on every message row.
- ``budget_aggregate`` — per (models, postmortem, random_seed, budget)
  mean ± std of the success fraction; a sanity check against the plotted bands.

Writes one CSV per table, and (when ``openpyxl`` is importable) a single
multi-sheet ``.xlsx`` workbook.
"""

import argparse
import logging
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from analysis.results_viewer.measurement_scores import (
    english_ngram_surprisal_score,
    gzip_compression_ratio_score,
    mcm_score,
    message_entropy_score,
    perplexity_score,
    read_labels,
)
from analysis.results_viewer.run_catalog import EvaluatedRun, list_evaluated_runs
from analysis.veyru_run_export.message_english_ngram_scorer import MessageEnglishNgramScorer
from analysis.veyru_run_export.message_perplexity_scorer import MessagePerplexityScorer
from analysis.veyru_run_export.run_context_scan import (
    RunContext,
    model_class,
    scan_run_context,
    sender_role,
)
from analysis.veyru_run_export.spreadsheet_writer import write_csvs, write_xlsx
from schmidt.evaluation.metric_core.character_entropy import character_entropy_bits
from schmidt.evaluation.metric_core.gzip_compression import gzip_compression_ratio

logger = logging.getLogger(__name__)

_ROUND_SUCCESS_METRIC = "round_success"
_RANDOM_SEED_LABEL = "random_seed"
# Runs in scope for the export: the homogeneous baseline cohorts plus the
# cross-family (oss_frontier) runs that pair an open-weight with a closed model.
_SCOPE_LABELS = frozenset({"baseline", "baseline_oss", "oss_frontier"})


class JoinedRun(NamedTuple):
    """A baseline run paired with its source ``EvaluatedRun``."""

    evaluated: EvaluatedRun


class RunRecord(NamedTuple):
    """The run-level facts the export needs, for any in-scope run.

    Replaces ``build_baseline_run`` so the export can also admit ``oss_frontier``
    (cross-family) runs, which carry no ``baseline`` label.
    """

    run_id: str
    budget: int
    postmortem_enabled: bool
    total_rounds: int
    round_success: int
    perplexity_score: float | None
    english_ngram_score: float | None
    message_entropy_score: float | None
    gzip_compression_ratio_score: float | None
    mcm_score: float | None
    labels: list[str]


def _build_record(evaluated: EvaluatedRun) -> RunRecord | None:
    """Build a ``RunRecord`` for an in-scope run, or ``None`` if it doesn't qualify.

    Qualifies when the run carries a scope label (``baseline`` / ``baseline_oss`` /
    ``oss_frontier``), a ``round_time_budget_seconds`` knob, and a ``round_success``
    measurement. ``round_success`` counts the rounds whose per-round value is positive.
    """
    labels = read_labels(run_dir=evaluated.run_dir)
    if not _SCOPE_LABELS.intersection(labels):
        return None
    config = evaluated.metadata.scenario_config
    budget = config.get("round_time_budget_seconds")
    if not isinstance(budget, (int, float)):
        return None
    per_round = _round_success_per_round(evaluated=evaluated)
    if not per_round:
        return None
    round_success = sum(1 for _, value, _ in per_round if value > 0)
    return RunRecord(
        run_id=evaluated.run_id,
        budget=int(budget),
        postmortem_enabled=bool(config.get("postmortem_enabled", False)),
        total_rounds=int(config.get("round_count", 0)),
        round_success=round_success,
        perplexity_score=perplexity_score(evaluated=evaluated),
        english_ngram_score=english_ngram_surprisal_score(evaluated=evaluated),
        message_entropy_score=message_entropy_score(evaluated=evaluated),
        gzip_compression_ratio_score=gzip_compression_ratio_score(evaluated=evaluated),
        mcm_score=mcm_score(evaluated=evaluated),
        labels=labels,
    )


def _collect_joined_runs(evaluated_runs: list[EvaluatedRun], scenario_name: str) -> list[JoinedRun]:
    """Return the baseline/baseline_oss runs for ``scenario_name``.

    A run is included only when ``_build_record`` accepts it — i.e. it carries a
    scope label, a budget knob, and a ``round_success`` measurement.
    """
    joined: list[JoinedRun] = []
    for run in evaluated_runs:
        if run.scenario_name != scenario_name:
            continue
        if _build_record(evaluated=run) is None:
            continue
        joined.append(JoinedRun(evaluated=run))
    return joined


def _is_canonical(labels: list[str]) -> bool:
    """True for the canonical-design cohort: the fixed ``seed=42`` runs.

    Canonical runs do not carry the ``random_seed`` label, so they used the fixed
    ``seed=42`` case set.
    """
    return _RANDOM_SEED_LABEL not in labels


def _apply_cohort_filters(
    joined_runs: list[JoinedRun],
    canonical_only: bool,
) -> list[JoinedRun]:
    """Filter by canonical design when requested."""
    out: list[JoinedRun] = []
    for joined in joined_runs:
        if canonical_only:
            record = _build_record(evaluated=joined.evaluated)
            if record is None or not _is_canonical(labels=record.labels):
                continue
        out.append(joined)
    return out


def _round_success_per_round(evaluated: EvaluatedRun) -> list[tuple[int, float, str]]:
    """Return ``(round_number, value, note)`` from the run's ``round_success`` measurement."""
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == _ROUND_SUCCESS_METRIC:
            return [(obs.round_number, obs.value, obs.note) for obs in measurement.per_round]
    return []


def _build_run_level_frame(
    joined_runs: list[JoinedRun], contexts: dict[str, RunContext]
) -> pd.DataFrame:
    """One row per run: covariates plus the Bernoulli numerator/denominator."""
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        record = _build_record(evaluated=joined.evaluated)
        if record is None:
            continue
        context = contexts[record.run_id]
        fraction = None
        if record.total_rounds > 0:
            fraction = record.round_success / record.total_rounds
        rows.append(
            {
                "run_id": record.run_id,
                "scenario": joined.evaluated.scenario_name,
                "field_observer_model": context.field_observer_model,
                "engineer_model": context.engineer_model,
                "model_class": model_class(
                    field_observer_model=context.field_observer_model,
                    engineer_model=context.engineer_model,
                ),
                "postmortem": record.postmortem_enabled,
                "round_time_budget_seconds": record.budget,
                "random_seed": _RANDOM_SEED_LABEL in record.labels,
                "total_rounds": record.total_rounds,
                "round_success_count": record.round_success,
                "round_success_fraction": fraction,
                "perplexity": record.perplexity_score,
                "english_ngram_surprisal": record.english_ngram_score,
                "message_entropy": record.message_entropy_score,
                "gzip_compression_ratio": record.gzip_compression_ratio_score,
                "mcm": record.mcm_score,
                "labels": "|".join(record.labels),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        by=[
            "model_class",
            "field_observer_model",
            "engineer_model",
            "postmortem",
            "round_time_budget_seconds",
            "run_id",
        ]
    ).reset_index(drop=True)


def _build_message_level_frame(
    joined_runs: list[JoinedRun], contexts: dict[str, RunContext]
) -> pd.DataFrame:
    """Long format: one row per link-channel message, with its substage/round context.

    Messages are walked substage by substage (substages the team reached). Substages
    with no link messages produce no rows. The substage ground truth
    (``symptoms`` / ``actions`` / ``substage_stabilized``), the round-level outcome
    (``success`` / ``note``), and the round-start briefings are repeated on every message
    row.
    """
    perplexity_scorer = MessagePerplexityScorer()
    english_ngram_scorer = MessageEnglishNgramScorer()
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        record = _build_record(evaluated=joined.evaluated)
        if record is None:
            continue
        context = contexts[record.run_id]
        run_model_class = model_class(
            field_observer_model=context.field_observer_model,
            engineer_model=context.engineer_model,
        )
        run_rows: list[dict[str, object]] = []
        for round_number, value, note in _round_success_per_round(evaluated=joined.evaluated):
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
                            "scenario": joined.evaluated.scenario_name,
                            "field_observer_model": context.field_observer_model,
                            "engineer_model": context.engineer_model,
                            "model_class": run_model_class,
                            "postmortem": record.postmortem_enabled,
                            "round_time_budget_seconds": record.budget,
                            "random_seed": _RANDOM_SEED_LABEL in record.labels,
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
        jsonl_path = joined.evaluated.run_dir / f"{joined.evaluated.scenario_name}.jsonl"
        message_texts = [str(row["message_text"]) for row in run_rows]
        perplexities = perplexity_scorer.score_run(jsonl_path=jsonl_path, texts=message_texts)
        english_ngram_surprisals = english_ngram_scorer.score_run(
            jsonl_path=jsonl_path, texts=message_texts
        )
        message_entropies = [
            character_entropy_bits(text=text) if text.strip() else None for text in message_texts
        ]
        gzip_ratios = [
            gzip_compression_ratio(text=text) if text.strip() else None for text in message_texts
        ]
        for row, perplexity, english_ngram, entropy, gzip_ratio in zip(
            run_rows, perplexities, english_ngram_surprisals, message_entropies, gzip_ratios
        ):
            row["perplexity"] = perplexity
            row["english_ngram_surprisal"] = english_ngram
            row["message_entropy"] = entropy
            row["gzip_compression_ratio"] = gzip_ratio
        rows.extend(run_rows)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        by=["run_id", "round_number", "substage", "message_index_in_substage"]
    ).reset_index(drop=True)


def _build_round_context_frame(
    joined_runs: list[JoinedRun], contexts: dict[str, RunContext]
) -> pd.DataFrame:
    """One row per (run, round) carrying the round-start briefings.

    Holds the large ``field_observer_round_event`` / ``engineer_round_event`` text once
    per round (join to ``message_level`` on ``run_id`` + ``round_number``) instead of
    repeating it on every message row.
    """
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        record = _build_record(evaluated=joined.evaluated)
        if record is None:
            continue
        context = contexts[record.run_id]
        for round_number, _, _ in _round_success_per_round(evaluated=joined.evaluated):
            round_ctx = context.rounds.get(round_number)
            if round_ctx is None:
                continue
            rows.append(
                {
                    "run_id": record.run_id,
                    "round_number": round_number,
                    "field_observer_round_event": round_ctx.field_observer_event,
                    "engineer_round_event": round_ctx.engineer_event,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(by=["run_id", "round_number"]).reset_index(drop=True)


def _build_budget_aggregate_frame(run_level: pd.DataFrame) -> pd.DataFrame:
    """Per (model, postmortem, seed mode, budget) mean ± std of the success fraction.

    ``random_seed`` is a grouping key so the aggregate never pools runs from
    different seed designs into one cell.
    """
    if run_level.empty:
        return run_level
    group_keys = [
        "model_class",
        "field_observer_model",
        "engineer_model",
        "postmortem",
        "random_seed",
        "round_time_budget_seconds",
    ]
    grouped = run_level.groupby(group_keys, as_index=False).agg(
        n=("round_success_fraction", "size"),
        mean_success_fraction=("round_success_fraction", "mean"),
        # population std (ddof=0) to match the chart's n=1 -> 0.0 error bars.
        std_success_fraction=("round_success_fraction", lambda s: s.std(ddof=0)),
        min_success_fraction=("round_success_fraction", "min"),
        max_success_fraction=("round_success_fraction", "max"),
        mean_success_count=("round_success_count", "mean"),
    )
    return grouped.sort_values(by=group_keys).reset_index(drop=True)


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for the exporter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--scenario", type=str, default="veyru")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("analysis/baseline_round_success/output")
    )
    parser.add_argument("--stem", type=str, default="baseline_round_success")
    parser.add_argument(
        "--canonical-only",
        action="store_true",
        help=(
            "Restrict to the canonical design — the fixed ``seed=42`` runs. Default "
            "keeps every seed mode, tagged by the random_seed column."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Build the three frames and write outputs."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    evaluated_runs = list_evaluated_runs(runs_dir=args.runs_dir)
    joined = _collect_joined_runs(evaluated_runs=evaluated_runs, scenario_name=args.scenario)
    kept = _apply_cohort_filters(joined_runs=joined, canonical_only=args.canonical_only)
    logger.info(
        "scenario=%s: %d baseline runs found, %d kept (canonical_only=%s).",
        args.scenario,
        len(joined),
        len(kept),
        args.canonical_only,
    )

    contexts = {
        joined.evaluated.run_id: scan_run_context(
            jsonl_path=joined.evaluated.run_dir / f"{joined.evaluated.scenario_name}.jsonl"
        )
        for joined in kept
    }
    run_level = _build_run_level_frame(joined_runs=kept, contexts=contexts)
    message_level = _build_message_level_frame(joined_runs=kept, contexts=contexts)
    round_context = _build_round_context_frame(joined_runs=kept, contexts=contexts)
    budget_aggregate = _build_budget_aggregate_frame(run_level=run_level)
    frames = {
        "run_level": run_level,
        "message_level": message_level,
        "round_context": round_context,
        "budget_aggregate": budget_aggregate,
    }

    csv_paths = write_csvs(frames=frames, output_dir=args.output_dir, stem=args.stem)
    xlsx_path = write_xlsx(frames=frames, output_dir=args.output_dir, stem=args.stem)

    logger.info(
        "Wrote %d runs, %d message-rows. CSVs: %s%s",
        len(run_level),
        len(message_level),
        ", ".join(str(p) for p in csv_paths),
        f"; workbook: {xlsx_path}" if xlsx_path is not None else "",
    )


if __name__ == "__main__":
    main()
