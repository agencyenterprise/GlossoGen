"""Round-success score restricted to the rounds played after a replace-agent swap.

Mirrors ``RoundSuccessEvaluator`` but filters the scored round set to
``[round_start, round_start + rounds_after_swap]`` as recorded in the
run's ``replace_manifest.json``. Also re-scores the *source* run over
the same round window (per-run, since the source may have ended early)
and reports both numbers plus the delta in evidence — so a single
metric tells us whether the replacement out-performed, matched, or
under-performed the agents it replaced. Runs without a manifest are
not applicable: the evaluator emits a ``FAIL`` verdict with an
explanatory evidence string (matching the convention used by
``ProtocolLearnedAfterSwapEvaluator``).
"""

import logging
from pathlib import Path
from typing import NamedTuple

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.log_reader import extract_agent_configs, load_events
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.replace_manifest import ReplaceManifest, read_replace_manifest
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.round_success_core import (
    TEAM_A_AGENT_IDS,
    TEAM_B_AGENT_IDS,
    collect_advanced_round_numbers,
    compute_team_result,
    filter_events_for_team,
    is_two_team_mode,
    score_to_verdict,
)
from schmidt.scenarios.veyru.ids import LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID, TEAM_SOLO_ID

logger = logging.getLogger(__name__)


class _WindowScore(NamedTuple):
    """Per-side scoring over a fixed round window."""

    won: int
    total: int
    score: float
    won_rounds: list[int]
    lost_details: list[str]
    is_two_team: bool
    team_summaries: list[str]


class RoundSuccessAfterResumeEvaluator(Evaluator):
    """Counts post-resume rounds where a Veyru was stabilized before collapse.

    Same accounting as ``RoundSuccessEvaluator``, restricted to the rounds
    that actually played after the replace-agent swap. The source run is
    re-scored over the same round window for direct comparison.
    """

    name = "round_success_after_resume"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Score post-swap rounds and append a source-run comparison."""
        _ = llm_provider
        manifest = read_replace_manifest(run_dir=run_dir)
        if manifest is None:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    "Run is not a replace-agent run; round_success_after_resume does not apply."
                ],
                per_agent={},
                rounds_identified=[],
            )

        candidate_rounds = _candidate_rounds(manifest=manifest)
        resumed_scored = sorted(candidate_rounds & collect_advanced_round_numbers(events=events))
        if not resumed_scored:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    "Replace-agent run did not advance any post-resume round "
                    f"(round_start={manifest.round_start}, "
                    f"rounds_after_swap={manifest.rounds_after_swap})."
                ],
                per_agent={},
                rounds_identified=[],
            )

        resumed_window = _score_window(
            events=events,
            agent_configs=agent_configs,
            scored_rounds=resumed_scored,
        )

        source_evidence = await _build_source_evidence(
            scenario_name=scenario.name(),
            manifest=manifest,
            candidate_rounds=candidate_rounds,
            resumed_window=resumed_window,
        )

        evidence = _build_resumed_evidence(
            manifest=manifest,
            scored_rounds=resumed_scored,
            window=resumed_window,
        )
        evidence.extend(source_evidence)

        return MetricResult(
            evaluator_name=self.name,
            verdict=score_to_verdict(score=resumed_window.score),
            score=resumed_window.score,
            evidence=evidence,
            per_agent={},
            rounds_identified=resumed_window.won_rounds,
        )


def _candidate_rounds(manifest: ReplaceManifest) -> set[int]:
    """Inclusive ``[round_start, round_start + rounds_after_swap]`` round set."""
    return set(range(manifest.round_start, manifest.round_start + manifest.rounds_after_swap + 1))


def _score_window(
    events: list[SimulationEvent],
    agent_configs: list[AgentConfig],
    scored_rounds: list[int],
) -> _WindowScore:
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
        joint_won_rounds = sorted(set(team_a_result.won_rounds) & set(team_b_result.won_rounds))
        won = len(joint_won_rounds)
        score = won / total
        team_summaries = [
            f"Team A: {team_a_result.won}/{total} stabilized.",
            f"Team B: {team_b_result.won}/{total} stabilized.",
        ]
        lost_details: list[str] = []
        if team_a_result.lost_details:
            lost_details.append("Team A losses: " + "; ".join(team_a_result.lost_details[:10]))
        if team_b_result.lost_details:
            lost_details.append("Team B losses: " + "; ".join(team_b_result.lost_details[:10]))
        return _WindowScore(
            won=won,
            total=total,
            score=score,
            won_rounds=joint_won_rounds,
            lost_details=lost_details,
            is_two_team=True,
            team_summaries=team_summaries,
        )

    solo_result = compute_team_result(
        round_numbers=scored_rounds,
        events=events,
        label=TEAM_SOLO_ID,
    )
    score = solo_result.won / total
    lost_details = []
    if solo_result.lost_details:
        lost_details.append("Lost rounds: " + "; ".join(solo_result.lost_details[:10]))
    return _WindowScore(
        won=solo_result.won,
        total=total,
        score=score,
        won_rounds=solo_result.won_rounds,
        lost_details=lost_details,
        is_two_team=False,
        team_summaries=[],
    )


def _build_resumed_evidence(
    manifest: ReplaceManifest,
    scored_rounds: list[int],
    window: _WindowScore,
) -> list[str]:
    """Compose the resumed-side evidence lines."""
    pct = round(window.score * 100)
    headline = (
        f"Resumed: {window.won}/{window.total} ({pct}%) stabilized in post-resume rounds "
        f"(round_start={manifest.round_start}, rounds_after_swap={manifest.rounds_after_swap})."
    )
    if window.is_two_team:
        headline = (
            f"Resumed: {window.won}/{window.total} ({pct}%) post-resume rounds stabilized by BOTH "
            f"teams (round_start={manifest.round_start}, "
            f"rounds_after_swap={manifest.rounds_after_swap})."
        )
    evidence: list[str] = [headline]
    evidence.extend(window.team_summaries)
    evidence.append(f"Scored rounds (resumed): {scored_rounds}.")
    evidence.extend(window.lost_details)
    return evidence


async def _build_source_evidence(
    scenario_name: str,
    manifest: ReplaceManifest,
    candidate_rounds: set[int],
    resumed_window: _WindowScore,
) -> list[str]:
    """Score the source run over the same window and return comparison lines.

    Returns an evidence note (without raising) when the source directory or
    JSONL is missing.
    """
    source_dir = _resolve_source_run_dir(manifest=manifest)
    if source_dir is None:
        return [
            f"Source run not available for comparison "
            f"(path: {manifest.source_run_dir!r}); skipping comparison."
        ]
    source_log = source_dir / f"{scenario_name}.jsonl"
    if not source_log.exists():
        return [f"Source JSONL not found at {source_log}; skipping comparison."]

    source_events = await load_events(log_path=source_log)
    source_agent_configs = extract_agent_configs(events=source_events)
    source_scored = sorted(candidate_rounds & collect_advanced_round_numbers(events=source_events))
    if not source_scored:
        return [
            f"Source run {manifest.source_run_id} did not advance any rounds in the "
            "candidate window; no comparison possible."
        ]

    source_window = _score_window(
        events=source_events,
        agent_configs=source_agent_configs,
        scored_rounds=source_scored,
    )

    source_pct = round(source_window.score * 100)
    delta_pp = round((resumed_window.score - source_window.score) * 100)
    if delta_pp > 0:
        delta_label = f"+{delta_pp} pp (resumed better)"
    elif delta_pp < 0:
        delta_label = f"{delta_pp} pp (resumed worse)"
    else:
        delta_label = "0 pp (same)"

    evidence: list[str] = [
        f"Source {manifest.source_run_id} over the same window: "
        f"{source_window.won}/{source_window.total} ({source_pct}%).",
        f"Δ vs source: {delta_label}.",
    ]
    if source_window.team_summaries:
        evidence.append("Source team breakdown: " + " ".join(source_window.team_summaries))
    evidence.append(f"Scored rounds (source): {source_scored}.")
    evidence.extend(f"Source {line}" for line in source_window.lost_details)
    return evidence


def _resolve_source_run_dir(manifest: ReplaceManifest) -> Path | None:
    """Return the source run directory, trying the stored path then cwd-relative."""
    raw_path = Path(manifest.source_run_dir)
    if raw_path.is_dir():
        return raw_path
    cwd_relative = Path.cwd() / manifest.source_run_dir
    if cwd_relative.is_dir():
        return cwd_relative
    return None
