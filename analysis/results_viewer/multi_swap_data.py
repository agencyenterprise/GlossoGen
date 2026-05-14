"""Load runs with one or more in-run agent swaps and score round_success per phase.

A *phase* is a contiguous round window between two adjacent ``AgentSwappedMidRun``
events (or between run start and the first swap, or between the last swap and
the run's last advanced round). For 3 swaps you get 4 phases (A, B, C, D).
Each phase carries:

* ``round_start`` / ``round_end`` — inclusive round bounds.
* ``swap`` — the swap event that opened this phase (``None`` for Phase A).
* ``round_outcomes`` — per-round success boolean for every advanced round in
  the phase, computed via the same helpers used by the round-success metrics.
* ``score`` — fraction of phase rounds stabilized.

Performance: runs without an ``agent_swapped_mid_run`` event are detected via
a cheap byte-level substring scan and skipped before the heavy pydantic-event
load runs. Computed ``MultiSwapRun`` payloads are cached per run directory in
``multi_swap_cache.json`` keyed on the JSONL's size + mtime, so repeat tab
loads on completed runs avoid re-parsing the log. Per-run loads run in a
worker-thread pool via ``asyncio.gather`` + ``asyncio.to_thread`` so a UI
listing dozens of runs scales with available cores instead of summing the
per-run latency.

The module is streamlit-free.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

import orjson
from pydantic import BaseModel

from analysis.results_viewer.run_catalog import EvaluatedRun
from schmidt.evaluation.log_reader import extract_agent_configs, load_events
from schmidt.evaluation.metric_core.resume_anchors import collect_advanced_round_numbers
from schmidt.evaluation.metric_core.round_result_index import per_round_joint_success
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentSwappedMidRun, SimulationEvent

logger = logging.getLogger(__name__)


_MULTI_SWAP_CACHE_FILENAME = "multi_swap_cache.json"
_SWAP_MARKER = b'"event_type":"agent_swapped_mid_run"'
_SIM_ENDED_MARKER = b'"event_type":"simulation_ended"'


class SwapDescriptor(NamedTuple):
    """The fields of an ``AgentSwappedMidRun`` event the multi-swap tab uses."""

    round_number: int
    agent_id: str
    new_model: str
    new_provider: str


class PhaseScore(NamedTuple):
    """One phase's round window plus its round-success score.

    ``swap`` is ``None`` for Phase A (the pre-first-swap window) and carries
    the swap event for every subsequent phase. ``round_outcomes`` covers only
    rounds the simulation actually advanced into (handles short or aborted runs).
    """

    phase_index: int
    label: str
    round_start: int
    round_end: int
    swap: SwapDescriptor | None
    round_outcomes: dict[int, bool]
    won: int
    total: int
    score: float


class MultiSwapRun(NamedTuple):
    """A run with at least one in-run agent swap, scored per phase."""

    run_id: str
    run_dir: Path
    scenario_name: str
    primary_model: str
    initial_agent_models: dict[str, str]
    swaps: list[SwapDescriptor]
    phases: list[PhaseScore]
    labels: list[str]


class _CachedSwapDescriptor(BaseModel):
    """Cache-only model mirroring ``SwapDescriptor``."""

    round_number: int
    agent_id: str
    new_model: str
    new_provider: str


class _CachedPhaseScore(BaseModel):
    """Cache-only model mirroring ``PhaseScore``.

    ``round_outcomes_pairs`` stores ``(round_number, won)`` tuples instead of a
    JSON object so the round number stays an int after round-tripping (JSON
    object keys are always strings).
    """

    phase_index: int
    label: str
    round_start: int
    round_end: int
    swap: _CachedSwapDescriptor | None
    round_outcomes_pairs: list[tuple[int, bool]]
    won: int
    total: int
    score: float


class _CachedMultiSwapRun(BaseModel):
    """On-disk cache schema for one ``MultiSwapRun``.

    ``jsonl_size`` and ``jsonl_mtime_ns`` form the cache key; if the JSONL
    file's stats differ, the cache is invalidated and the run is rescanned.
    """

    schema_version: int
    jsonl_size: int
    jsonl_mtime_ns: int
    run_id: str
    scenario_name: str
    primary_model: str
    initial_agent_models: dict[str, str]
    swaps: list[_CachedSwapDescriptor]
    phases: list[_CachedPhaseScore]
    labels: list[str]


_CACHE_SCHEMA_VERSION = 1


def _read_labels(run_dir: Path) -> list[str]:
    """Return the labels stored in the run directory's ``labels.json``."""
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
    round_numbers: list[int],
) -> dict[int, bool]:
    """Per-round joint-success boolean over ``round_numbers``."""
    _ = agent_configs
    if not round_numbers:
        return {}
    joint = per_round_joint_success(events=events)
    return {round_number: joint.get(round_number, False) for round_number in round_numbers}


def _build_swap_descriptors(events: list[SimulationEvent]) -> list[SwapDescriptor]:
    """Extract swap events sorted by round_number ascending."""
    descriptors = [
        SwapDescriptor(
            round_number=event.round_number,
            agent_id=event.agent_id,
            new_model=event.new_model,
            new_provider=event.new_provider,
        )
        for event in events
        if isinstance(event, AgentSwappedMidRun)
    ]
    descriptors.sort(key=lambda d: d.round_number)
    return descriptors


def _phase_label(phase_index: int, swap: SwapDescriptor | None) -> str:
    """Compose the human-readable phase label."""
    letter = chr(ord("A") + phase_index)
    if swap is None:
        return f"Phase {letter} (initial)"
    return f"Phase {letter} (swap {swap.agent_id} → {swap.new_model})"


def _build_phases(
    events: list[SimulationEvent],
    agent_configs: list[AgentConfig],
    swaps: list[SwapDescriptor],
) -> list[PhaseScore]:
    """Carve the run into phases between adjacent swaps and score each one."""
    advanced = sorted(collect_advanced_round_numbers(events=events))
    if not advanced:
        return []
    last_round = advanced[-1]
    boundaries: list[tuple[int, int, SwapDescriptor | None]] = []
    pre_first_end = swaps[0].round_number - 1 if swaps else last_round
    if pre_first_end >= 1:
        boundaries.append((1, pre_first_end, None))
    for index, swap in enumerate(swaps):
        if index + 1 < len(swaps):
            phase_end = swaps[index + 1].round_number - 1
        else:
            phase_end = last_round
        if phase_end < swap.round_number:
            continue
        boundaries.append((swap.round_number, phase_end, swap))

    advanced_set = set(advanced)
    phases: list[PhaseScore] = []
    for phase_index, (round_start, round_end, boundary_swap) in enumerate(boundaries):
        phase_rounds = sorted(r for r in range(round_start, round_end + 1) if r in advanced_set)
        outcomes = _compute_round_outcomes(
            events=events,
            agent_configs=agent_configs,
            round_numbers=phase_rounds,
        )
        won = sum(1 for value in outcomes.values() if value)
        total = len(outcomes)
        score = won / total if total > 0 else 0.0
        phases.append(
            PhaseScore(
                phase_index=phase_index,
                label=_phase_label(phase_index=phase_index, swap=boundary_swap),
                round_start=round_start,
                round_end=round_end,
                swap=boundary_swap,
                round_outcomes=outcomes,
                won=won,
                total=total,
                score=score,
            )
        )
    return phases


def _initial_agent_models(agent_configs: list[AgentConfig]) -> dict[str, str]:
    """Map agent_id to its registered model (from the run's first AgentRegistered events)."""
    models: dict[str, str] = {}
    for config in agent_configs:
        models[config.agent_id] = config.model
    return models


_MARKER_SCAN_CACHE: dict[Path, tuple[int, int, bool, bool]] = {}


def _scan_jsonl_for_markers_sync(log_path: Path) -> tuple[bool, bool]:
    """Single byte-level pass that returns ``(has_swap, run_completed)``.

    Uses substring matching against the raw JSONL bytes — far cheaper than
    parsing every line into a typed event when the goal is just to decide
    whether the run is even eligible for the multi-swap tab and whether it
    is safe to write a long-lived cache. Memoized per ``log_path`` keyed
    on the JSONL's size + mtime, so repeat renders skip the file I/O.
    """
    stat = log_path.stat()
    cached = _MARKER_SCAN_CACHE.get(log_path)
    if cached is not None and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
        return cached[2], cached[3]
    has_swap = False
    has_end = False
    with open(log_path, mode="rb") as f:
        for line in f:
            if not has_swap and _SWAP_MARKER in line:
                has_swap = True
            if not has_end and _SIM_ENDED_MARKER in line:
                has_end = True
            if has_swap and has_end:
                break
    _MARKER_SCAN_CACHE[log_path] = (stat.st_size, stat.st_mtime_ns, has_swap, has_end)
    return has_swap, has_end


def _cache_path(run_dir: Path) -> Path:
    """Path to the per-run multi-swap cache file."""
    return run_dir / _MULTI_SWAP_CACHE_FILENAME


def _read_cache(run_dir: Path, log_path: Path) -> MultiSwapRun | None:
    """Load and decode the cached ``MultiSwapRun`` for ``run_dir``, if still valid.

    Returns ``None`` when the cache file is missing, the cached schema does
    not match, or the JSONL's size/mtime no longer match the cached values.
    """
    cache_path = _cache_path(run_dir=run_dir)
    if not cache_path.exists():
        return None
    try:
        cached = _CachedMultiSwapRun.model_validate_json(cache_path.read_bytes())
    except Exception:
        logger.exception("Failed to read multi-swap cache at %s", cache_path)
        return None
    if cached.schema_version != _CACHE_SCHEMA_VERSION:
        return None
    log_stat = log_path.stat()
    if cached.jsonl_size != log_stat.st_size:
        return None
    if cached.jsonl_mtime_ns != log_stat.st_mtime_ns:
        return None
    swaps = [
        SwapDescriptor(
            round_number=descriptor.round_number,
            agent_id=descriptor.agent_id,
            new_model=descriptor.new_model,
            new_provider=descriptor.new_provider,
        )
        for descriptor in cached.swaps
    ]
    swap_by_round = {descriptor.round_number: descriptor for descriptor in swaps}
    phases = [
        PhaseScore(
            phase_index=phase.phase_index,
            label=phase.label,
            round_start=phase.round_start,
            round_end=phase.round_end,
            swap=swap_by_round.get(phase.swap.round_number) if phase.swap is not None else None,
            round_outcomes=dict(phase.round_outcomes_pairs),
            won=phase.won,
            total=phase.total,
            score=phase.score,
        )
        for phase in cached.phases
    ]
    return MultiSwapRun(
        run_id=cached.run_id,
        run_dir=run_dir,
        scenario_name=cached.scenario_name,
        primary_model=cached.primary_model,
        initial_agent_models=cached.initial_agent_models,
        swaps=swaps,
        phases=phases,
        labels=_read_labels(run_dir=run_dir),
    )


def _write_cache(run_dir: Path, log_path: Path, multi_swap: MultiSwapRun) -> None:
    """Persist ``multi_swap`` to disk so the next tab load skips the re-parse."""
    log_stat = log_path.stat()
    payload = _CachedMultiSwapRun(
        schema_version=_CACHE_SCHEMA_VERSION,
        jsonl_size=log_stat.st_size,
        jsonl_mtime_ns=log_stat.st_mtime_ns,
        run_id=multi_swap.run_id,
        scenario_name=multi_swap.scenario_name,
        primary_model=multi_swap.primary_model,
        initial_agent_models=multi_swap.initial_agent_models,
        swaps=[
            _CachedSwapDescriptor(
                round_number=swap.round_number,
                agent_id=swap.agent_id,
                new_model=swap.new_model,
                new_provider=swap.new_provider,
            )
            for swap in multi_swap.swaps
        ],
        phases=[
            _CachedPhaseScore(
                phase_index=phase.phase_index,
                label=phase.label,
                round_start=phase.round_start,
                round_end=phase.round_end,
                swap=(
                    _CachedSwapDescriptor(
                        round_number=phase.swap.round_number,
                        agent_id=phase.swap.agent_id,
                        new_model=phase.swap.new_model,
                        new_provider=phase.swap.new_provider,
                    )
                    if phase.swap is not None
                    else None
                ),
                round_outcomes_pairs=sorted(phase.round_outcomes.items()),
                won=phase.won,
                total=phase.total,
                score=phase.score,
            )
            for phase in multi_swap.phases
        ],
        labels=multi_swap.labels,
    )
    cache_path = _cache_path(run_dir=run_dir)
    try:
        cache_path.write_bytes(orjson.dumps(payload.model_dump(mode="json")))
    except Exception:
        logger.exception("Failed to write multi-swap cache at %s", cache_path)


def _build_multi_swap_run_from_events(
    evaluated: EvaluatedRun,
    events: list[SimulationEvent],
) -> MultiSwapRun | None:
    """Pure compute step: turn parsed events into a ``MultiSwapRun`` (or ``None``)."""
    swaps = _build_swap_descriptors(events=events)
    if not swaps:
        return None
    agent_configs = extract_agent_configs(events=events)
    phases = _build_phases(events=events, agent_configs=agent_configs, swaps=swaps)
    if not phases:
        return None
    return MultiSwapRun(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        scenario_name=evaluated.scenario_name,
        primary_model=evaluated.metadata.primary_model,
        initial_agent_models=_initial_agent_models(agent_configs=agent_configs),
        swaps=swaps,
        phases=phases,
        labels=_read_labels(run_dir=evaluated.run_dir),
    )


_MULTI_SWAP_RUN_CACHE: dict[Path, tuple[int, int, MultiSwapRun | None]] = {}


async def _build_multi_swap_run_async(evaluated: EvaluatedRun) -> MultiSwapRun | None:
    """Async pipeline: fast pre-filter → cache check → load+score → cache write.

    The fast path returns from an in-memory dict keyed on the JSONL's
    ``(size, mtime_ns)`` — most renders hit this and skip both the
    marker scan and the on-disk cache read.
    """
    log_path = evaluated.run_dir / f"{evaluated.scenario_name}.jsonl"
    if not log_path.exists():
        return None

    has_swap, run_completed = _scan_jsonl_for_markers_sync(log_path)
    if not has_swap:
        return None

    log_stat = log_path.stat()
    cached_in_memory = _MULTI_SWAP_RUN_CACHE.get(log_path)
    if (
        cached_in_memory is not None
        and cached_in_memory[0] == log_stat.st_size
        and cached_in_memory[1] == log_stat.st_mtime_ns
    ):
        return cached_in_memory[2]

    cached = await asyncio.to_thread(_read_cache, evaluated.run_dir, log_path)
    if cached is not None:
        _MULTI_SWAP_RUN_CACHE[log_path] = (log_stat.st_size, log_stat.st_mtime_ns, cached)
        return cached

    events = await load_events(log_path=log_path)
    multi_swap = _build_multi_swap_run_from_events(evaluated=evaluated, events=events)
    if multi_swap is None:
        _MULTI_SWAP_RUN_CACHE[log_path] = (log_stat.st_size, log_stat.st_mtime_ns, None)
        return None

    if run_completed:
        await asyncio.to_thread(_write_cache, evaluated.run_dir, log_path, multi_swap)
    _MULTI_SWAP_RUN_CACHE[log_path] = (log_stat.st_size, log_stat.st_mtime_ns, multi_swap)
    return multi_swap


def build_multi_swap_run(evaluated: EvaluatedRun) -> MultiSwapRun | None:
    """Construct a ``MultiSwapRun`` for any run with at least one ``AgentSwappedMidRun`` event.

    Synchronous wrapper around the async pipeline; preserved for ad-hoc scripts
    that don't run inside an event loop.
    """
    return asyncio.run(_build_multi_swap_run_async(evaluated=evaluated))


def _has_swap_marker(evaluated: EvaluatedRun) -> bool:
    """Synchronous fast pre-filter: ``True`` if the JSONL contains a swap marker."""
    log_path = evaluated.run_dir / f"{evaluated.scenario_name}.jsonl"
    if not log_path.exists():
        return False
    has_swap, _ = _scan_jsonl_for_markers_sync(log_path)
    return has_swap


async def _list_multi_swap_runs_async(
    evaluated_runs: list[EvaluatedRun],
) -> list[MultiSwapRun]:
    """Concurrent fan-out across candidate runs, returning successful builds.

    A cheap synchronous pre-filter drops runs whose JSONL has no swap
    marker before the asyncio dispatch — typical corpora have many runs
    but only a handful with in-run swaps, and skipping them keeps
    warm-cache renders close to a pure dict lookup.
    """
    candidates = [run for run in evaluated_runs if _has_swap_marker(evaluated=run)]
    if not candidates:
        return []
    results = await asyncio.gather(
        *(_build_multi_swap_run_async(evaluated=run) for run in candidates),
        return_exceptions=True,
    )
    out: list[MultiSwapRun] = []
    for source_run, result in zip(candidates, results, strict=True):
        if isinstance(result, BaseException):
            logger.exception(
                "Failed to build multi-swap run for %s",
                source_run.run_id,
                exc_info=result,
            )
            continue
        if isinstance(result, MultiSwapRun):
            out.append(result)
    return out


def list_multi_swap_runs(evaluated_runs: list[EvaluatedRun]) -> list[MultiSwapRun]:
    """Filter ``evaluated_runs`` to those with at least one in-run agent swap.

    Per-run loads run concurrently in worker threads and short-circuit on a
    cheap byte-level scan for the swap-event marker. Completed runs reuse a
    persisted cache (``multi_swap_cache.json``) keyed on the JSONL's size and
    mtime, so repeat tab loads on the same run are nearly free.
    """
    return asyncio.run(_list_multi_swap_runs_async(evaluated_runs=evaluated_runs))
