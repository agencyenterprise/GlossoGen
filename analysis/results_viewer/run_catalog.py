"""Enumerates Veyru runs that have evaluation reports available."""

from pathlib import Path
from typing import Any, NamedTuple

import orjson

from schmidt.evaluation.evaluation_report import EvaluationReport


class RunMetadata(NamedTuple):
    """Lightweight metadata read from the first ~10 lines of a run's JSONL."""

    scenario_config: dict[str, Any]
    primary_model: str


class EvaluatedRun(NamedTuple):
    """A Veyru run that has both a JSONL log and a report.json."""

    label: str
    run_dir: Path
    report: EvaluationReport
    metadata: RunMetadata


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


def _compose_label(metadata: RunMetadata) -> str:
    """Readable multiselect label: mode • pm • model."""
    mode = _mode_label(scenario_config=metadata.scenario_config)
    if mode == "single":
        pm_fragment = ""
    else:
        pm_value = bool(metadata.scenario_config.get("postmortem_after_swap", False))
        pm_fragment = f" • pm={'on' if pm_value else 'off'}"
    return f"{mode}{pm_fragment} • {metadata.primary_model}"


def list_evaluated_runs(runs_dir: Path) -> list[EvaluatedRun]:
    """Scan ``runs_dir`` for veyru runs with a readable evaluation report."""
    veyru_dir = runs_dir / "veyru"
    if not veyru_dir.is_dir():
        return []
    out: list[EvaluatedRun] = []
    for entry in sorted(veyru_dir.iterdir()):
        if not entry.is_dir():
            continue
        report_path = entry / "veyru_report.json"
        jsonl_path = entry / "veyru.jsonl"
        if not report_path.exists() or not jsonl_path.exists():
            continue
        report = EvaluationReport.model_validate_json(report_path.read_bytes())
        metadata = _scan_metadata(jsonl_path=jsonl_path)
        label = _compose_label(metadata=metadata)
        out.append(
            EvaluatedRun(
                label=label,
                run_dir=entry,
                report=report,
                metadata=metadata,
            )
        )
    out.sort(key=lambda r: r.run_dir.name, reverse=True)
    return out
