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

By default every seed mode and easy-round skeleton is included; two columns mark
each run's design so they can be modelled or subset downstream:

- ``random_seed`` — True when the run used a per-launch random seed, False for the
  canonical fixed ``seed=42``.
- ``easy_rounds`` — True when the run used the default ordered easy-round warmups
  (rounds 1/2/3/6/13 forced single-stage), False for the ``no_ordered_easy_rounds``
  design. Pass ``--canonical-only`` to keep just fixed-seed + default-easy runs.

Per-agent models come from the run's ``AgentRegistered`` events: every table carries
``field_observer_model`` and ``engineer_model`` instead of a single ``model`` column.

Four output tables:

- ``run_level`` — one row per run (the replica dots on the chart). The Bernoulli
  numerator/denominator (``round_success_count`` / ``total_rounds``) supports a
  binomial GLMM ``cbind(successes, failures) ~ ...`` and the fraction supports a
  beta/linear model. Also carries the run's headline ``perplexity`` (overall mean
  per-token surprisal) and ``mcm`` (overall mean chars per message) from the report.
- ``message_level`` — one row per link-channel message. Each row carries its substage
  context (``substage``, ``symptoms`` / ``actions``, ``substage_stabilized``),
  ``message_index_in_substage``, ``message_agent`` (sender role, normalized to
  ``field_observer`` or ``stabilization_engineer``), ``message_text``, ``chars``
  (``len(message_text)``), ``perplexity`` (per-message mean per-token surprisal in nats
  under gpt2; blank for empty/single-token messages), and the round-level
  ``success`` / ``success_raw`` / ``note``. Messages are walked over the substages the
  team reached (``min(stabilized_stages + 1, total_stages)``); substages with no link
  traffic produce no rows.
- ``round_context`` — one row per (run, round) holding the large round-start briefings
  (``field_observer_round_event`` / ``engineer_round_event``). Kept separate (join on
  ``run_id`` + ``round_number``) so the briefing text is stored once per round rather
  than duplicated on every message row.
- ``budget_aggregate`` — per (models, postmortem, random_seed, easy_rounds, budget)
  mean ± std of the success fraction; a sanity check against the plotted bands.

Writes one CSV per table, and (when ``openpyxl`` is importable) a single
multi-sheet ``.xlsx`` workbook.
"""

import argparse
import importlib.util
import logging
import math
from pathlib import Path
from typing import NamedTuple

import orjson
import pandas as pd

from analysis.results_viewer.baseline_data import build_baseline_run
from analysis.results_viewer.run_catalog import EvaluatedRun, list_evaluated_runs
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_ID,
    LINK_CHANNEL_IDS,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_B_ID,
    STABILIZATION_ENGINEER_ID,
)

logger = logging.getLogger(__name__)

_ROUND_SUCCESS_METRIC = "round_success"
_RANDOM_SEED_LABEL = "random_seed"
_NO_ORDERED_EASY_ROUNDS_LABEL = "no_ordered_easy_rounds"
_KIND_TO_MODEL_CLASS = {"baseline": "closed", "baseline_oss": "open"}

_FIELD_OBSERVER_IDS = frozenset({FIELD_OBSERVER_ID, OBSERVER_A_ID, OBSERVER_B_ID})
# "specialist" is a legacy agent_id some early runs used for the engineer role.
_ENGINEER_IDS = frozenset(
    {
        STABILIZATION_ENGINEER_ID,
        STABILIZATION_ENGINEER_A_ID,
        STABILIZATION_ENGINEER_B_ID,
        "specialist",
    }
)


class StageGroundTruth(NamedTuple):
    """One stage's ground truth: the symptoms the observer saw and the expected procedure."""

    symptoms: str
    actions: str


class LinkMessage(NamedTuple):
    """One link-channel message: which agent sent it and the text."""

    agent: str
    message: str


class RoundContext(NamedTuple):
    """Per-round veyru ground truth and per-agent context read from the event log.

    ``stages_reached`` is the number of stages the team actually progressed to:
    ``min(stabilized_stages + 1, total_stages)`` (the team always sees stage 1, each
    stabilized stage unlocks the next, and the stage they ended on counts as reached).
    Substages beyond ``stages_reached`` are not emitted. ``stabilized_stages`` is the
    count of stages successfully stabilized this round. ``link_messages_by_substage``
    maps a 1-indexed substage to the link-channel messages exchanged while it was active.
    """

    stages: list[StageGroundTruth]
    stages_reached: int
    stabilized_stages: int
    field_observer_event: str
    engineer_event: str
    link_messages_by_substage: dict[int, list[LinkMessage]]


class RunContext(NamedTuple):
    """Per-run agent models plus per-round context, keyed by round number."""

    field_observer_model: str
    engineer_model: str
    rounds: dict[int, RoundContext]


class JoinedRun(NamedTuple):
    """A baseline run paired with its source ``EvaluatedRun``."""

    evaluated: EvaluatedRun


def _resolve_model(models: dict[str, str], candidate_ids: frozenset[str]) -> str:
    """Return the first registered model whose agent_id is in ``candidate_ids`` (or "")."""
    for agent_id, model in models.items():
        if agent_id in candidate_ids:
            return model
    return ""


def _sender_role(agent_id: str) -> str:
    """Normalize a sender agent_id to a role: ``field_observer`` or ``stabilization_engineer``.

    The engineer role appears under several ids (``stabilization_engineer``, the two-team
    ``_a`` / ``_b`` variants, and the legacy ``specialist``); they all map to
    ``stabilization_engineer``. Field observers map to ``field_observer``. Any other
    sender falls back to its raw agent_id.
    """
    if agent_id in _FIELD_OBSERVER_IDS:
        return FIELD_OBSERVER_ID
    if agent_id in _ENGINEER_IDS:
        return STABILIZATION_ENGINEER_ID
    return agent_id


def _injection_for(
    injections: dict[tuple[int, str], str], round_number: int, candidate_ids: frozenset[str]
) -> str:
    """Return the round-start briefing delivered to the matching agent that round (or "")."""
    for agent_id in candidate_ids:
        text = injections.get((round_number, agent_id))
        if text is not None:
            return text
    return ""


def _bucket_link_messages(
    raw_buckets: dict[int, list[LinkMessage]], stages_reached: int
) -> dict[int, list[LinkMessage]]:
    """Clamp raw per-substage message buckets into ``1..stages_reached``.

    Any messages recorded past the last reached substage (e.g. sent after the final
    stabilization of a fully-solved round) fold into ``stages_reached``, preserving
    chronological order by walking the raw substage indices in ascending order.
    """
    if stages_reached < 1:
        return {}
    clamped: dict[int, list[LinkMessage]] = {}
    for substage in sorted(raw_buckets):
        index = min(max(substage, 1), stages_reached)
        clamped.setdefault(index, []).extend(raw_buckets[substage])
    return clamped


def _scan_run_context(jsonl_path: Path) -> RunContext:
    """Read a run's JSONL once and extract per-agent models + per-round veyru context.

    Tracks the most recent ``round_advanced`` to backfill ``round_number`` on older
    logs. ``stages`` come from ``veyru_case_started``; ``stabilized_stages`` from the
    count of ``veyru_stabilization_judged`` events with ``judge_match=True`` (matching
    ``outcome_reconstruction``); the round-start briefing is the first
    ``injection_delivered`` per (round, agent). Each link-channel ``message_sent`` is
    bucketed into the substage active when it was sent — a per-round counter that starts
    at 1 and advances on every ``judge_match=True`` — so messages are attributed to the
    stage the team was working on.
    """
    models: dict[str, str] = {}
    stages_by_round: dict[int, list[StageGroundTruth]] = {}
    matched_by_round: dict[int, int] = {}
    injections: dict[tuple[int, str], str] = {}
    links_by_round_substage: dict[tuple[int, int], list[LinkMessage]] = {}
    current_substage: dict[int, int] = {}
    running_round = 0
    with jsonl_path.open("rb") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = orjson.loads(line)
            event_type = raw.get("event_type")
            if event_type == "round_advanced":
                advanced = raw.get("round_number")
                if isinstance(advanced, int):
                    running_round = advanced
            round_number = raw.get("round_number")
            if not isinstance(round_number, int):
                round_number = running_round
            if event_type == "agent_registered":
                agent_id = raw.get("agent_id")
                model = raw.get("model")
                if isinstance(agent_id, str) and isinstance(model, str) and agent_id not in models:
                    models[agent_id] = model
            elif event_type == "veyru_case_started" and round_number >= 1:
                stages_by_round.setdefault(
                    round_number,
                    [
                        StageGroundTruth(
                            symptoms=str(stage.get("observable_symptoms", "")),
                            actions=str(stage.get("judge_expected_actions", "")),
                        )
                        for stage in raw.get("stages", [])
                    ],
                )
            elif event_type == "veyru_stabilization_judged" and round_number >= 1:
                if raw.get("judge_match") is True:
                    matched_by_round[round_number] = matched_by_round.get(round_number, 0) + 1
                    current_substage[round_number] = current_substage.get(round_number, 1) + 1
            elif event_type == "injection_delivered" and round_number >= 1:
                agent_id = raw.get("agent_id")
                if isinstance(agent_id, str):
                    injections.setdefault((round_number, agent_id), str(raw.get("text", "")))
            elif event_type == "message_sent" and round_number >= 1:
                message = raw.get("message") or {}
                if message.get("channel_id") in LINK_CHANNEL_IDS:
                    substage = current_substage.get(round_number, 1)
                    links_by_round_substage.setdefault((round_number, substage), []).append(
                        LinkMessage(
                            agent=str(message.get("sender_agent_id", "")),
                            message=str(message.get("text", "")),
                        )
                    )
    links_grouped: dict[int, dict[int, list[LinkMessage]]] = {}
    for (round_number, substage), messages in links_by_round_substage.items():
        links_grouped.setdefault(round_number, {})[substage] = messages
    rounds: dict[int, RoundContext] = {}
    all_rounds = (
        set(stages_by_round)
        | set(matched_by_round)
        | set(links_grouped)
        | {round_number for round_number, _ in injections}
    )
    for round_number in all_rounds:
        stages = stages_by_round.get(round_number, [])
        total = len(stages)
        matched = matched_by_round.get(round_number, 0)
        stages_reached = min(matched + 1, total) if total >= 1 else 0
        rounds[round_number] = RoundContext(
            stages=stages,
            stages_reached=stages_reached,
            stabilized_stages=matched,
            field_observer_event=_injection_for(injections, round_number, _FIELD_OBSERVER_IDS),
            engineer_event=_injection_for(injections, round_number, _ENGINEER_IDS),
            link_messages_by_substage=_bucket_link_messages(
                raw_buckets=links_grouped.get(round_number, {}), stages_reached=stages_reached
            ),
        )
    return RunContext(
        field_observer_model=_resolve_model(models=models, candidate_ids=_FIELD_OBSERVER_IDS),
        engineer_model=_resolve_model(models=models, candidate_ids=_ENGINEER_IDS),
        rounds=rounds,
    )


def _collect_joined_runs(evaluated_runs: list[EvaluatedRun], scenario_name: str) -> list[JoinedRun]:
    """Return the baseline/baseline_oss runs for ``scenario_name``.

    A run is included only when ``build_baseline_run`` accepts it — i.e. it
    carries a baseline label, a budget knob, and a ``round_success`` measurement.
    """
    joined: list[JoinedRun] = []
    for run in evaluated_runs:
        if run.scenario_name != scenario_name:
            continue
        if build_baseline_run(evaluated=run) is None:
            continue
        joined.append(JoinedRun(evaluated=run))
    return joined


def _is_canonical(labels: list[str]) -> bool:
    """True for the canonical-design cohort: fixed seed and default easy-round skeleton.

    Canonical runs carry neither the ``random_seed`` label (so they used the
    fixed ``seed=42``) nor the ``no_ordered_easy_rounds`` label (so rounds
    1/2/3/6/13 are the default forced single-stage warmups).
    """
    if _RANDOM_SEED_LABEL in labels:
        return False
    return _NO_ORDERED_EASY_ROUNDS_LABEL not in labels


def _apply_cohort_filters(
    joined_runs: list[JoinedRun],
    canonical_only: bool,
) -> list[JoinedRun]:
    """Filter by canonical design when requested."""
    out: list[JoinedRun] = []
    for joined in joined_runs:
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


def _build_run_level_frame(
    joined_runs: list[JoinedRun], contexts: dict[str, RunContext]
) -> pd.DataFrame:
    """One row per run: covariates plus the Bernoulli numerator/denominator."""
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        baseline = build_baseline_run(evaluated=joined.evaluated)
        if baseline is None:
            continue
        context = contexts[baseline.run_id]
        fraction = None
        if baseline.total_rounds > 0:
            fraction = baseline.round_success / baseline.total_rounds
        rows.append(
            {
                "run_id": baseline.run_id,
                "scenario": joined.evaluated.scenario_name,
                "field_observer_model": context.field_observer_model,
                "engineer_model": context.engineer_model,
                "model_class": _KIND_TO_MODEL_CLASS[baseline.kind],
                "postmortem": baseline.postmortem_enabled,
                "round_time_budget_seconds": baseline.budget,
                "random_seed": _RANDOM_SEED_LABEL in baseline.labels,
                "easy_rounds": _NO_ORDERED_EASY_ROUNDS_LABEL not in baseline.labels,
                "total_rounds": baseline.total_rounds,
                "round_success_count": baseline.round_success,
                "round_success_fraction": fraction,
                "perplexity": baseline.perplexity_score,
                "mcm": baseline.mcm_score,
                "labels": "|".join(baseline.labels),
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


def _score_message_perplexities(texts: list[str]) -> list[float | None]:
    """Per-message mean per-token surprisal (nats) under gpt2, aligned with ``texts``.

    Mirrors the ``perplexity`` metric: ``minicons.IncrementalLMScorer`` with
    ``reduction = -x.mean(0)``. Empty messages and single-token inputs (which return
    NaN — no left context) map to ``None`` so the column stays numeric elsewhere.
    """
    import torch
    from minicons import scorer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("perplexity: scoring %d messages with gpt2 on %s", len(texts), device)
    lm_scorer = scorer.IncrementalLMScorer("gpt2", device)

    def _negative_mean(tensor: object) -> float:
        return -tensor.mean(0).item()  # type: ignore[attr-defined]

    results: list[float | None] = [None] * len(texts)
    scored_indices = [index for index, text in enumerate(texts) if text and text.strip()]
    batch_size = 256
    flat_scores: list[float] = []
    for start in range(0, len(scored_indices), batch_size):
        chunk = [texts[i] for i in scored_indices[start : start + batch_size]]
        flat_scores.extend(lm_scorer.sequence_score(chunk, reduction=_negative_mean))
    for index, score in zip(scored_indices, flat_scores):
        value = float(score)
        if not math.isnan(value):
            results[index] = value
    return results


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
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        baseline = build_baseline_run(evaluated=joined.evaluated)
        if baseline is None:
            continue
        context = contexts[baseline.run_id]
        for round_number, value, note in _round_success_per_round(evaluated=joined.evaluated):
            round_ctx = context.rounds.get(round_number)
            if round_ctx is None:
                continue
            for substage in range(1, round_ctx.stages_reached + 1):
                stage = round_ctx.stages[substage - 1]
                messages = round_ctx.link_messages_by_substage.get(substage, [])
                for message_index, message in enumerate(messages, start=1):
                    rows.append(
                        {
                            "run_id": baseline.run_id,
                            "scenario": joined.evaluated.scenario_name,
                            "field_observer_model": context.field_observer_model,
                            "engineer_model": context.engineer_model,
                            "model_class": _KIND_TO_MODEL_CLASS[baseline.kind],
                            "postmortem": baseline.postmortem_enabled,
                            "round_time_budget_seconds": baseline.budget,
                            "random_seed": _RANDOM_SEED_LABEL in baseline.labels,
                            "easy_rounds": _NO_ORDERED_EASY_ROUNDS_LABEL not in baseline.labels,
                            "round_number": round_number,
                            "substage": substage,
                            "symptoms": stage.symptoms,
                            "actions": stage.actions,
                            "substage_stabilized": int(substage <= round_ctx.stabilized_stages),
                            "message_index_in_substage": message_index,
                            "message_agent": _sender_role(agent_id=message.agent),
                            "message_text": message.message,
                            "chars": len(message.message),
                            "success": int(round(value)),
                            "success_raw": value,
                            "note": note,
                        }
                    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["perplexity"] = _score_message_perplexities(texts=frame["message_text"].tolist())
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
        baseline = build_baseline_run(evaluated=joined.evaluated)
        if baseline is None:
            continue
        context = contexts[baseline.run_id]
        for round_number, _, _ in _round_success_per_round(evaluated=joined.evaluated):
            round_ctx = context.rounds.get(round_number)
            if round_ctx is None:
                continue
            rows.append(
                {
                    "run_id": baseline.run_id,
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
    """Per (model, postmortem, seed mode, easy-rounds, budget) mean ± std of the success fraction.

    ``random_seed`` and ``easy_rounds`` are grouping keys so the aggregate never
    pools runs from different experimental designs into one cell.
    """
    if run_level.empty:
        return run_level
    group_keys = [
        "model_class",
        "field_observer_model",
        "engineer_model",
        "postmortem",
        "random_seed",
        "easy_rounds",
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
    parser.add_argument(
        "--output-dir", type=Path, default=Path("analysis/baseline_round_success/output")
    )
    parser.add_argument("--stem", type=str, default="baseline_round_success")
    parser.add_argument(
        "--canonical-only",
        action="store_true",
        help=(
            "Restrict to the canonical design — fixed seed and default easy-round "
            "warmups. Default keeps every seed mode / easy-round skeleton, tagged "
            "by the random_seed and easy_rounds columns."
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
        joined.evaluated.run_id: _scan_run_context(
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

    csv_paths = _write_csvs(frames=frames, output_dir=args.output_dir, stem=args.stem)
    xlsx_path = _write_xlsx(frames=frames, output_dir=args.output_dir, stem=args.stem)

    logger.info(
        "Wrote %d runs, %d message-rows. CSVs: %s%s",
        len(run_level),
        len(message_level),
        ", ".join(str(p) for p in csv_paths),
        f"; workbook: {xlsx_path}" if xlsx_path is not None else "",
    )


if __name__ == "__main__":
    main()
