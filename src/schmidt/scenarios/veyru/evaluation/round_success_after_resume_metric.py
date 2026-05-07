"""Round-success score restricted to the rounds played after an agent swap.

Supports three flows: same-run replace-agent (``replace_manifest.json``),
cross-run replace-agent (``cross_run_replace_manifest.json``), and
in-run scheduled swaps (``AgentSwappedMidRun`` events in the JSONL).
For each flow the metric scores the post-swap rounds and compares
against a baseline:

* manifest flows compare against the source run's events over the
  same round window (one anchor per run);
* in-run scheduled flows compare against the same run's earlier
  rounds — specifically the window between the previous swap (or
  the start of the run) and this swap (one anchor per swap).

Two-team runs emit two Measurements per anchor
(``..._team_a`` / ``..._team_b``); single-team runs emit one.
In-run scheduled swaps additionally suffix the round number and
swapped agent_id (e.g. ``round_success_after_resume_round_16_field_observer``)
to disambiguate when a single run has multiple anchors.

Summary format contract — the ``Resumed: W/T (P%)`` and
``Source ... over the same window: W/T (P%).`` prefixes are parsed by
the Streamlit resume tab (``analysis/results_viewer/resume_data.py``);
keep them stable when editing this module.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from schmidt.cross_run_replace_manifest import read_cross_run_replace_manifest
from schmidt.evaluation.log_reader import extract_agent_configs, load_events
from schmidt.evaluation.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentSwappedMidRun, SimulationEvent
from schmidt.replace_manifest import read_replace_manifest
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


class _ResumeAnchor(NamedTuple):
    """Common fields needed to score one swap window and its baseline.

    ``round_start`` and ``rounds_after_swap`` define the post-swap
    window (rounds ``[round_start, round_start + rounds_after_swap]``).
    For manifest-based flows the baseline lives in a different run
    (``external_source_run_id`` / ``external_source_run_dir``); for
    in-run scheduled flows the baseline window is in the same run
    (``in_run_baseline_window``). Exactly one of those two baseline
    fields is populated per anchor.

    ``flow_label`` is used in ``summary`` text. ``replaced_agent_id``
    is set for in-run scheduled flows to disambiguate per-swap
    Measurement names.
    """

    round_start: int
    rounds_after_swap: int
    flow_label: str
    external_source_run_id: str | None
    external_source_run_dir: str | None
    in_run_baseline_window: tuple[int, int] | None
    replaced_agent_id: str | None


def _read_resume_anchors(events: list[SimulationEvent], run_dir: Path) -> list[_ResumeAnchor]:
    """Return one anchor per swap event, falling back to manifest if no events fired.

    In-run scheduled flows can produce multiple ``AgentSwappedMidRun``
    events; manifest flows always yield exactly one anchor. The
    returned list preserves declaration order (which equals dispatch
    order, which equals ascending round_number).
    """
    in_run_anchors = _collect_in_run_anchors(events=events)
    if in_run_anchors:
        return in_run_anchors
    replace = read_replace_manifest(run_dir=run_dir)
    if replace is not None:
        return [
            _ResumeAnchor(
                round_start=replace.round_start,
                rounds_after_swap=replace.rounds_after_swap,
                flow_label="replace-agent",
                external_source_run_id=replace.source_run_id,
                external_source_run_dir=replace.source_run_dir,
                in_run_baseline_window=None,
                replaced_agent_id=None,
            )
        ]
    cross_run = read_cross_run_replace_manifest(run_dir=run_dir)
    if cross_run is not None:
        return [
            _ResumeAnchor(
                round_start=cross_run.round_start,
                rounds_after_swap=cross_run.rounds_after_swap,
                flow_label="cross-run replace-agent",
                external_source_run_id=cross_run.source_a_run_id,
                external_source_run_dir=cross_run.source_a_run_dir,
                in_run_baseline_window=None,
                replaced_agent_id=None,
            )
        ]
    return []


def _collect_in_run_anchors(events: list[SimulationEvent]) -> list[_ResumeAnchor]:
    """Build one anchor per ``AgentSwappedMidRun`` event in the log.

    Each anchor's post-window runs from its swap round to one round
    before the next swap (or to the last advanced round of the run).
    Each anchor's in-run baseline window is the slice between the
    previous swap (or round 1) and the current swap.
    """
    swaps = [event for event in events if isinstance(event, AgentSwappedMidRun)]
    if not swaps:
        return []
    advanced_rounds = collect_advanced_round_numbers(events=events)
    if not advanced_rounds:
        return []
    last_round = max(advanced_rounds)

    anchors: list[_ResumeAnchor] = []
    swap_rounds_sorted = sorted(swap.round_number for swap in swaps)
    for index, swap in enumerate(swaps):
        next_swap_round_index = swap_rounds_sorted.index(swap.round_number) + 1
        if next_swap_round_index < len(swap_rounds_sorted):
            next_swap_round = swap_rounds_sorted[next_swap_round_index]
            window_end = next_swap_round - 1
        else:
            window_end = last_round
        rounds_after_swap = max(0, window_end - swap.round_number)

        if index == 0:
            baseline_start = 1
        else:
            baseline_start = swaps[index - 1].round_number
        baseline_end = swap.round_number - 1
        baseline_window: tuple[int, int] | None
        if baseline_end >= baseline_start:
            baseline_window = (baseline_start, baseline_end)
        else:
            baseline_window = None

        anchors.append(
            _ResumeAnchor(
                round_start=swap.round_number,
                rounds_after_swap=rounds_after_swap,
                flow_label="in-run scheduled swap",
                external_source_run_id=None,
                external_source_run_dir=None,
                in_run_baseline_window=baseline_window,
                replaced_agent_id=swap.agent_id,
            )
        )
    return anchors


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
        """Score one Measurement per swap anchor (manifest or in-run scheduled)."""
        _ = llm_provider
        anchors = _read_resume_anchors(events=events, run_dir=run_dir)
        if not anchors:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="fraction of post-resume rounds stabilized",
                    summary=(
                        "Run has no replace-agent manifest and no AgentSwappedMidRun "
                        "events; round_success_after_resume does not apply."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        measurements: list[Measurement] = []
        for anchor in anchors:
            measurements.extend(
                await self._compute_for_anchor(
                    anchor=anchor,
                    events=events,
                    agent_configs=agent_configs,
                    scenario=scenario,
                )
            )
        return measurements

    async def _compute_for_anchor(
        self,
        anchor: _ResumeAnchor,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
    ) -> list[Measurement]:
        """Score a single anchor and emit one Measurement per team."""
        candidate_rounds = _candidate_rounds(anchor=anchor)
        resumed_scored = sorted(candidate_rounds & collect_advanced_round_numbers(events=events))
        if not resumed_scored:
            return [
                Measurement(
                    metric_name=_anchor_metric_name(base_name=self.name, anchor=anchor),
                    score=0.0,
                    score_unit="fraction of post-resume rounds stabilized",
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
            events=events,
            agent_configs=agent_configs,
            scored_rounds=resumed_scored,
        )
        baseline_sides_by_label = await _score_baseline_window(
            scenario_name=scenario.name(),
            anchor=anchor,
            events=events,
            agent_configs=agent_configs,
            candidate_rounds=candidate_rounds,
        )
        return [
            _build_side_measurement(
                metric_base_name=self.name,
                resumed_side=resumed_side,
                source_side=baseline_sides_by_label.get(resumed_side.team_label),
                anchor=anchor,
                resumed_scored=resumed_scored,
            )
            for resumed_side in resumed_sides
        ]


def _anchor_metric_name(base_name: str, anchor: _ResumeAnchor) -> str:
    """Build a metric name with a per-anchor suffix for in-run scheduled swaps.

    Manifest-based anchors keep ``base_name`` unchanged so existing
    measurement consumers continue to work. In-run scheduled anchors
    add ``_round_<R>_<agent_id>`` so multiple anchors in the same run
    do not collide on Measurement name.
    """
    if anchor.replaced_agent_id is None:
        return base_name
    return f"{base_name}_round_{anchor.round_start}_{anchor.replaced_agent_id}"


def _candidate_rounds(anchor: _ResumeAnchor) -> set[int]:
    """Inclusive ``[round_start, round_start + rounds_after_swap]`` round set."""
    return set(range(anchor.round_start, anchor.round_start + anchor.rounds_after_swap + 1))


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


async def _score_baseline_window(
    scenario_name: str,
    anchor: _ResumeAnchor,
    events: list[SimulationEvent],
    agent_configs: list[AgentConfig],
    candidate_rounds: set[int],
) -> dict[str, _SideScore]:
    """Score whichever baseline applies to this anchor (external source or in-run pre-window).

    Returns an empty dict when the baseline is unavailable (missing
    source-run directory for manifest flows, or empty pre-window for
    the first in-run swap).
    """
    if anchor.in_run_baseline_window is not None:
        baseline_start, baseline_end = anchor.in_run_baseline_window
        baseline_rounds = set(range(baseline_start, baseline_end + 1))
        baseline_scored = sorted(baseline_rounds & collect_advanced_round_numbers(events=events))
        if not baseline_scored:
            return {}
        baseline_sides = _score_window(
            events=events,
            agent_configs=agent_configs,
            scored_rounds=baseline_scored,
        )
        return {side.team_label: side for side in baseline_sides}

    if anchor.external_source_run_dir is None:
        return {}
    source_dir = _resolve_external_source_dir(source_run_dir=anchor.external_source_run_dir)
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
    anchor: _ResumeAnchor,
    resumed_scored: list[int],
) -> Measurement:
    """Compose a Measurement for one team (or solo) covering both resumed and baseline."""
    base_name = _anchor_metric_name(base_name=metric_base_name, anchor=anchor)
    if resumed_side.team_label == TEAM_SOLO_ID:
        metric_name = base_name
    else:
        metric_name = f"{base_name}_{resumed_side.team_label}"

    pct = round(resumed_side.score * 100)
    headline = (
        f"Resumed: {resumed_side.won}/{resumed_side.total} ({pct}%) stabilized "
        f"in post-resume rounds (round_start={anchor.round_start}, "
        f"rounds_after_swap={anchor.rounds_after_swap})."
    )
    summary_parts = [headline]
    baseline_descriptor = _baseline_descriptor(anchor=anchor)
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
            f"Source {baseline_descriptor} over the same window: "
            f"{source_side.won}/{source_side.total} ({source_pct}%)."
        )
        summary_parts.append(f"Δ vs source: {delta_label}.")
    else:
        summary_parts.append(f"Source {baseline_descriptor} not available for comparison.")
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


def _baseline_descriptor(anchor: _ResumeAnchor) -> str:
    """Human-readable label for the comparison baseline used in summary text."""
    if anchor.in_run_baseline_window is not None:
        baseline_start, baseline_end = anchor.in_run_baseline_window
        return f"(rounds {baseline_start}-{baseline_end} of same run)"
    if anchor.external_source_run_id is not None:
        return anchor.external_source_run_id
    return "unknown"


def _resolve_external_source_dir(source_run_dir: str) -> Path | None:
    """Return the source run directory, trying the stored path then cwd-relative."""
    raw_path = Path(source_run_dir)
    if raw_path.is_dir():
        return raw_path
    cwd_relative = Path.cwd() / source_run_dir
    if cwd_relative.is_dir():
        return cwd_relative
    return None
