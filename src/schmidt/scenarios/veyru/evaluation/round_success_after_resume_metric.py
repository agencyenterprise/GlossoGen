"""Round-success score restricted to the rounds played after a replace-agent swap.

Mirrors ``RoundSuccessMetric`` but filters the scored round set to
``[round_start, round_start + rounds_after_swap]`` as recorded in the
run's ``replace_manifest.json``. Also re-scores the *source* run over
the same round window (per-run, since the source may have ended early)
and reports both numbers plus the delta in ``summary`` — so a single
measurement tells us whether the replacement out-performed, matched,
or under-performed the agents it replaced.

Two-team runs emit two Measurements (``round_success_after_resume_team_a``
and ``round_success_after_resume_team_b``); single-team runs emit one.
Runs without a replace manifest emit a single zero-score measurement
explaining that the metric does not apply.

Summary format contract — these prefixes are parsed by the Streamlit
resume tab (``analysis/results_viewer/resume_data.py``). Keep the
``Resumed: W/T (P%)`` and ``Source ... over the same window: W/T (P%).``
shapes stable when editing this module:

    Resumed: <won>/<total> (<pct>%) stabilized in post-resume rounds (...)
    Source <source_run_id> over the same window: <won>/<total> (<pct>%).
"""

import logging
from pathlib import Path
from typing import NamedTuple

from schmidt.evaluation.log_reader import extract_agent_configs, load_events
from schmidt.evaluation.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.replace_manifest import ReplaceManifest, read_replace_manifest
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.round_success_core import (
    TEAM_A_AGENT_IDS,
    TEAM_B_AGENT_IDS,
    RoundOutcome,
    collect_advanced_round_numbers,
    compute_team_result,
    filter_events_for_team,
    is_two_team_mode,
)
from schmidt.scenarios.veyru.ids import LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID, TEAM_SOLO_ID

logger = logging.getLogger(__name__)


class _SideScore(NamedTuple):
    """Per-side scoring over a fixed round window for one team or solo run."""

    team_label: str
    won: int
    total: int
    score: float
    round_outcomes: list[RoundOutcome]
    lost_details: list[str]


class RoundSuccessAfterResumeMetric(Metric):
    """Counts post-resume rounds where a Veyru was stabilized before collapse."""

    name = "round_success_after_resume"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> list[Measurement]:
        """Score post-swap rounds and append a source-run comparison."""
        _ = llm_provider
        manifest = read_replace_manifest(run_dir=run_dir)
        if manifest is None:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="fraction of post-resume rounds stabilized",
                    summary=(
                        "Run is not a replace-agent run; round_success_after_resume "
                        "does not apply."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        candidate_rounds = _candidate_rounds(manifest=manifest)
        resumed_scored = sorted(candidate_rounds & collect_advanced_round_numbers(events=events))
        if not resumed_scored:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="fraction of post-resume rounds stabilized",
                    summary=(
                        "Replace-agent run did not advance any post-resume round "
                        f"(round_start={manifest.round_start}, "
                        f"rounds_after_swap={manifest.rounds_after_swap})."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        resumed_sides = _score_window(
            events=events,
            agent_configs=agent_configs,
            scored_rounds=resumed_scored,
        )
        source_sides_by_label = await _score_source_window(
            scenario_name=scenario.name(),
            manifest=manifest,
            candidate_rounds=candidate_rounds,
        )

        return [
            _build_side_measurement(
                metric_base_name=self.name,
                resumed_side=resumed_side,
                source_side=source_sides_by_label.get(resumed_side.team_label),
                manifest=manifest,
                resumed_scored=resumed_scored,
            )
            for resumed_side in resumed_sides
        ]


def _candidate_rounds(manifest: ReplaceManifest) -> set[int]:
    """Inclusive ``[round_start, round_start + rounds_after_swap]`` round set."""
    return set(range(manifest.round_start, manifest.round_start + manifest.rounds_after_swap + 1))


def _score_window(
    events: list[SimulationEvent],
    agent_configs: list[AgentConfig],
    scored_rounds: list[int],
) -> list[_SideScore]:
    """Score ``events`` against the round-success rules over ``scored_rounds``."""
    is_two_team = is_two_team_mode(agent_configs=agent_configs)
    total = len(scored_rounds)
    if is_two_team:
        team_a_events = filter_events_for_team(
            events=events,
            agent_ids=TEAM_A_AGENT_IDS,
            link_channel_id=LINK_A_CHANNEL_ID,
        )
        team_b_events = filter_events_for_team(
            events=events,
            agent_ids=TEAM_B_AGENT_IDS,
            link_channel_id=LINK_B_CHANNEL_ID,
        )
        team_a_result = compute_team_result(
            round_numbers=scored_rounds,
            events=team_a_events,
            label="Team A",
        )
        team_b_result = compute_team_result(
            round_numbers=scored_rounds,
            events=team_b_events,
            label="Team B",
        )
        return [
            _SideScore(
                team_label="team_a",
                won=team_a_result.won,
                total=total,
                score=team_a_result.won / total if total > 0 else 0.0,
                round_outcomes=team_a_result.round_outcomes,
                lost_details=team_a_result.lost_details,
            ),
            _SideScore(
                team_label="team_b",
                won=team_b_result.won,
                total=total,
                score=team_b_result.won / total if total > 0 else 0.0,
                round_outcomes=team_b_result.round_outcomes,
                lost_details=team_b_result.lost_details,
            ),
        ]

    solo_result = compute_team_result(
        round_numbers=scored_rounds,
        events=events,
        label=TEAM_SOLO_ID,
    )
    return [
        _SideScore(
            team_label=TEAM_SOLO_ID,
            won=solo_result.won,
            total=total,
            score=solo_result.won / total if total > 0 else 0.0,
            round_outcomes=solo_result.round_outcomes,
            lost_details=solo_result.lost_details,
        )
    ]


async def _score_source_window(
    scenario_name: str,
    manifest: ReplaceManifest,
    candidate_rounds: set[int],
) -> dict[str, _SideScore]:
    """Score the source run's events over the same window. Empty when unavailable."""
    source_dir = _resolve_source_run_dir(manifest=manifest)
    if source_dir is None:
        return {}
    source_log = source_dir / f"{scenario_name}.jsonl"
    if not source_log.exists():
        return {}

    source_events = await load_events(log_path=source_log)
    source_agent_configs = extract_agent_configs(events=source_events)
    source_scored = sorted(candidate_rounds & collect_advanced_round_numbers(events=source_events))
    if not source_scored:
        return {}

    source_sides = _score_window(
        events=source_events,
        agent_configs=source_agent_configs,
        scored_rounds=source_scored,
    )
    return {side.team_label: side for side in source_sides}


def _build_side_measurement(
    metric_base_name: str,
    resumed_side: _SideScore,
    source_side: _SideScore | None,
    manifest: ReplaceManifest,
    resumed_scored: list[int],
) -> Measurement:
    """Compose a Measurement for one team (or solo) covering both resumed and source."""
    if resumed_side.team_label == TEAM_SOLO_ID:
        metric_name = metric_base_name
    else:
        metric_name = f"{metric_base_name}_{resumed_side.team_label}"

    pct = round(resumed_side.score * 100)
    headline = (
        f"Resumed: {resumed_side.won}/{resumed_side.total} ({pct}%) stabilized "
        f"in post-resume rounds (round_start={manifest.round_start}, "
        f"rounds_after_swap={manifest.rounds_after_swap})."
    )
    summary_parts = [headline]
    if source_side is not None:
        source_pct = round(source_side.score * 100)
        delta_pp = round((resumed_side.score - source_side.score) * 100)
        if delta_pp > 0:
            delta_label = f"+{delta_pp} pp (resumed better)"
        elif delta_pp < 0:
            delta_label = f"{delta_pp} pp (resumed worse)"
        else:
            delta_label = "0 pp (same)"
        summary_parts.append(
            f"Source {manifest.source_run_id} over the same window: "
            f"{source_side.won}/{source_side.total} ({source_pct}%)."
        )
        summary_parts.append(f"Δ vs source: {delta_label}.")
    else:
        summary_parts.append(f"Source run {manifest.source_run_id} not available for comparison.")
    summary_parts.append(f"Scored rounds (resumed): {resumed_scored}.")
    summary_parts.extend(resumed_side.lost_details)
    summary = " ".join(summary_parts)

    per_round = [
        RoundObservation(
            round_number=outcome.round_number,
            value=1.0 if outcome.won else 0.0,
            note=outcome.note,
        )
        for outcome in resumed_side.round_outcomes
    ]
    return Measurement(
        metric_name=metric_name,
        score=resumed_side.score,
        score_unit=(
            f"fraction of post-resume rounds {resumed_side.team_label} "
            f"stabilized ({resumed_side.won}/{resumed_side.total})"
        ),
        summary=summary,
        per_round=per_round,
        per_agent=[],
    )


def _resolve_source_run_dir(manifest: ReplaceManifest) -> Path | None:
    """Return the source run directory, trying the stored path then cwd-relative."""
    raw_path = Path(manifest.source_run_dir)
    if raw_path.is_dir():
        return raw_path
    cwd_relative = Path.cwd() / manifest.source_run_dir
    if cwd_relative.is_dir():
        return cwd_relative
    return None
