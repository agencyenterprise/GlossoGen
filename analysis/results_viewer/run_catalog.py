"""Enumerates Veyru runs that have evaluation reports available."""

from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from typing import Any, NamedTuple

import orjson

from schmidt.evaluation.evaluation_report import EvaluationReport


class RunMetadata(NamedTuple):
    """Lightweight metadata read from the first ~10 lines of a run's JSONL."""

    scenario_config: dict[str, Any]
    primary_model: str


class EvaluatedRun(NamedTuple):
    """A run that has both a JSONL log and an evaluation report."""

    label: str
    run_dir: Path
    run_id: str
    run_timestamp: int
    scenario_name: str
    execution_mode: str
    report: EvaluationReport
    metadata: RunMetadata


class DayGroup(NamedTuple):
    """A day bucket of runs, ordered most-recent run first within the day."""

    day: date
    header: str
    runs: list["EvaluatedRun"]


def _parse_run_timestamp(run_dir_name: str) -> int:
    """Extract the base unix timestamp from a run dir name, ignoring fork suffixes like ``_2``.

    Forked runs reuse the source timestamp with a ``_N`` suffix. Python's ``int()`` silently
    treats underscores as digit separators (``int("1776_2") == 17762``), which would project
    the run centuries into the future; parse the numeric prefix explicitly instead.
    """
    base = run_dir_name.split("_", 1)[0]
    return int(base)


def _scan_metadata(jsonl_path: Path) -> RunMetadata:
    """Read the first handful of lines to grab scenario_config + first agent's model."""
    scenario_config: dict[str, Any] = {}
    primary_model = "unknown"
    with jsonl_path.open("rb") as f:
        for line_count, line in enumerate(f):
            if line_count > 20 and primary_model != "unknown":
                break
            raw = orjson.loads(line)
            event_type = raw.get("event_type")
            if event_type == "simulation_started":
                scenario_config = raw.get("scenario_config") or {}
            elif event_type == "agent_registered" and primary_model == "unknown":
                model = raw.get("model")
                if isinstance(model, str) and model:
                    primary_model = model
    return RunMetadata(scenario_config=scenario_config, primary_model=primary_model)


def _mode_label(scenario_config: dict[str, Any]) -> str:
    """Derive a compact mode label from Veyru knobs."""
    intern_enabled = bool(scenario_config.get("intern_enabled", False))
    two_teams = bool(scenario_config.get("two_teams", False))
    announce_swap = bool(scenario_config.get("announce_swap", False))
    if intern_enabled:
        return "intern"
    if two_teams and announce_swap:
        return "swap"
    if two_teams:
        return "silent-swap"
    return "single"


def _knob_fragments(scenario_config: dict[str, Any]) -> list[str]:
    """Pick a handful of high-signal knobs to surface in the picker label."""
    fragments: list[str] = []
    round_count = scenario_config.get("round_count")
    if isinstance(round_count, int):
        fragments.append(f"r={round_count}")
    round_time_budget = scenario_config.get("round_time_budget_seconds")
    if isinstance(round_time_budget, (int, float)):
        fragments.append(f"b={int(round_time_budget)}s")
    seconds_per_token = scenario_config.get("seconds_per_token")
    if isinstance(seconds_per_token, (int, float)):
        fragments.append(f"spt={seconds_per_token:g}")
    return fragments


def _postmortem_fragment(scenario_config: dict[str, Any], mode: str) -> str:
    """Describe postmortem state in words.

    Emits one of: "no postmortem", "postmortem", or (for modes with a boundary)
    "postmortem kept after boundary" / "postmortem dropped after boundary".
    """
    postmortem_enabled = bool(scenario_config.get("postmortem_enabled", False))
    if not postmortem_enabled:
        return "no postmortem"
    if mode == "single":
        return "postmortem"
    postmortem_after_swap = bool(scenario_config.get("postmortem_after_swap", False))
    if postmortem_after_swap:
        return "postmortem kept after boundary"
    return "postmortem dropped after boundary"


def _compose_label(metadata: RunMetadata, run_timestamp: int, run_dir_name: str) -> str:
    """Readable picker label: [HH:MM:SS] run_dir_name • mode • postmortem-state • knobs • model."""
    mode = _mode_label(scenario_config=metadata.scenario_config)
    postmortem_fragment = _postmortem_fragment(scenario_config=metadata.scenario_config, mode=mode)
    knob_fragments = _knob_fragments(scenario_config=metadata.scenario_config)
    if knob_fragments:
        knobs_fragment = " • " + " ".join(knob_fragments)
    else:
        knobs_fragment = ""
    time_str = datetime.fromtimestamp(run_timestamp).strftime("%H:%M:%S")
    return (
        f"[{time_str}] {run_dir_name} • {mode} • {postmortem_fragment}{knobs_fragment} • "
        f"{metadata.primary_model}"
    )


def _derive_run_id(scenario_name: str, run_dir: Path) -> str:
    """Compose the canonical run identifier from the on-disk path."""
    return f"{scenario_name}/{run_dir.name}"


def _load_runs_for_scenario(scenario_dir: Path, scenario_name: str) -> list[EvaluatedRun]:
    """Load every run directory under ``scenario_dir`` that has an evaluation report."""
    out: list[EvaluatedRun] = []
    for entry in sorted(scenario_dir.iterdir()):
        if not entry.is_dir():
            continue
        report_path = entry / f"{scenario_name}_report.json"
        jsonl_path = entry / f"{scenario_name}.jsonl"
        if not report_path.exists() or not jsonl_path.exists():
            continue
        report = EvaluationReport.model_validate_json(report_path.read_bytes())
        metadata = _scan_metadata(jsonl_path=jsonl_path)
        run_timestamp = _parse_run_timestamp(run_dir_name=entry.name)
        label = _compose_label(
            metadata=metadata, run_timestamp=run_timestamp, run_dir_name=entry.name
        )
        execution_mode = _mode_label(scenario_config=metadata.scenario_config)
        run_id = _derive_run_id(scenario_name=scenario_name, run_dir=entry)
        out.append(
            EvaluatedRun(
                label=label,
                run_dir=entry,
                run_id=run_id,
                run_timestamp=run_timestamp,
                scenario_name=scenario_name,
                execution_mode=execution_mode,
                report=report,
                metadata=metadata,
            )
        )
    return out


def list_evaluated_runs(runs_dir: Path) -> list[EvaluatedRun]:
    """Scan every scenario subdirectory of ``runs_dir`` for runs with an evaluation report."""
    if not runs_dir.is_dir():
        return []
    out: list[EvaluatedRun] = []
    for scenario_dir in sorted(runs_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        out.extend(
            _load_runs_for_scenario(scenario_dir=scenario_dir, scenario_name=scenario_dir.name)
        )
    out.sort(key=lambda r: r.run_timestamp, reverse=True)
    return out


def _format_day_header(day: date) -> str:
    """Match the frontend header style: e.g. 'Tuesday, April 21, 2026'."""
    weekday_and_month = day.strftime("%A, %B")
    return f"{weekday_and_month} {day.day}, {day.year}"


def group_runs_by_day(runs: list[EvaluatedRun]) -> list[DayGroup]:
    """Bucket runs by local calendar date, preserving the most-recent-first order."""
    buckets: OrderedDict[date, list[EvaluatedRun]] = OrderedDict()
    for run in runs:
        day = datetime.fromtimestamp(run.run_timestamp).date()
        bucket = buckets.get(day)
        if bucket is None:
            buckets[day] = [run]
        else:
            bucket.append(run)
    return [
        DayGroup(day=day, header=_format_day_header(day=day), runs=items)
        for day, items in buckets.items()
    ]
