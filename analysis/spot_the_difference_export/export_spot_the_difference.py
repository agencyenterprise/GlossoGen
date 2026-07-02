"""Export the spot_the_difference cohort to a modelling-ready spreadsheet.

spot_the_difference is a two-team scenario: each team runs two viewers (a left
viewer holding scene A and a right viewer holding scene B) who talk on a private
link channel and submit the differences they find. The scoring gate is
correctness (every planted difference found, no false positives, within the
character budget); in two-team mode the eligible team with the *fewest* link
characters wins. Every char/language metric is scored per team, so the report
carries ``round_success_team_a`` / ``round_success_team_b``,
``perplexity_team_a`` / ``perplexity_team_b``, and so on — this export is the
per-team counterpart to the veyru/drive single-team exports.

The unit of analysis is **(run, team)**: a two-team run contributes two rows to
``run_level`` (one per team), keyed by ``team_id``.

Four output tables:

- ``run_level`` — one row per (run, team). Per-team outcome numerators
  (``round_success_count`` / ``round_count`` / fraction — the correctness gate;
  ``wins_count`` / ``wins_fraction`` — the fewest-characters competitive win;
  ``mean_found_fraction`` partial credit; ``mean_characters_used``;
  ``budget_exceeded_count`` / ``did_not_submit_count`` / ``disagreed_count``) and
  the per-team headline language metrics (``perplexity``,
  ``english_ngram_surprisal``, ``message_entropy``, ``gzip_compression_ratio``,
  ``language_repetition``, ``mcm``, ``mcr``).
- ``round_level`` — one row per (run, round, team): the per-round-per-team
  outcome reconstructed from the event log (``success`` = eligible, ``won``,
  ``found_count`` / ``found_fraction``, ``false_positive_count``, ``found_all``,
  ``submitted``, ``budget_exceeded``, ``characters_used``, ``members_submitted``
  / ``members_required`` / ``agreed``, the opponent's ``characters`` /
  ``found_all`` / ``eligible`` for head-to-head, and the human-readable
  ``reason``) plus the scene facts (``difference_count``, ``difference_kinds``,
  ``object_count``, ``grid_size``) and the per-round-per-team ``perplexity`` /
  ``mcr`` / ``language_repetition``.
- ``message_level`` — one row per link-channel message: ``message_agent``
  (``viewer_left`` / ``viewer_right``), ``message_text`` (pristine), the
  channel-delivered ``message_text_transmitted``, ``chars``, per-message
  ``perplexity`` / ``english_ngram_surprisal`` / ``message_entropy`` /
  ``gzip_compression_ratio`` / ``message_repetition_factor``, and the round's team
  ``success`` / ``won``.
- ``team_aggregate`` — per (model_class, viewer models, all_must_submit) mean ± std
  of the success and win fractions plus mean characters / perplexity / repetition;
  a sanity check against the run-level rows.

Writes one CSV per table, and (when ``openpyxl`` is importable) a single
multi-sheet ``.xlsx`` workbook.
"""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from analysis.results_viewer.measurement_scores import measurement_score, read_labels
from analysis.results_viewer.run_catalog import EvaluatedRun, list_evaluated_runs
from analysis.run_export.message_english_ngram_scorer import MessageEnglishNgramScorer
from analysis.run_export.message_perplexity_scorer import MessagePerplexityScorer
from analysis.run_export.message_repetition_sidecar import read_message_repetition_factors
from analysis.run_export.run_context_scan import model_class
from analysis.run_export.spreadsheet_writer import write_csvs, write_xlsx
from schmidt.evaluation.log_reader import load_events
from schmidt.evaluation.metric_core.character_entropy import character_entropy_bits
from schmidt.evaluation.metric_core.gzip_compression import gzip_compression_ratio
from schmidt.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from schmidt.models.event import AgentRegistered, MessageSent, RoundResultRecorded, SimulationEvent
from schmidt.scenarios.spot_the_difference.events import SpotTheDifferenceCaseStarted
from schmidt.scenarios.spot_the_difference.ids import (
    TEAM_SOLO_ID,
    VIEWER_LEFT_A_ID,
    VIEWER_LEFT_B_ID,
    VIEWER_LEFT_ID,
    VIEWER_RIGHT_A_ID,
    VIEWER_RIGHT_B_ID,
    VIEWER_RIGHT_ID,
)
from schmidt.scenarios.spot_the_difference.outcome_reconstruction import (
    restore_outcomes_from_events,
)
from schmidt.scenarios.spot_the_difference.scene_generation import DiffCase
from schmidt.scenarios.spot_the_difference.team_routing import (
    AGENT_ID_TO_TEAM_ID,
    link_channel_id_for_team,
    team_id_for_agent,
    team_id_for_channel,
    viewer_left_id_for_team,
    viewer_right_id_for_team,
)
from schmidt.scenarios.spot_the_difference.world_state import DiffOutcome, TeamState

logger = logging.getLogger(__name__)

SCENARIO_NAME = "spot_the_difference"
_SCOPE_LABEL = "baseline"
_RANDOM_SEED_LABEL = "random_seed"

_VIEWER_LEFT_IDS = frozenset({VIEWER_LEFT_ID, VIEWER_LEFT_A_ID, VIEWER_LEFT_B_ID})
_VIEWER_RIGHT_IDS = frozenset({VIEWER_RIGHT_ID, VIEWER_RIGHT_A_ID, VIEWER_RIGHT_B_ID})

# (metric base name, output column) for the per-team char/language metrics. The
# base name is suffixed with the team id for two-team runs (``perplexity_team_a``)
# and left bare for solo runs (``perplexity``), matching ``PrimaryChannel.metric_name``.
_TEAM_METRIC_COLUMNS = (
    ("perplexity", "perplexity"),
    ("english_ngram_surprisal", "english_ngram_surprisal"),
    ("message_entropy", "message_entropy"),
    ("gzip_compression_ratio", "gzip_compression_ratio"),
    ("language_repetition", "language_repetition"),
    ("mean_chars_per_message", "mcm"),
    ("mean_chars_per_round", "mcr"),
)


class TeamModels(NamedTuple):
    """The two viewer models that staffed one team."""

    viewer_left_model: str
    viewer_right_model: str


class LinkMsg(NamedTuple):
    """One link-channel message sent by a team's viewer."""

    round_number: int
    agent_id: str
    message_id: str
    transmitted_text: str


class SpotRunContext(NamedTuple):
    """Everything one spot run's event log yields, scanned once and reused per frame.

    ``outcomes`` maps ``round_number -> team_id -> DiffOutcome`` (reconstructed via
    the same scoring path the world uses). ``round_result`` maps
    ``(round_number, result_team_id) -> RoundResultRecorded`` where
    ``result_team_id`` is ``None`` in solo mode.
    """

    two_teams: bool
    all_must_submit: bool
    team_ids: list[str]
    models_by_team: dict[str, TeamModels]
    cases: dict[int, SpotTheDifferenceCaseStarted]
    outcomes: dict[int, dict[str, DiffOutcome]]
    link_messages: dict[str, dict[int, list[LinkMsg]]]
    round_result: dict[tuple[int, str | None], RoundResultRecorded]


def _metric_name(base: str, two_teams: bool, team_id: str) -> str:
    """Return the per-team metric name: ``base`` for solo, ``base_{team_id}`` for two teams."""
    if two_teams:
        return f"{base}_{team_id}"
    return base


def _fraction(numerator: float, denominator: float) -> float | None:
    """Return ``numerator / denominator`` or ``None`` when the denominator is not positive."""
    if denominator <= 0:
        return None
    return numerator / denominator


def _result_team_id(team_id: str, two_teams: bool) -> str | None:
    """Map a world team id to the ``RoundResultRecorded.team_id`` (``None`` in solo mode)."""
    if two_teams:
        return team_id
    return None


def _team_metric_score(
    evaluated: EvaluatedRun, base: str, two_teams: bool, team_id: str
) -> float | None:
    """Return the headline score for a per-team metric on this run, or ``None`` if unscored."""
    return measurement_score(
        evaluated=evaluated,
        metric_name=_metric_name(base=base, two_teams=two_teams, team_id=team_id),
    )


def _team_metric_per_round(
    evaluated: EvaluatedRun, base: str, two_teams: bool, team_id: str
) -> dict[int, float]:
    """Return ``round_number -> value`` for a per-team metric, empty if the run wasn't scored."""
    target = _metric_name(base=base, two_teams=two_teams, team_id=team_id)
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == target:
            return {obs.round_number: obs.value for obs in measurement.per_round}
    return {}


def _team_model_class(models: TeamModels) -> str:
    """Return ``closed`` / ``open`` / ``mixed`` from the team's two viewer models."""
    return model_class(
        role_models={
            "viewer_left": models.viewer_left_model,
            "viewer_right": models.viewer_right_model,
        }
    )


def _minimal_cases(cases: dict[int, SpotTheDifferenceCaseStarted]) -> list[DiffCase]:
    """Build the ``DiffCase`` list the outcome reconstructor needs (scenes left empty).

    ``build_round_outcomes`` reads every fact it needs from the event log; the
    reconstructor only uses this list for its length guard and a fallback the
    events make unnecessary, so the scene / difference tuples are left empty.
    """
    max_round = 0
    if cases:
        max_round = max(cases)
    out: list[DiffCase] = []
    for round_number in range(1, max_round + 1):
        event = cases.get(round_number)
        if event is None:
            out.append(
                DiffCase(
                    case_number=round_number,
                    grid_size=0,
                    round_time_budget_seconds=0,
                    difference_count=0,
                    scene_a=(),
                    scene_b=(),
                    differences=(),
                )
            )
            continue
        out.append(
            DiffCase(
                case_number=event.case_number,
                grid_size=event.grid_size,
                round_time_budget_seconds=event.round_time_budget_seconds,
                difference_count=event.difference_count,
                scene_a=(),
                scene_b=(),
                differences=(),
            )
        )
    return out


def _reconstruct_outcomes(
    events: list[SimulationEvent],
    team_ids: list[str],
    all_must_submit: bool,
    two_teams: bool,
    cases: dict[int, SpotTheDifferenceCaseStarted],
) -> dict[int, dict[str, DiffOutcome]]:
    """Rebuild ``round_number -> team_id -> DiffOutcome`` via the world's scoring path.

    Seeds one fresh ``TeamState`` per team and replays the event log through the
    same reconstructor the resume flow uses, so the correctness gate and
    fewest-characters win are computed exactly as they were live.
    """
    members_by_team: dict[str, set[str]] = {team_id: set() for team_id in team_ids}
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id in AGENT_ID_TO_TEAM_ID:
            members_by_team[team_id_for_agent(agent_id=event.agent_id)].add(event.agent_id)
    teams: dict[str, TeamState] = {}
    for team_id in team_ids:
        teams[team_id] = TeamState(
            team_id=team_id,
            link_channel_id=link_channel_id_for_team(team_id=team_id),
            member_agent_ids=frozenset(members_by_team[team_id]),
            all_must_submit=all_must_submit,
        )
    restore_outcomes_from_events(
        teams=teams, cases=_minimal_cases(cases=cases), two_teams=two_teams, events=events
    )
    outcomes: dict[int, dict[str, DiffOutcome]] = {}
    for team_id, team in teams.items():
        for outcome in team.outcomes:
            outcomes.setdefault(outcome.case_number, {})[team_id] = outcome
    return outcomes


def _team_ids_from_events(events: list[SimulationEvent]) -> list[str]:
    """Return the sorted team ids that registered viewers this run."""
    team_ids: set[str] = set()
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id in AGENT_ID_TO_TEAM_ID:
            team_ids.add(team_id_for_agent(agent_id=event.agent_id))
    return sorted(team_ids)


def _models_for_team(events: list[SimulationEvent], team_id: str) -> TeamModels:
    """Resolve the left/right viewer models that staffed ``team_id`` from AgentRegistered."""
    model_by_agent: dict[str, str] = {}
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id not in model_by_agent:
            model_by_agent[event.agent_id] = event.model
    return TeamModels(
        viewer_left_model=model_by_agent.get(viewer_left_id_for_team(team_id=team_id), ""),
        viewer_right_model=model_by_agent.get(viewer_right_id_for_team(team_id=team_id), ""),
    )


def _link_messages(
    events: list[SimulationEvent], team_ids: list[str]
) -> dict[str, dict[int, list[LinkMsg]]]:
    """Return ``team_id -> round_number -> [LinkMsg]`` for every link-channel message, in order."""
    by_team: dict[str, dict[int, list[LinkMsg]]] = {team_id: {} for team_id in team_ids}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        message_team_id = team_id_for_channel(channel_id=event.message.channel_id)
        if message_team_id is None or message_team_id not in by_team:
            continue
        by_team[message_team_id].setdefault(event.round_number, []).append(
            LinkMsg(
                round_number=event.round_number,
                agent_id=event.message.sender_agent_id,
                message_id=event.message.message_id,
                transmitted_text=event.message.text,
            )
        )
    return by_team


def _round_results(
    events: list[SimulationEvent],
) -> dict[tuple[int, str | None], RoundResultRecorded]:
    """Return ``(round_number, team_id) -> RoundResultRecorded`` (team_id ``None`` in solo mode)."""
    results: dict[tuple[int, str | None], RoundResultRecorded] = {}
    for event in events:
        if isinstance(event, RoundResultRecorded):
            results[(event.round_number, event.team_id)] = event
    return results


def _case_events(events: list[SimulationEvent]) -> dict[int, SpotTheDifferenceCaseStarted]:
    """Return ``round_number -> SpotTheDifferenceCaseStarted`` for each round's scene pair."""
    cases: dict[int, SpotTheDifferenceCaseStarted] = {}
    for event in events:
        if isinstance(event, SpotTheDifferenceCaseStarted):
            cases[event.round_number] = event
    return cases


def build_spot_context(evaluated: EvaluatedRun) -> SpotRunContext | None:
    """Scan one spot run's JSONL once into a :class:`SpotRunContext`, or ``None`` if empty."""
    jsonl_path = evaluated.run_dir / f"{evaluated.scenario_name}.jsonl"
    events = asyncio.run(load_events(log_path=jsonl_path))
    team_ids = _team_ids_from_events(events=events)
    if not team_ids:
        return None
    two_teams = TEAM_SOLO_ID not in team_ids
    all_must_submit = bool(evaluated.metadata.scenario_config.get("all_must_submit", True))
    cases = _case_events(events=events)
    outcomes = _reconstruct_outcomes(
        events=events,
        team_ids=team_ids,
        all_must_submit=all_must_submit,
        two_teams=two_teams,
        cases=cases,
    )
    if not outcomes:
        return None
    return SpotRunContext(
        two_teams=two_teams,
        all_must_submit=all_must_submit,
        team_ids=team_ids,
        models_by_team={
            team_id: _models_for_team(events=events, team_id=team_id) for team_id in team_ids
        },
        cases=cases,
        outcomes=outcomes,
        link_messages=_link_messages(events=events, team_ids=team_ids),
        round_result=_round_results(events=events),
    )


class JoinedRun(NamedTuple):
    """A qualifying spot run paired with its scanned context."""

    evaluated: EvaluatedRun
    context: SpotRunContext


def _collect_runs(evaluated_runs: list[EvaluatedRun], canonical_only: bool) -> list[JoinedRun]:
    """Return the in-scope spot runs (scope label present) paired with their scanned context."""
    joined: list[JoinedRun] = []
    for run in evaluated_runs:
        if run.scenario_name != SCENARIO_NAME:
            continue
        labels = read_labels(run_dir=run.run_dir)
        if _SCOPE_LABEL not in labels:
            continue
        if canonical_only and _RANDOM_SEED_LABEL in labels:
            continue
        context = build_spot_context(evaluated=run)
        if context is None:
            continue
        joined.append(JoinedRun(evaluated=run, context=context))
    return joined


def _team_outcomes(context: SpotRunContext, team_id: str) -> list[DiffOutcome]:
    """Return every round's ``DiffOutcome`` for one team, ordered by round."""
    out: list[DiffOutcome] = []
    for round_number in sorted(context.outcomes):
        outcome = context.outcomes[round_number].get(team_id)
        if outcome is not None:
            out.append(outcome)
    return out


def _config_int(evaluated: EvaluatedRun, key: str) -> int:
    """Read an int knob from the run's scenario_config, defaulting to 0 when absent."""
    value = evaluated.metadata.scenario_config.get(key)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _build_run_level(joined_runs: list[JoinedRun]) -> pd.DataFrame:
    """One row per (run, team): covariates, per-team outcome numerators, and metrics."""
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        evaluated = joined.evaluated
        context = joined.context
        labels = read_labels(run_dir=evaluated.run_dir)
        config = evaluated.metadata.scenario_config
        round_count = _config_int(evaluated=evaluated, key="round_count")
        for team_id in context.team_ids:
            outcomes = _team_outcomes(context=context, team_id=team_id)
            models = context.models_by_team[team_id]
            row: dict[str, object] = {
                "run_id": evaluated.run_id,
                "scenario": evaluated.scenario_name,
                "team_id": team_id,
                "all_must_submit": context.all_must_submit,
                "viewer_left_model": models.viewer_left_model,
                "viewer_right_model": models.viewer_right_model,
                "model_class": _team_model_class(models=models),
                "round_count": round_count,
                "seed": _config_int(evaluated=evaluated, key="seed"),
                "random_seed": _RANDOM_SEED_LABEL in labels,
                "grid_size": _config_int(evaluated=evaluated, key="grid_size"),
                "postmortem_enabled": bool(config.get("postmortem_enabled", False)),
                "round_success_count": sum(1 for o in outcomes if o.eligible),
                "wins_count": sum(1 for o in outcomes if o.won),
                "round_success_fraction": _fraction(
                    numerator=sum(1 for o in outcomes if o.eligible), denominator=len(outcomes)
                ),
                "wins_fraction": _fraction(
                    numerator=sum(1 for o in outcomes if o.won), denominator=len(outcomes)
                ),
                "mean_found_fraction": _mean_found_fraction(outcomes=outcomes),
                "mean_characters_used": _mean_characters(outcomes=outcomes),
                "budget_exceeded_count": sum(1 for o in outcomes if o.budget_exceeded),
                "did_not_submit_count": sum(1 for o in outcomes if not o.submitted),
                "disagreed_count": sum(1 for o in outcomes if o.submitted and not o.agreed),
                "labels": "|".join(labels),
            }
            for base, column in _TEAM_METRIC_COLUMNS:
                row[column] = _team_metric_score(
                    evaluated=evaluated, base=base, two_teams=context.two_teams, team_id=team_id
                )
            rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        by=["model_class", "viewer_left_model", "viewer_right_model", "run_id", "team_id"]
    ).reset_index(drop=True)


def _mean_found_fraction(outcomes: list[DiffOutcome]) -> float | None:
    """Mean of per-round ``found_count / total_differences`` across a team's rounds."""
    fractions: list[float] = []
    for outcome in outcomes:
        fraction = _fraction(numerator=outcome.found_count, denominator=outcome.total_differences)
        if fraction is not None:
            fractions.append(fraction)
    if not fractions:
        return None
    return sum(fractions) / len(fractions)


def _mean_characters(outcomes: list[DiffOutcome]) -> float | None:
    """Mean link characters a team used per round."""
    if not outcomes:
        return None
    return sum(o.characters_used for o in outcomes) / len(outcomes)


def _build_round_level(joined_runs: list[JoinedRun]) -> pd.DataFrame:
    """One row per (run, round, team): reconstructed outcome + scene facts + per-round metrics."""
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        evaluated = joined.evaluated
        context = joined.context
        grid_size = _config_int(evaluated=evaluated, key="grid_size")
        for team_id in context.team_ids:
            models = context.models_by_team[team_id]
            perplexity_by_round = _team_metric_per_round(
                evaluated=evaluated, base="perplexity", two_teams=context.two_teams, team_id=team_id
            )
            mcr_by_round = _team_metric_per_round(
                evaluated=evaluated,
                base="mean_chars_per_round",
                two_teams=context.two_teams,
                team_id=team_id,
            )
            repetition_by_round = _team_metric_per_round(
                evaluated=evaluated,
                base="language_repetition",
                two_teams=context.two_teams,
                team_id=team_id,
            )
            for round_number in sorted(context.outcomes):
                outcome = context.outcomes[round_number].get(team_id)
                if outcome is None:
                    continue
                case = context.cases.get(round_number)
                result = context.round_result.get(
                    (round_number, _result_team_id(team_id=team_id, two_teams=context.two_teams))
                )
                rows.append(
                    {
                        "run_id": evaluated.run_id,
                        "scenario": evaluated.scenario_name,
                        "team_id": team_id,
                        "viewer_left_model": models.viewer_left_model,
                        "viewer_right_model": models.viewer_right_model,
                        "model_class": _team_model_class(models=models),
                        "round_number": round_number,
                        "case_number": outcome.case_number,
                        "grid_size": grid_size,
                        "object_count": _object_count(case=case),
                        "difference_count": outcome.total_differences,
                        "difference_kinds": _difference_kinds(case=case),
                        "success": int(outcome.eligible),
                        "won": int(outcome.won),
                        "found_count": outcome.found_count,
                        "found_fraction": _fraction(
                            numerator=outcome.found_count, denominator=outcome.total_differences
                        ),
                        "false_positive_count": outcome.false_positive_count,
                        "found_all": int(outcome.found_all),
                        "submitted": int(outcome.submitted),
                        "budget_exceeded": int(outcome.budget_exceeded),
                        "characters_used": outcome.characters_used,
                        "members_submitted": outcome.members_submitted,
                        "members_required": outcome.members_required,
                        "agreed": int(outcome.agreed),
                        "opponent_characters": outcome.opponent_characters,
                        "opponent_found_all": _optional_int(flag=outcome.opponent_found_all),
                        "opponent_eligible": _optional_int(flag=outcome.opponent_eligible),
                        "reason": _reason(result=result),
                        "perplexity": perplexity_by_round.get(round_number),
                        "mcr": mcr_by_round.get(round_number),
                        "language_repetition": repetition_by_round.get(round_number),
                    }
                )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(by=["run_id", "round_number", "team_id"]).reset_index(drop=True)


def _optional_int(flag: bool | None) -> int | None:
    """Render an optional bool as 0/1, preserving ``None``."""
    if flag is None:
        return None
    return int(flag)


def _reason(result: RoundResultRecorded | None) -> str:
    """Return the human-readable round-result reason, or empty when the event is absent."""
    if result is None:
        return ""
    return result.reason


def _object_count(case: SpotTheDifferenceCaseStarted | None) -> int | None:
    """Number of objects in the round's scene A, or ``None`` when the case is absent."""
    if case is None:
        return None
    return len(case.scene_a)


def _difference_kinds(case: SpotTheDifferenceCaseStarted | None) -> str:
    """Pipe-joined planted-difference kinds for the round, or empty when the case is absent."""
    if case is None:
        return ""
    return "|".join(diff.kind for diff in case.differences)


def _build_message_level(joined_runs: list[JoinedRun]) -> pd.DataFrame:
    """One row per link-channel message with per-message language features + round outcome."""
    perplexity_scorer = MessagePerplexityScorer()
    english_ngram_scorer = MessageEnglishNgramScorer()
    rows: list[dict[str, object]] = []
    for joined in joined_runs:
        evaluated = joined.evaluated
        context = joined.context
        jsonl_path = evaluated.run_dir / f"{evaluated.scenario_name}.jsonl"
        events = asyncio.run(load_events(log_path=jsonl_path))
        pristine_by_id = build_pristine_text_index(events=events)
        message_repetition = read_message_repetition_factors(run_dir=evaluated.run_dir)
        run_rows = _message_rows_for_run(
            evaluated=evaluated,
            context=context,
            pristine_by_id=pristine_by_id,
            message_repetition=message_repetition,
        )
        pristine_texts = [str(row["message_text"]) for row in run_rows]
        perplexities = perplexity_scorer.score_run(jsonl_path=jsonl_path, texts=pristine_texts)
        english_ngram_surprisals = english_ngram_scorer.score_run(
            jsonl_path=jsonl_path, texts=pristine_texts
        )
        for row, perplexity, english_ngram in zip(run_rows, perplexities, english_ngram_surprisals):
            row["perplexity"] = perplexity
            row["english_ngram_surprisal"] = english_ngram
        rows.extend(run_rows)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        by=["run_id", "round_number", "team_id", "message_index_in_round"]
    ).reset_index(drop=True)


def _message_rows_for_run(
    evaluated: EvaluatedRun,
    context: SpotRunContext,
    pristine_by_id: dict[str, str],
    message_repetition: dict[str, float],
) -> list[dict[str, object]]:
    """Build the per-message rows for one run (features scored by the caller)."""
    run_rows: list[dict[str, object]] = []
    for team_id in context.team_ids:
        models = context.models_by_team[team_id]
        for round_number in sorted(context.link_messages.get(team_id, {})):
            outcome = context.outcomes.get(round_number, {}).get(team_id)
            messages = context.link_messages[team_id][round_number]
            for message_index, message in enumerate(messages, start=1):
                transmitted = message.transmitted_text
                pristine = pristine_by_id.get(message.message_id, transmitted)
                chars = len(pristine)
                run_rows.append(
                    {
                        "run_id": evaluated.run_id,
                        "scenario": evaluated.scenario_name,
                        "team_id": team_id,
                        "viewer_left_model": models.viewer_left_model,
                        "viewer_right_model": models.viewer_right_model,
                        "model_class": _team_model_class(models=models),
                        "round_number": round_number,
                        "message_index_in_round": message_index,
                        "message_agent": _sender_role(agent_id=message.agent_id),
                        "message_text": pristine,
                        "message_text_transmitted": transmitted,
                        "chars": chars,
                        "message_entropy": _entropy(text=pristine),
                        "gzip_compression_ratio": _gzip(text=pristine),
                        "message_repetition_factor": message_repetition.get(message.message_id),
                        "success": _outcome_flag(outcome=outcome, attr="eligible"),
                        "won": _outcome_flag(outcome=outcome, attr="won"),
                    }
                )
    return run_rows


def _entropy(text: str) -> float | None:
    """Per-message character Shannon entropy in bits/char, or ``None`` for empty text."""
    if not text.strip():
        return None
    return character_entropy_bits(text=text)


def _gzip(text: str) -> float | None:
    """Per-message raw-DEFLATE compression ratio, or ``None`` for empty text."""
    if not text.strip():
        return None
    return gzip_compression_ratio(text=text)


def _sender_role(agent_id: str) -> str:
    """Normalize a viewer agent id to ``viewer_left`` / ``viewer_right`` (else the raw id)."""
    if agent_id in _VIEWER_LEFT_IDS:
        return "viewer_left"
    if agent_id in _VIEWER_RIGHT_IDS:
        return "viewer_right"
    return agent_id


def _outcome_flag(outcome: DiffOutcome | None, attr: str) -> int | None:
    """Render a bool attribute of a round's team outcome as 0/1, ``None`` when absent."""
    if outcome is None:
        return None
    return int(getattr(outcome, attr))


def _build_team_aggregate(run_level: pd.DataFrame) -> pd.DataFrame:
    """Per (models, team config, budget, noise) mean ± std of success / win fractions."""
    if run_level.empty:
        return run_level
    group_keys = [
        "model_class",
        "viewer_left_model",
        "viewer_right_model",
        "all_must_submit",
    ]
    grouped = run_level.groupby(group_keys, as_index=False).agg(
        n=("round_success_fraction", "size"),
        mean_success_fraction=("round_success_fraction", "mean"),
        std_success_fraction=("round_success_fraction", lambda s: s.std(ddof=0)),
        min_success_fraction=("round_success_fraction", "min"),
        max_success_fraction=("round_success_fraction", "max"),
        mean_wins_fraction=("wins_fraction", "mean"),
        mean_characters_used=("mean_characters_used", "mean"),
        mean_perplexity=("perplexity", "mean"),
        mean_language_repetition=("language_repetition", "mean"),
    )
    return grouped.sort_values(by=group_keys).reset_index(drop=True)


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for the exporter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("analysis/spot_the_difference_export/output")
    )
    parser.add_argument("--stem", type=str, default="spot_the_difference")
    parser.add_argument(
        "--canonical-only",
        action="store_true",
        help="Restrict to the canonical design — the fixed seed=42 runs (no random_seed label).",
    )
    return parser.parse_args()


def main() -> None:
    """Build the five frames and write outputs."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    evaluated_runs = list_evaluated_runs(runs_dir=args.runs_dir)
    joined = _collect_runs(evaluated_runs=evaluated_runs, canonical_only=args.canonical_only)
    logger.info(
        "scenario=%s: %d in-scope runs (canonical_only=%s).",
        SCENARIO_NAME,
        len(joined),
        args.canonical_only,
    )

    run_level = _build_run_level(joined_runs=joined)
    round_level = _build_round_level(joined_runs=joined)
    message_level = _build_message_level(joined_runs=joined)
    team_aggregate = _build_team_aggregate(run_level=run_level)
    frames = {
        "run_level": run_level,
        "round_level": round_level,
        "message_level": message_level,
        "team_aggregate": team_aggregate,
    }

    csv_paths = write_csvs(frames=frames, output_dir=args.output_dir, stem=args.stem)
    xlsx_path = write_xlsx(frames=frames, output_dir=args.output_dir, stem=args.stem)

    logger.info(
        "Wrote %d run-team rows, %d round-team rows, %d messages. CSVs: %s%s",
        len(run_level),
        len(round_level),
        len(message_level),
        ", ".join(str(p) for p in csv_paths),
        f"; workbook: {xlsx_path}" if xlsx_path is not None else "",
    )


if __name__ == "__main__":
    main()
