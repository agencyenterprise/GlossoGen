"""Load replace-agent runs with per-round resumed/source outcomes the resume tab plots.

Each ``ResumeRun`` carries per-round success booleans for both the resumed run
itself and its source run, scored over every round each ran. The tab uses these
to plot one line per (replacement_model, round_start) bucket (averaged across
replicas) plus one line per source run for direct round-by-round comparison.

Round outcomes are computed by replaying the JSONL events through the same
helpers used by the round-success evaluators. Source outcomes are cached by
source run directory because multiple resumes typically share a source.

This module is streamlit-free so ad-hoc analysis scripts can reuse it.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

import orjson

from analysis.results_viewer.run_catalog import EvaluatedRun
from schmidt.evaluation.log_reader import extract_agent_configs, load_events
from schmidt.evaluation.metric_core.resume_anchors import collect_advanced_round_numbers
from schmidt.evaluation.metric_core.round_result_index import per_round_joint_success
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent

logger = logging.getLogger(__name__)


_REPLACE_MANIFEST_FILENAME = "replace_manifest.json"
_RESUME_LABEL = "resume"


class _ManifestSummary(NamedTuple):
    """Subset of ``replace_manifest.json`` the tab needs.

    Read directly from JSON rather than via ``schmidt.replace_manifest`` so the
    tab keeps working when the source schema renames or adds fields the tab
    does not consume (e.g. ``target_event_id`` was renamed from
    ``target_message_id``; both still appear in older runs).
    """

    round_start: int
    rounds_after_swap: int
    replacement_model: str
    source_run_id: str
    source_run_dir: str


class ResumeRun(NamedTuple):
    """A single replace-agent run with per-round outcomes for itself and its source.

    ``resumed_round_outcomes`` covers only post-swap rounds (round number
    ``>= round_start``); rounds 1..round_start-1 are inherited from the source's
    git history at clone time and would conflate source data with resume data.
    ``source_round_outcomes`` carries every advanced round from the source so
    callers can match a window themselves.
    """

    run_id: str
    run_dir: Path
    scenario_name: str
    round_start: int
    rounds_after_swap: int
    replacement_model: str
    source_run_id: str
    resumed_round_outcomes: dict[int, bool]
    source_round_outcomes: dict[int, bool]
    labels: list[str]

    def has_bugfix(self) -> bool:
        """Whether this run carries the ``bugfix`` label (cost-capture fix applied)."""
        return "bugfix" in self.labels

    def resumed_series_key(self) -> str:
        """Plot-series identifier for this run's resume bucket.

        Runs with the ``bugfix`` label are placed on a separate series so the
        chart can compare pre- and post-fix replicas side by side.
        """
        suffix = " · bugfix" if self.has_bugfix() else ""
        return f"{self.replacement_model} · R{self.round_start}{suffix}"

    def source_series_key(self) -> str:
        """Plot-series identifier for this run's source line."""
        return f"source · {self.source_run_id}"


def _read_manifest_summary(run_dir: Path) -> _ManifestSummary | None:
    """Read the replace-agent manifest fields the tab uses, or ``None`` if absent."""
    manifest_path = run_dir / _REPLACE_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    round_start = raw.get("round_start")
    rounds_after_swap = raw.get("rounds_after_swap")
    replacement_model = raw.get("replacement_model")
    source_run_id = raw.get("source_run_id")
    source_run_dir = raw.get("source_run_dir")
    if not isinstance(round_start, int):
        return None
    if not isinstance(rounds_after_swap, int):
        return None
    if not isinstance(replacement_model, str):
        return None
    if not isinstance(source_run_id, str):
        return None
    if not isinstance(source_run_dir, str):
        return None
    return _ManifestSummary(
        round_start=round_start,
        rounds_after_swap=rounds_after_swap,
        replacement_model=replacement_model,
        source_run_id=source_run_id,
        source_run_dir=source_run_dir,
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
    """Per-round joint-success boolean for every advanced round in ``events``."""
    _ = agent_configs
    advanced = sorted(collect_advanced_round_numbers(events=events))
    if not advanced:
        return {}
    joint = per_round_joint_success(events=events)
    return {round_number: joint.get(round_number, False) for round_number in advanced}


_outcomes_cache: dict[Path, dict[int, bool]] = {}


def _load_round_outcomes(run_dir: Path, scenario_name: str) -> dict[int, bool]:
    """Replay events for ``run_dir`` and return per-round success outcomes (cached)."""
    cached = _outcomes_cache.get(run_dir)
    if cached is not None:
        return cached
    log_path = run_dir / f"{scenario_name}.jsonl"
    if not log_path.exists():
        return {}
    events = asyncio.run(load_events(log_path=log_path))
    agent_configs = extract_agent_configs(events=events)
    outcomes = _compute_round_outcomes(events=events, agent_configs=agent_configs)
    _outcomes_cache[run_dir] = outcomes
    return outcomes


def _resolve_source_run_dir(manifest: _ManifestSummary) -> Path | None:
    """Return the source run directory, trying the stored path then cwd-relative."""
    raw_path = Path(manifest.source_run_dir)
    if raw_path.is_dir():
        return raw_path
    cwd_relative = Path.cwd() / manifest.source_run_dir
    if cwd_relative.is_dir():
        return cwd_relative
    return None


def build_resume_run(evaluated: EvaluatedRun) -> ResumeRun | None:
    """Convert an ``EvaluatedRun`` into a ``ResumeRun`` if it qualifies.

    A run qualifies when it has a ``replace_manifest.json``, the resumed run's
    JSONL produces at least one advanced round, and the source run directory
    can be resolved with at least one advanced round.
    """
    manifest = _read_manifest_summary(run_dir=evaluated.run_dir)
    if manifest is None:
        return None
    all_resumed_outcomes = _load_round_outcomes(
        run_dir=evaluated.run_dir, scenario_name=evaluated.scenario_name
    )
    resumed_outcomes = {
        round_number: succeeded
        for round_number, succeeded in all_resumed_outcomes.items()
        if round_number >= manifest.round_start
    }
    if not resumed_outcomes:
        logger.warning(
            "Skipping %s: no advanced rounds at or after round_start=%d in resumed run",
            evaluated.run_id,
            manifest.round_start,
        )
        return None
    source_run_dir = _resolve_source_run_dir(manifest=manifest)
    if source_run_dir is None:
        logger.warning(
            "Skipping %s: source run directory %r not found",
            evaluated.run_id,
            manifest.source_run_dir,
        )
        return None
    source_outcomes = _load_round_outcomes(
        run_dir=source_run_dir, scenario_name=evaluated.scenario_name
    )
    if not source_outcomes:
        logger.warning(
            "Skipping %s: no advanced rounds in source run %s",
            evaluated.run_id,
            manifest.source_run_id,
        )
        return None
    labels = _read_labels(run_dir=evaluated.run_dir)
    return ResumeRun(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        scenario_name=evaluated.scenario_name,
        round_start=manifest.round_start,
        rounds_after_swap=manifest.rounds_after_swap,
        replacement_model=manifest.replacement_model,
        source_run_id=manifest.source_run_id,
        resumed_round_outcomes=resumed_outcomes,
        source_round_outcomes=source_outcomes,
        labels=labels,
    )


def list_resume_runs(evaluated_runs: list[EvaluatedRun]) -> list[ResumeRun]:
    """Filter ``evaluated_runs`` to runs labeled ``resume`` with a usable replace manifest."""
    out: list[ResumeRun] = []
    for run in evaluated_runs:
        labels = _read_labels(run_dir=run.run_dir)
        if _RESUME_LABEL not in labels:
            continue
        resume = build_resume_run(evaluated=run)
        if resume is not None:
            out.append(resume)
    return out
