"""Data loading for the streamlit "Stabilize over-calling" tab.

Scans each veyru run's event JSONL to compare how many times the field observer
invoked the ``stabilize_veyru`` tool against how many problems the run actually
contained. Each round presents one case made of 1-5 stages, and every stage is a
distinct problem that needs its own ``stabilize_veyru`` call, so a raw call count
is not comparable across runs. The headline metric is therefore normalized:
``ratio = calls / (total stages * num_teams)`` -- ``1.0`` means one call per
problem, ``> 1.0`` means the agent over-called the tool.

The numerator counts every ``tool_call_invoked`` for ``stabilize_veyru`` (all
invocations, including ones that errored or were rejected by the judge), since
those are exactly the over-calls. The accepted / rejected / unjudged breakdown is
read from ``veyru_stabilization_judged`` events for context.
"""

import logging
from pathlib import Path
from typing import NamedTuple

import orjson

from analysis.results_viewer.run_catalog import EvaluatedRun

logger = logging.getLogger(__name__)

_SCENARIO_NAME = "veyru"
_STABILIZE_TOOL_NAME = "stabilize_veyru"


class RoundOvercall(NamedTuple):
    """One round's stage count (problems) and decomposed ``stabilize_veyru`` calls.

    ``calls`` splits into ``accepted`` (judge accepted), ``rejected`` (judge
    rejected -- a failed attempt on a still-open stage, i.e. a legitimate retry),
    and ``unjudged`` (no judgment emitted -- the case was already stabilized /
    collapsed / had no active stage, i.e. a redundant over-call).
    """

    round_number: int
    stages: int
    calls: int
    accepted: int
    rejected: int
    unjudged: int


class StabilizeOvercallRun(NamedTuple):
    """One veyru run's normalized over-calling profile.

    ``problems`` is the total number of stages across all rounds (one
    ``veyru_case_started`` per round). ``expected`` is ``problems * num_teams``.
    ``unjudged`` is the count of invocations that produced no
    ``veyru_stabilization_judged`` event (case already stabilized / collapsed /
    no active stage) -- the retry-normalized over-call signal, since failed
    retries land in ``rejected`` instead. Headline ratios are derived per the
    user's chosen numerator + aggregation via :func:`run_metric`.
    """

    run_id: str
    run_dir: Path
    model: str
    mode: str
    labels: tuple[str, ...]
    num_teams: int
    problems: int
    expected: int
    calls: int
    accepted: int
    rejected: int
    unjudged: int
    per_round: tuple[RoundOvercall, ...]


class _ScanResult(NamedTuple):
    """Raw per-run aggregates from a single JSONL pass, before team normalization."""

    problems: int
    calls: int
    accepted: int
    rejected: int
    unjudged: int
    per_round: tuple[RoundOvercall, ...]


class _CacheKey(NamedTuple):
    """Identity tuple for a run's on-disk inputs, mirroring ``run_catalog._RunCacheKey``."""

    jsonl_size: int
    jsonl_mtime_ns: int
    labels_size: int
    labels_mtime_ns: int


_OVERCALL_CACHE: dict[Path, tuple[_CacheKey, StabilizeOvercallRun]] = {}


def _read_labels(run_dir: Path) -> tuple[str, ...]:
    """Read ``labels.json`` as a tuple of strings; empty tuple when absent."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return ()
    try:
        raw = orjson.loads(labels_path.read_bytes())
    except orjson.JSONDecodeError:
        logger.exception("Failed to parse labels.json at %s", labels_path)
        return ()
    return tuple(str(label) for label in raw)


def _stat_cache_key(jsonl_path: Path, labels_path: Path) -> _CacheKey | None:
    """Build the cache key from JSONL + labels stats; ``None`` if the JSONL is missing."""
    try:
        jsonl_stat = jsonl_path.stat()
    except FileNotFoundError:
        return None
    try:
        labels_stat = labels_path.stat()
        labels_size = labels_stat.st_size
        labels_mtime_ns = labels_stat.st_mtime_ns
    except FileNotFoundError:
        labels_size = 0
        labels_mtime_ns = 0
    return _CacheKey(
        jsonl_size=jsonl_stat.st_size,
        jsonl_mtime_ns=jsonl_stat.st_mtime_ns,
        labels_size=labels_size,
        labels_mtime_ns=labels_mtime_ns,
    )


def _scan_overcall(jsonl_path: Path) -> _ScanResult:
    """Single linear scan of a run's JSONL collecting stages, calls, and judge verdicts.

    ``round_number`` is read off each event, falling back to the running round
    derived from ``round_advanced`` events for any event that omits it.
    """
    stages_by_round: dict[int, int] = {}
    calls_by_round: dict[int, int] = {}
    accepted_by_round: dict[int, int] = {}
    rejected_by_round: dict[int, int] = {}
    running_round = 0
    with jsonl_path.open("rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = orjson.loads(line)
            event_type = raw.get("event_type")
            if event_type == "round_advanced":
                advanced = raw.get("round_number")
                if isinstance(advanced, int):
                    running_round = advanced
                continue
            round_number = raw.get("round_number")
            if not isinstance(round_number, int):
                round_number = running_round
            if event_type == "veyru_case_started":
                stages_by_round[round_number] = len(raw.get("stages", []))
            elif event_type == "tool_call_invoked" and raw.get("tool_name") == _STABILIZE_TOOL_NAME:
                calls_by_round[round_number] = calls_by_round.get(round_number, 0) + 1
            elif event_type == "veyru_stabilization_judged":
                if raw.get("judge_match"):
                    accepted_by_round[round_number] = accepted_by_round.get(round_number, 0) + 1
                else:
                    rejected_by_round[round_number] = rejected_by_round.get(round_number, 0) + 1
    rounds = sorted(set(stages_by_round) | set(calls_by_round))
    per_round = tuple(
        _build_round(
            round_number=round_number,
            stages=stages_by_round.get(round_number, 0),
            calls=calls_by_round.get(round_number, 0),
            accepted=accepted_by_round.get(round_number, 0),
            rejected=rejected_by_round.get(round_number, 0),
        )
        for round_number in rounds
    )
    return _ScanResult(
        problems=sum(stages_by_round.values()),
        calls=sum(calls_by_round.values()),
        accepted=sum(accepted_by_round.values()),
        rejected=sum(rejected_by_round.values()),
        unjudged=sum(observation.unjudged for observation in per_round),
        per_round=per_round,
    )


def _build_round(
    round_number: int, stages: int, calls: int, accepted: int, rejected: int
) -> RoundOvercall:
    """Build a ``RoundOvercall``, deriving ``unjudged`` as the non-negative remainder.

    Every judged event originates from a call, so ``calls >= accepted + rejected``;
    ``max(0, ...)`` guards against any round-attribution skew between a call and
    its judgment.
    """
    unjudged = max(0, calls - accepted - rejected)
    return RoundOvercall(
        round_number=round_number,
        stages=stages,
        calls=calls,
        accepted=accepted,
        rejected=rejected,
        unjudged=unjudged,
    )


def _num_teams(run: EvaluatedRun) -> int:
    """Return ``2`` for two-team runs, else ``1``, read from the run's scenario_config."""
    if bool(run.metadata.scenario_config.get("two_teams", False)):
        return 2
    return 1


def _build_overcall_run(run: EvaluatedRun, scan: _ScanResult) -> StabilizeOvercallRun:
    """Assemble one ``StabilizeOvercallRun`` from a scan result + catalog metadata."""
    num_teams = _num_teams(run=run)
    return StabilizeOvercallRun(
        run_id=run.run_id,
        run_dir=run.run_dir,
        model=run.metadata.primary_model,
        mode=run.execution_mode,
        labels=_read_labels(run_dir=run.run_dir),
        num_teams=num_teams,
        problems=scan.problems,
        expected=scan.problems * num_teams,
        calls=scan.calls,
        accepted=scan.accepted,
        rejected=scan.rejected,
        unjudged=scan.unjudged,
        per_round=scan.per_round,
    )


def run_metric(run: StabilizeOvercallRun, use_redundant: bool, worst_round: bool) -> float:
    """Selected normalized over-call ratio for a run.

    ``use_redundant`` swaps the numerator from all calls to redundant
    (``unjudged``) calls only, excluding failed retries. ``worst_round`` returns
    the maximum per-round ratio instead of the whole-simulation total ratio.
    Denominator is ``stages * num_teams`` (per round, or summed across the run).
    """
    if worst_round:
        best = 0.0
        for observation in run.per_round:
            denominator = observation.stages * run.num_teams
            if denominator <= 0:
                continue
            numerator = _round_numerator(observation=observation, use_redundant=use_redundant)
            ratio = numerator / denominator
            if ratio > best:
                best = ratio
        return best
    if run.expected <= 0:
        return 0.0
    if use_redundant:
        return run.unjudged / run.expected
    return run.calls / run.expected


def _round_numerator(observation: RoundOvercall, use_redundant: bool) -> int:
    """Per-round numerator: redundant (unjudged) calls, or all calls."""
    if use_redundant:
        return observation.unjudged
    return observation.calls


def worst_round(run: StabilizeOvercallRun, use_redundant: bool) -> RoundOvercall | None:
    """Return the round with the highest numerator/stages ratio, or ``None`` if no rounds."""
    best_observation: RoundOvercall | None = None
    best_ratio = -1.0
    for observation in run.per_round:
        denominator = observation.stages * run.num_teams
        if denominator <= 0:
            continue
        ratio = _round_numerator(observation=observation, use_redundant=use_redundant) / denominator
        if ratio > best_ratio:
            best_ratio = ratio
            best_observation = observation
    return best_observation


def load_overcall_runs(evaluated: list[EvaluatedRun]) -> list[StabilizeOvercallRun]:
    """Compute the over-calling profile for every evaluated veyru run.

    Memoized per run on ``(jsonl, labels.json)`` stats so the cold JSONL scan
    runs once per run per session; re-renders cost only ``stat`` calls. Runs
    with zero problems (no ``veyru_case_started`` -- crashed / non-standard) are
    skipped. Sorted by ``ratio`` descending so the worst over-callers surface first.
    """
    out: list[StabilizeOvercallRun] = []
    for run in evaluated:
        if run.scenario_name != _SCENARIO_NAME:
            continue
        jsonl_path = run.run_dir / f"{_SCENARIO_NAME}.jsonl"
        labels_path = run.run_dir / "labels.json"
        cache_key = _stat_cache_key(jsonl_path=jsonl_path, labels_path=labels_path)
        if cache_key is None:
            continue
        cached = _OVERCALL_CACHE.get(run.run_dir)
        if cached is not None and cached[0] == cache_key:
            out.append(cached[1])
            continue
        scan = _scan_overcall(jsonl_path=jsonl_path)
        if scan.problems == 0:
            continue
        overcall_run = _build_overcall_run(run=run, scan=scan)
        _OVERCALL_CACHE[run.run_dir] = (cache_key, overcall_run)
        out.append(overcall_run)
    return out


def distinct_labels(runs: list[StabilizeOvercallRun]) -> list[str]:
    """Sorted union of every label across the runs, for the label filter widget."""
    seen: set[str] = set()
    for run in runs:
        seen.update(run.labels)
    return sorted(seen)
