"""Export the veyru channel-noise sweep to a modelling-ready spreadsheet.

Covers runs labelled ``channel_noise`` (the per-character link-noise baseline
sweep) that carry a ``round_time_budget_seconds`` knob and a ``round_success``
measurement. Mirrors the ``baseline_round_success`` export's shape so the two
workbooks share a schema, with the additions the noise sweep needs.

The noise sweep's defining covariate is ``channel_noise_level`` — the
per-character drop probability applied to the link channel (postmortem stays
clean). Every table carries it. Because the link text the agent *composed*
differs from what the channel *delivered*, the ``message_level`` table reports
both: ``message_text`` is the pristine pre-transform text (joined back via the
``send_message`` ``message_id``), ``message_text_transmitted`` is what the
channel delivered (``_`` for dropped characters), and ``chars_dropped`` /
``drop_fraction`` quantify the loss. Per-message ``perplexity`` is scored on the
**pristine** text, matching the run-level ``perplexity`` metric.

Columns inherited from the baseline export that are constant across this cohort
(``model_class`` = closed, ``postmortem`` = True, ``random_seed`` = False) are
kept so the two workbooks concatenate cleanly for cross-cohort comparison.

Four output tables:

- ``run_level`` — one row per run: per-agent models, ``model_class``,
  ``postmortem``, ``round_time_budget_seconds``, ``channel_noise_level``,
  ``random_seed``, the Bernoulli numerator/denominator
  (``round_success_count`` / ``total_rounds``) and fraction, plus the run's
  headline ``perplexity`` (pristine), ``mcm``, and ``repetition`` (the
  ``language_repetition`` mean redundancy factor — encodings per information unit).
- ``message_level`` — one row per link-channel message with its substage / round
  context, the pristine and transmitted text, character-loss stats, and
  per-message pristine ``perplexity``.
- ``round_context`` — one row per (run, round): the round-start briefings plus the
  per-round ``round_success`` flag and ``repetition_factor`` (so per-round
  redundancy can be correlated with per-round success directly).
- ``budget_aggregate`` — per (models, postmortem, random_seed,
  channel_noise_level, budget) mean ± std of the success fraction and of the
  ``repetition`` factor.

Writes one CSV per table, and (when ``openpyxl`` is importable) a single
multi-sheet ``.xlsx`` workbook.
"""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from analysis.results_viewer.measurement_scores import (
    LANGUAGE_REPETITION_METRIC,
    language_repetition_score,
    mcm_score,
    perplexity_score,
    read_labels,
)
from analysis.results_viewer.run_catalog import EvaluatedRun, list_evaluated_runs
from analysis.veyru_run_export.message_perplexity_scorer import MessagePerplexityScorer
from analysis.veyru_run_export.run_context_scan import (
    RunContext,
    model_class,
    scan_run_context,
    sender_role,
)
from analysis.veyru_run_export.spreadsheet_writer import write_csvs, write_xlsx
from schmidt.evaluation.log_reader import load_events
from schmidt.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from schmidt.models.event import RoundResultRecorded, SimulationEvent

logger = logging.getLogger(__name__)


class _RoundOutcome(NamedTuple):
    """A round's joint success flag and its recorded reason."""

    success: bool
    reason: str


def _round_outcomes_from_events(events: list[SimulationEvent]) -> dict[int, _RoundOutcome]:
    """Build ``round_number -> (joint success, reason)`` straight from the JSONL events.

    Reads ``RoundResultRecorded`` directly rather than the report's
    ``round_success`` measurement, so a stale or partially-flushed
    measurement can never cause a round (and its link messages) to be
    dropped from the export. Multi-team rounds collapse to joint success.
    """
    successes: dict[int, list[bool]] = {}
    reasons: dict[int, str] = {}
    for event in events:
        if isinstance(event, RoundResultRecorded):
            successes.setdefault(event.round_number, []).append(event.success)
            reasons.setdefault(event.round_number, event.reason)
    return {
        round_number: _RoundOutcome(success=all(flags), reason=reasons.get(round_number, ""))
        for round_number, flags in successes.items()
    }


_ROUND_SUCCESS_METRIC = "round_success"
_RANDOM_SEED_LABEL = "random_seed"
_SCOPE_LABEL = "channel_noise"


class RunRecord(NamedTuple):
    """The run-level facts the channel-noise export needs."""

    run_id: str
    budget: int
    channel_noise_level: float
    postmortem_enabled: bool
    total_rounds: int
    round_success: int
    perplexity_score: float | None
    mcm_score: float | None
    repetition_score: float | None
    labels: list[str]


def _build_record(evaluated: EvaluatedRun) -> RunRecord | None:
    """Build a ``RunRecord`` for a channel_noise run, or ``None`` if it doesn't qualify.

    Qualifies when the run carries the ``channel_noise`` label, a
    ``round_time_budget_seconds`` knob, and a ``round_success`` measurement.
    """
    labels = read_labels(run_dir=evaluated.run_dir)
    if _SCOPE_LABEL not in labels:
        return None
    config = evaluated.metadata.scenario_config
    budget = config.get("round_time_budget_seconds")
    if not isinstance(budget, (int, float)):
        return None
    per_round = _round_success_per_round(evaluated=evaluated)
    if not per_round:
        return None
    noise = config.get("channel_noise_level")
    round_success = sum(1 for _, value, _ in per_round if value > 0)
    return RunRecord(
        run_id=evaluated.run_id,
        budget=int(budget),
        channel_noise_level=float(noise) if isinstance(noise, (int, float)) else 0.0,
        postmortem_enabled=bool(config.get("postmortem_enabled", False)),
        total_rounds=int(config.get("round_count", 0)),
        round_success=round_success,
        perplexity_score=perplexity_score(evaluated=evaluated),
        mcm_score=mcm_score(evaluated=evaluated),
        repetition_score=language_repetition_score(evaluated=evaluated),
        labels=labels,
    )


def _collect_runs(evaluated_runs: list[EvaluatedRun], scenario_name: str) -> list[EvaluatedRun]:
    """Return the channel_noise runs for ``scenario_name`` that ``_build_record`` accepts."""
    out: list[EvaluatedRun] = []
    for run in evaluated_runs:
        if run.scenario_name != scenario_name:
            continue
        if _build_record(evaluated=run) is None:
            continue
        out.append(run)
    return out


def _round_success_per_round(evaluated: EvaluatedRun) -> list[tuple[int, float, str]]:
    """Return ``(round_number, value, note)`` from the run's ``round_success`` measurement."""
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == _ROUND_SUCCESS_METRIC:
            return [(obs.round_number, obs.value, obs.note) for obs in measurement.per_round]
    return []


def _repetition_per_round(evaluated: EvaluatedRun) -> dict[int, float]:
    """Map ``round_number -> redundancy factor`` from the ``language_repetition`` measurement.

    Empty when the run wasn't scored for ``language_repetition``. Rounds the
    metric skipped (no primary-channel content) are absent from the map.
    """
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == LANGUAGE_REPETITION_METRIC:
            return {obs.round_number: obs.value for obs in measurement.per_round}
    return {}


def _build_run_level_frame(
    runs: list[EvaluatedRun], contexts: dict[str, RunContext]
) -> pd.DataFrame:
    """One row per run: covariates plus the Bernoulli numerator/denominator."""
    rows: list[dict[str, object]] = []
    for evaluated in runs:
        record = _build_record(evaluated=evaluated)
        if record is None:
            continue
        context = contexts[record.run_id]
        fraction = None
        if record.total_rounds > 0:
            fraction = record.round_success / record.total_rounds
        rows.append(
            {
                "run_id": record.run_id,
                "scenario": evaluated.scenario_name,
                "field_observer_model": context.field_observer_model,
                "engineer_model": context.engineer_model,
                "model_class": model_class(
                    field_observer_model=context.field_observer_model,
                    engineer_model=context.engineer_model,
                ),
                "postmortem": record.postmortem_enabled,
                "round_time_budget_seconds": record.budget,
                "channel_noise_level": record.channel_noise_level,
                "random_seed": _RANDOM_SEED_LABEL in record.labels,
                "total_rounds": record.total_rounds,
                "round_success_count": record.round_success,
                "round_success_fraction": fraction,
                "perplexity": record.perplexity_score,
                "mcm": record.mcm_score,
                "repetition": record.repetition_score,
                "labels": "|".join(record.labels),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        by=[
            "field_observer_model",
            "engineer_model",
            "channel_noise_level",
            "round_time_budget_seconds",
            "run_id",
        ]
    ).reset_index(drop=True)


def _build_message_level_frame(
    runs: list[EvaluatedRun], contexts: dict[str, RunContext]
) -> pd.DataFrame:
    """Long format: one row per link-channel message with pristine + transmitted text.

    ``message_text`` is the pristine pre-transform text the agent composed (joined
    from the ``send_message`` ``message_id``); ``message_text_transmitted`` is the
    channel-delivered text. ``chars`` is the message length (preserved under
    character-drop noise); ``chars_dropped`` counts ``_`` substitutions and
    ``drop_fraction`` normalizes it. Per-message ``perplexity`` scores the pristine
    text.
    """
    perplexity_scorer = MessagePerplexityScorer()
    rows: list[dict[str, object]] = []
    for evaluated in runs:
        record = _build_record(evaluated=evaluated)
        if record is None:
            continue
        context = contexts[record.run_id]
        jsonl_path = evaluated.run_dir / f"{evaluated.scenario_name}.jsonl"
        events = asyncio.run(load_events(log_path=jsonl_path))
        pristine_by_id = build_pristine_text_index(events=events)
        outcomes = _round_outcomes_from_events(events=events)
        run_model_class = model_class(
            field_observer_model=context.field_observer_model,
            engineer_model=context.engineer_model,
        )
        run_rows: list[dict[str, object]] = []
        # Iterate the rounds the scanner found (not the round_success measurement)
        # so a stale/partial measurement can't drop a round's messages. Success
        # and reason come straight from the JSONL round-result events.
        for round_number in sorted(context.rounds):
            round_ctx = context.rounds[round_number]
            outcome = outcomes.get(round_number, _RoundOutcome(success=False, reason=""))
            value = 1.0 if outcome.success else 0.0
            note = outcome.reason
            for substage in range(1, round_ctx.stages_reached + 1):
                stage = round_ctx.stages[substage - 1]
                messages = round_ctx.link_messages_by_substage.get(substage, [])
                for message_index, message in enumerate(messages, start=1):
                    transmitted = message.message
                    pristine = pristine_by_id.get(message.message_id, transmitted)
                    chars_dropped = transmitted.count("_")
                    chars = len(pristine)
                    drop_fraction = chars_dropped / chars if chars > 0 else None
                    run_rows.append(
                        {
                            "run_id": record.run_id,
                            "scenario": evaluated.scenario_name,
                            "field_observer_model": context.field_observer_model,
                            "engineer_model": context.engineer_model,
                            "model_class": run_model_class,
                            "postmortem": record.postmortem_enabled,
                            "round_time_budget_seconds": record.budget,
                            "channel_noise_level": record.channel_noise_level,
                            "random_seed": _RANDOM_SEED_LABEL in record.labels,
                            "round_number": round_number,
                            "substage": substage,
                            "symptoms": stage.symptoms,
                            "actions": stage.actions,
                            "substage_stabilized": int(substage <= round_ctx.stabilized_stages),
                            "message_index_in_substage": message_index,
                            "message_agent": sender_role(agent_id=message.agent),
                            "message_text": pristine,
                            "message_text_transmitted": transmitted,
                            "chars": chars,
                            "chars_dropped": chars_dropped,
                            "drop_fraction": drop_fraction,
                            "success": int(round(value)),
                            "note": note,
                        }
                    )
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
        by=["run_id", "round_number", "substage", "message_index_in_substage"]
    ).reset_index(drop=True)


def _build_round_context_frame(
    runs: list[EvaluatedRun], contexts: dict[str, RunContext]
) -> pd.DataFrame:
    """One row per (run, round): the round-start briefings plus per-round outcomes.

    Carries ``round_success`` (1/0 from the run's ``round_success`` measurement)
    and ``repetition_factor`` (the round's ``language_repetition`` redundancy
    factor, ``None`` when the round had no primary-channel content or the run
    wasn't scored), so per-round redundancy can be correlated with per-round
    success directly from this table.
    """
    rows: list[dict[str, object]] = []
    for evaluated in runs:
        record = _build_record(evaluated=evaluated)
        if record is None:
            continue
        context = contexts[record.run_id]
        success_by_round = {
            rn: value for rn, value, _ in _round_success_per_round(evaluated=evaluated)
        }
        repetition_by_round = _repetition_per_round(evaluated=evaluated)
        for round_number in sorted(context.rounds):
            round_ctx = context.rounds[round_number]
            success = success_by_round.get(round_number)
            rows.append(
                {
                    "run_id": record.run_id,
                    "round_number": round_number,
                    "channel_noise_level": record.channel_noise_level,
                    "round_time_budget_seconds": record.budget,
                    "round_success": None if success is None else int(round(success)),
                    "repetition_factor": repetition_by_round.get(round_number),
                    "field_observer_round_event": round_ctx.field_observer_event,
                    "engineer_round_event": round_ctx.engineer_event,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(by=["run_id", "round_number"]).reset_index(drop=True)


def _build_budget_aggregate_frame(run_level: pd.DataFrame) -> pd.DataFrame:
    """Per (models, postmortem, seed mode, noise, budget) mean ± std of the success fraction."""
    if run_level.empty:
        return run_level
    group_keys = [
        "model_class",
        "field_observer_model",
        "engineer_model",
        "postmortem",
        "random_seed",
        "channel_noise_level",
        "round_time_budget_seconds",
    ]
    grouped = run_level.groupby(group_keys, as_index=False).agg(
        n=("round_success_fraction", "size"),
        mean_success_fraction=("round_success_fraction", "mean"),
        std_success_fraction=("round_success_fraction", lambda s: s.std(ddof=0)),
        min_success_fraction=("round_success_fraction", "min"),
        max_success_fraction=("round_success_fraction", "max"),
        mean_success_count=("round_success_count", "mean"),
        mean_repetition=("repetition", "mean"),
        std_repetition=("repetition", lambda s: s.std(ddof=0)),
    )
    return grouped.sort_values(by=group_keys).reset_index(drop=True)


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for the exporter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--scenario", type=str, default="veyru")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("analysis/channel_noise_export/output")
    )
    parser.add_argument("--stem", type=str, default="channel_noise")
    return parser.parse_args()


def main() -> None:
    """Build the four frames and write outputs."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    evaluated_runs = list_evaluated_runs(runs_dir=args.runs_dir)
    runs = _collect_runs(evaluated_runs=evaluated_runs, scenario_name=args.scenario)
    logger.info("scenario=%s: %d channel_noise runs found.", args.scenario, len(runs))

    contexts = {
        evaluated.run_id: scan_run_context(
            jsonl_path=evaluated.run_dir / f"{evaluated.scenario_name}.jsonl"
        )
        for evaluated in runs
    }
    run_level = _build_run_level_frame(runs=runs, contexts=contexts)
    message_level = _build_message_level_frame(runs=runs, contexts=contexts)
    round_context = _build_round_context_frame(runs=runs, contexts=contexts)
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
