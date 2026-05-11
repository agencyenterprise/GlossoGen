"""Load cross-run replace-agent runs with per-round swapped/source outcomes.

Each ``CrossSwapRun`` carries per-round success booleans for the swapped run
itself and for both source A (the timeline that was modified) and source B
(the run the imported agent came from). The tab uses these to plot one line
per ``imported_model`` bucket plus matched lines for source A and source B
over the same round window.

Round outcomes are computed by replaying the JSONL events through the same
helpers used by the round-success evaluators. Source outcomes are cached by
source run directory because multiple cross-runs typically share sources.

This module is streamlit-free so ad-hoc analysis scripts can reuse it.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

import orjson

from analysis.results_viewer.run_catalog import EvaluatedRun
from schmidt.evaluation.log_reader import extract_agent_configs, load_events
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenarios.veyru.evaluation.metrics.round_success.scoring import (
    TEAM_A_AGENT_IDS,
    TEAM_B_AGENT_IDS,
    collect_advanced_round_numbers,
    compute_team_result,
    filter_events_for_team,
    is_two_team_mode,
)
from schmidt.scenarios.veyru.ids import LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID

logger = logging.getLogger(__name__)


_CROSS_RUN_MANIFEST_FILENAME = "cross_run_replace_manifest.json"
_CROSS_TEAM_LABEL = "cross_team"


class _ManifestSummary(NamedTuple):
    """Subset of ``cross_run_replace_manifest.json`` the cross-swap tab needs.

    Read directly from JSON rather than via ``schmidt.cross_run_replace_manifest``
    so the tab keeps working when the source schema renames or adds fields the
    tab does not consume.
    """

    round_start: int
    rounds_after_swap: int
    source_b_round_end: int
    imported_model: str
    replaced_agent_id: str
    source_a_run_id: str
    source_a_run_dir: str
    source_b_run_id: str
    source_b_run_dir: str


class CrossSwapRun(NamedTuple):
    """A single cross-run replace-agent run with per-round outcomes for itself + A + B.

    ``swapped_round_outcomes`` covers only post-swap rounds (round number
    ``>= round_start``); rounds 1..round_start-1 are inherited from source A's
    git history at clone time and would conflate source-A data with the
    swapped run. ``source_a_round_outcomes`` and ``source_b_round_outcomes``
    carry every advanced round from each source so callers can match a window
    themselves.
    """

    run_id: str
    run_dir: Path
    scenario_name: str
    round_start: int
    rounds_after_swap: int
    source_b_round_end: int
    imported_model: str
    source_a_run_id: str
    source_b_run_id: str
    source_a_replaced_agent_model: str
    source_b_replaced_agent_model: str
    swapped_round_outcomes: dict[int, bool]
    source_a_round_outcomes: dict[int, bool]
    source_b_round_outcomes: dict[int, bool]
    labels: list[str]

    def swapped_series_key(self) -> str:
        """Plot-bucket identifier (imported model + round_start) for filter rows."""
        return f"{self.imported_model} · R{self.round_start}"


def _read_manifest_summary(run_dir: Path) -> _ManifestSummary | None:
    """Read the cross-run manifest fields the tab uses, or ``None`` if absent or malformed."""
    manifest_path = run_dir / _CROSS_RUN_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    round_start = raw.get("round_start")
    rounds_after_swap = raw.get("rounds_after_swap")
    source_b_round_end = raw.get("source_b_round_end")
    imported_model = raw.get("imported_model")
    replaced_agent_id = raw.get("replaced_agent_id")
    source_a_run_id = raw.get("source_a_run_id")
    source_a_run_dir = raw.get("source_a_run_dir")
    source_b_run_id = raw.get("source_b_run_id")
    source_b_run_dir = raw.get("source_b_run_dir")
    if not isinstance(round_start, int):
        return None
    if not isinstance(rounds_after_swap, int):
        return None
    if not isinstance(source_b_round_end, int):
        return None
    if not isinstance(imported_model, str):
        return None
    if not isinstance(replaced_agent_id, str):
        return None
    if not isinstance(source_a_run_id, str):
        return None
    if not isinstance(source_a_run_dir, str):
        return None
    if not isinstance(source_b_run_id, str):
        return None
    if not isinstance(source_b_run_dir, str):
        return None
    return _ManifestSummary(
        round_start=round_start,
        rounds_after_swap=rounds_after_swap,
        source_b_round_end=source_b_round_end,
        imported_model=imported_model,
        replaced_agent_id=replaced_agent_id,
        source_a_run_id=source_a_run_id,
        source_a_run_dir=source_a_run_dir,
        source_b_run_id=source_b_run_id,
        source_b_run_dir=source_b_run_dir,
    )


def _read_labels(run_dir: Path) -> list[str]:
    """Return the labels stored in the run directory's ``labels.json``, or an empty list."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return []
    raw = orjson.loads(labels_path.read_bytes())
    if not isinstance(raw, list):
        return []
    return [label for label in raw if isinstance(label, str)]


def _compute_round_outcomes(
    events: list[SimulationEvent],
    agent_configs: list[AgentConfig],
) -> dict[int, bool]:
    """Per-round success boolean for every advanced round in ``events``."""
    advanced = sorted(collect_advanced_round_numbers(events=events))
    if not advanced:
        return {}
    if is_two_team_mode(agent_configs=agent_configs):
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
            round_numbers=advanced, events=team_a_events, label="Team A"
        )
        team_b_result = compute_team_result(
            round_numbers=advanced, events=team_b_events, label="Team B"
        )
        joint = set(team_a_result.won_rounds) & set(team_b_result.won_rounds)
        return {round_number: round_number in joint for round_number in advanced}
    solo_result = compute_team_result(round_numbers=advanced, events=events, label="solo")
    won = set(solo_result.won_rounds)
    return {round_number: round_number in won for round_number in advanced}


class _SourceRunSummary(NamedTuple):
    """Cached per-round outcomes plus agent configs for a source run dir."""

    round_outcomes: dict[int, bool]
    agent_configs: list[AgentConfig]


_source_summary_cache: dict[Path, _SourceRunSummary] = {}


def _load_source_summary(run_dir: Path, scenario_name: str) -> _SourceRunSummary:
    """Replay events for ``run_dir`` once and return outcomes + agent configs (cached)."""
    cached = _source_summary_cache.get(run_dir)
    if cached is not None:
        return cached
    log_path = run_dir / f"{scenario_name}.jsonl"
    if not log_path.exists():
        summary = _SourceRunSummary(round_outcomes={}, agent_configs=[])
        _source_summary_cache[run_dir] = summary
        return summary
    events = asyncio.run(load_events(log_path=log_path))
    agent_configs = extract_agent_configs(events=events)
    outcomes = _compute_round_outcomes(events=events, agent_configs=agent_configs)
    summary = _SourceRunSummary(round_outcomes=outcomes, agent_configs=agent_configs)
    _source_summary_cache[run_dir] = summary
    return summary


def _model_for_agent(agent_configs: list[AgentConfig], agent_id: str) -> str:
    """Return the model registered for ``agent_id``; ``"unknown"`` if missing."""
    for config in agent_configs:
        if config.agent_id == agent_id:
            return config.model
    return "unknown"


def _resolve_run_dir(stored_dir: str) -> Path | None:
    """Return the run directory, trying the stored path then cwd-relative."""
    raw_path = Path(stored_dir)
    if raw_path.is_dir():
        return raw_path
    cwd_relative = Path.cwd() / stored_dir
    if cwd_relative.is_dir():
        return cwd_relative
    return None


def build_cross_swap_run(evaluated: EvaluatedRun) -> CrossSwapRun | None:
    """Convert an ``EvaluatedRun`` into a ``CrossSwapRun`` if it qualifies.

    A run qualifies when it has a ``cross_run_replace_manifest.json``, the
    swapped run's JSONL has at least one advanced round at or after
    ``round_start``, and at least one of source A / source B can be located
    with usable round outcomes.
    """
    manifest = _read_manifest_summary(run_dir=evaluated.run_dir)
    if manifest is None:
        return None
    swapped_summary = _load_source_summary(
        run_dir=evaluated.run_dir, scenario_name=evaluated.scenario_name
    )
    swapped_outcomes = {
        round_number: succeeded
        for round_number, succeeded in swapped_summary.round_outcomes.items()
        if round_number >= manifest.round_start
    }
    if not swapped_outcomes:
        logger.warning(
            "Skipping %s: no advanced rounds at or after round_start=%d in swapped run",
            evaluated.run_id,
            manifest.round_start,
        )
        return None
    source_a_dir = _resolve_run_dir(stored_dir=manifest.source_a_run_dir)
    source_b_dir = _resolve_run_dir(stored_dir=manifest.source_b_run_dir)
    if source_a_dir is None and source_b_dir is None:
        logger.warning(
            "Skipping %s: neither source A (%r) nor source B (%r) found",
            evaluated.run_id,
            manifest.source_a_run_dir,
            manifest.source_b_run_dir,
        )
        return None
    if source_a_dir is not None:
        source_a_summary = _load_source_summary(
            run_dir=source_a_dir, scenario_name=evaluated.scenario_name
        )
    else:
        source_a_summary = _SourceRunSummary(round_outcomes={}, agent_configs=[])
    if source_b_dir is not None:
        source_b_summary = _load_source_summary(
            run_dir=source_b_dir, scenario_name=evaluated.scenario_name
        )
    else:
        source_b_summary = _SourceRunSummary(round_outcomes={}, agent_configs=[])
    labels = _read_labels(run_dir=evaluated.run_dir)
    return CrossSwapRun(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        scenario_name=evaluated.scenario_name,
        round_start=manifest.round_start,
        rounds_after_swap=manifest.rounds_after_swap,
        source_b_round_end=manifest.source_b_round_end,
        imported_model=manifest.imported_model,
        source_a_run_id=manifest.source_a_run_id,
        source_b_run_id=manifest.source_b_run_id,
        source_a_replaced_agent_model=_model_for_agent(
            agent_configs=source_a_summary.agent_configs,
            agent_id=manifest.replaced_agent_id,
        ),
        source_b_replaced_agent_model=_model_for_agent(
            agent_configs=source_b_summary.agent_configs,
            agent_id=manifest.replaced_agent_id,
        ),
        swapped_round_outcomes=swapped_outcomes,
        source_a_round_outcomes=source_a_summary.round_outcomes,
        source_b_round_outcomes=source_b_summary.round_outcomes,
        labels=labels,
    )


def list_cross_swap_runs(evaluated_runs: list[EvaluatedRun]) -> list[CrossSwapRun]:
    """Filter ``evaluated_runs`` to runs labeled ``cross_team`` with a usable manifest."""
    out: list[CrossSwapRun] = []
    for run in evaluated_runs:
        labels = _read_labels(run_dir=run.run_dir)
        if _CROSS_TEAM_LABEL not in labels:
            continue
        cross_swap = build_cross_swap_run(evaluated=run)
        if cross_swap is not None:
            out.append(cross_swap)
    return out
