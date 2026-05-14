"""Round-success score restricted to the rounds played after a swap.

Generic platform metric that reads ``RoundResultRecorded`` events
emitted by every scenario's ``judge_round_result`` hook. Supports three
flows uniformly:

* same-run replace-agent (``replace_manifest.json``);
* cross-run replace-agent (``cross_run_replace_manifest.json``);
* in-run scheduled swaps (``AgentSwappedMidRun`` events in the JSONL).

For manifest flows the baseline is the matching round window in the
source run; for in-run scheduled flows the baseline is the same run's
earlier rounds (between the previous swap, or the start of the run,
and this swap). Multi-team scenarios emit one ``Measurement`` per team
per anchor (e.g. ``..._team_a`` / ``..._team_b``); single-team
scenarios emit one. In-run scheduled flows additionally suffix the
metric name with ``_round_<R>_<agent_id>`` so multiple anchors in
one run produce distinct measurement names.

Summary format contract — the ``Resumed: W/T (P%)`` and
``Source ... over the same window: W/T (P%).`` prefixes are parsed by
the Streamlit resume tab; keep them stable when editing this module.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from schmidt.evaluation.log_reader import load_events
from schmidt.evaluation.metric_core.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.metric_core.resume_anchors import (
    ResumeAnchor,
    anchor_metric_name,
    candidate_rounds,
    collect_advanced_round_numbers,
    read_resume_anchors,
    resolve_external_source_dir,
)
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import RoundResultRecorded, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class _RoundOutcome(NamedTuple):
    """One round's success verdict + human-readable reason."""

    round_number: int
    success: bool
    reason: str


class _SideScore(NamedTuple):
    """Aggregate win/loss accounting for one team over a window."""

    team_id: str | None
    won: int
    total: int
    round_outcomes: list[_RoundOutcome]


class RoundSuccessAfterResumeMetric(Metric):
    """Scenario-agnostic post-swap round-success metric."""

    name = "round_success_after_resume"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Emit one Measurement per team per swap anchor."""
        _ = agent_configs, llm_provider, options
        anchors = read_resume_anchors(events=events, run_dir=run_dir)
        if not anchors:
            logger.info(
                "%s: skipping — run has no replace-agent manifest and no "
                "AgentSwappedMidRun events",
                self.name,
            )
            return []
        results_by_round = _index_results_by_round(events=events)
        if not results_by_round:
            logger.info(
                "%s: skipping — run has no RoundResultRecorded events "
                "(scenario must implement judge_round_result)",
                self.name,
            )
            return []

        measurements: list[Measurement] = []
        for anchor in anchors:
            measurements.extend(
                await self._compute_for_anchor(
                    anchor=anchor,
                    events=events,
                    results_by_round=results_by_round,
                    scenario_name=scenario.name(),
                )
            )
        return measurements

    async def _compute_for_anchor(
        self,
        anchor: ResumeAnchor,
        events: list[SimulationEvent],
        results_by_round: dict[int, list[RoundResultRecorded]],
        scenario_name: str,
    ) -> list[Measurement]:
        """Score one anchor and emit one Measurement per team."""
        anchor_candidates = candidate_rounds(anchor=anchor)
        resumed_scored = sorted(anchor_candidates & set(results_by_round.keys()))
        if not resumed_scored:
            return [
                Measurement(
                    metric_name=anchor_metric_name(base_name=self.name, anchor=anchor),
                    score=0.0,
                    score_unit="fraction of post-resume rounds won",
                    summary=(
                        f"{anchor.flow_label} did not advance any post-swap round "
                        f"(round_start={anchor.round_start}, "
                        f"rounds_after_swap={anchor.rounds_after_swap})."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]
        resumed_sides = _score_window(
            results_by_round=results_by_round, round_numbers=resumed_scored
        )
        baseline_sides_by_team = await self._score_baseline_window(
            scenario_name=scenario_name,
            anchor=anchor,
            events=events,
            anchor_candidates=anchor_candidates,
            results_by_round=results_by_round,
        )
        return [
            _build_side_measurement(
                metric_base_name=self.name,
                resumed_side=resumed_side,
                source_side=baseline_sides_by_team.get(resumed_side.team_id),
                anchor=anchor,
                resumed_scored=resumed_scored,
            )
            for resumed_side in resumed_sides
        ]

    async def _score_baseline_window(
        self,
        scenario_name: str,
        anchor: ResumeAnchor,
        events: list[SimulationEvent],
        anchor_candidates: set[int],
        results_by_round: dict[int, list[RoundResultRecorded]],
    ) -> dict[str | None, _SideScore]:
        """Score whichever baseline applies (external source or in-run pre-window)."""
        _ = events
        if anchor.in_run_baseline_window is not None:
            baseline_start, baseline_end = anchor.in_run_baseline_window
            baseline_rounds = set(range(baseline_start, baseline_end + 1))
            baseline_scored = sorted(baseline_rounds & set(results_by_round.keys()))
            if not baseline_scored:
                return {}
            baseline_sides = _score_window(
                results_by_round=results_by_round, round_numbers=baseline_scored
            )
            return {side.team_id: side for side in baseline_sides}

        if anchor.external_source_run_dir is None:
            return {}
        source_dir = resolve_external_source_dir(source_run_dir=anchor.external_source_run_dir)
        if source_dir is None:
            return {}
        source_log = source_dir / f"{scenario_name}.jsonl"
        if not source_log.exists():
            return {}
        source_events = await load_events(log_path=source_log)
        source_results_by_round = _index_results_by_round(events=source_events)
        source_scored = sorted(
            anchor_candidates
            & collect_advanced_round_numbers(events=source_events)
            & set(source_results_by_round.keys())
        )
        if not source_scored:
            return {}
        source_sides = _score_window(
            results_by_round=source_results_by_round, round_numbers=source_scored
        )
        return {side.team_id: side for side in source_sides}


def _index_results_by_round(
    events: list[SimulationEvent],
) -> dict[int, list[RoundResultRecorded]]:
    """Group ``RoundResultRecorded`` events by their round number."""
    by_round: dict[int, list[RoundResultRecorded]] = {}
    for event in events:
        if isinstance(event, RoundResultRecorded):
            by_round.setdefault(event.round_number, []).append(event)
    return by_round


def _score_window(
    results_by_round: dict[int, list[RoundResultRecorded]],
    round_numbers: list[int],
) -> list[_SideScore]:
    """Aggregate per-team win/loss counts across the round window."""
    per_team_outcomes: dict[str | None, list[_RoundOutcome]] = {}
    for round_number in round_numbers:
        for result in results_by_round.get(round_number, []):
            per_team_outcomes.setdefault(result.team_id, []).append(
                _RoundOutcome(
                    round_number=result.round_number,
                    success=result.success,
                    reason=result.reason,
                )
            )
    sides: list[_SideScore] = []
    for team_id, outcomes in sorted(
        per_team_outcomes.items(), key=lambda item: (item[0] is not None, item[0])
    ):
        outcomes_sorted = sorted(outcomes, key=lambda o: o.round_number)
        won = sum(1 for o in outcomes_sorted if o.success)
        sides.append(
            _SideScore(
                team_id=team_id,
                won=won,
                total=len(outcomes_sorted),
                round_outcomes=outcomes_sorted,
            )
        )
    return sides


def _build_side_measurement(
    metric_base_name: str,
    resumed_side: _SideScore,
    source_side: _SideScore | None,
    anchor: ResumeAnchor,
    resumed_scored: list[int],
) -> Measurement:
    """Compose a Measurement for one team covering both resumed and baseline."""
    base_name = anchor_metric_name(base_name=metric_base_name, anchor=anchor)
    if resumed_side.team_id is None:
        metric_name = base_name
    else:
        metric_name = f"{base_name}_{resumed_side.team_id}"

    score = resumed_side.won / resumed_side.total if resumed_side.total > 0 else 0.0
    pct = round(score * 100)
    headline = (
        f"Resumed: {resumed_side.won}/{resumed_side.total} ({pct}%) won "
        f"in post-resume rounds (round_start={anchor.round_start}, "
        f"rounds_after_swap={anchor.rounds_after_swap})."
    )
    summary_parts = [headline]
    baseline_descriptor = _baseline_descriptor(anchor=anchor)
    if source_side is not None:
        source_score = source_side.won / source_side.total if source_side.total > 0 else 0.0
        source_pct = round(source_score * 100)
        delta_pp = round((score - source_score) * 100)
        if delta_pp > 0:
            delta_label = f"+{delta_pp} pp (resumed better)"
        elif delta_pp < 0:
            delta_label = f"{delta_pp} pp (resumed worse)"
        else:
            delta_label = "0 pp (same)"
        summary_parts.append(
            f"Source {baseline_descriptor} over the same window: "
            f"{source_side.won}/{source_side.total} ({source_pct}%)."
        )
        summary_parts.append(f"Δ vs source: {delta_label}.")
    else:
        summary_parts.append(f"Source {baseline_descriptor} not available for comparison.")
    summary_parts.append(f"Scored rounds (resumed): {resumed_scored}.")
    lost_details = [
        f"R{outcome.round_number}: {outcome.reason}"
        for outcome in resumed_side.round_outcomes
        if not outcome.success
    ]
    summary_parts.extend(lost_details)
    summary = " ".join(summary_parts)

    per_round = [
        RoundObservation(
            round_number=outcome.round_number,
            value=1.0 if outcome.success else 0.0,
            note=outcome.reason,
        )
        for outcome in resumed_side.round_outcomes
    ]
    team_label = "solo" if resumed_side.team_id is None else resumed_side.team_id
    return Measurement(
        metric_name=metric_name,
        score=score,
        score_unit=(
            f"fraction of post-resume rounds {team_label} won "
            f"({resumed_side.won}/{resumed_side.total})"
        ),
        summary=summary,
        per_round=per_round,
        per_agent=[],
    )


def _baseline_descriptor(anchor: ResumeAnchor) -> str:
    """Human-readable label for the comparison baseline used in summary text."""
    if anchor.in_run_baseline_window is not None:
        baseline_start, baseline_end = anchor.in_run_baseline_window
        return f"(rounds {baseline_start}-{baseline_end} of same run)"
    if anchor.external_source_run_id is not None:
        return anchor.external_source_run_id
    return "unknown"
