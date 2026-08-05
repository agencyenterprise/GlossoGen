#!/usr/bin/env python3
"""Render, inspect, and validate reproducible GlossoGen experiment records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = (
    "Question",
    "Expected decision",
    "Design",
    "Outcomes inspected",
    "Provenance",
    "Result",
    "Outcome",
    "Validity limitations",
    "What it changed",
    "Traps found",
)
RECORD_PATTERN = re.compile(r"<!-- experiment-record:v1\s*(\{.*?\})\s*-->", re.DOTALL)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    """Hash a JSON value canonically, independent of source formatting."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def relative_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def git_state(repo_root: Path) -> tuple[str, bool]:
    commit = git_output(repo_root, "rev-parse", "HEAD")
    dirty = bool(git_output(repo_root, "status", "--porcelain"))
    return commit, dirty


def find_event_log(run_dir: Path) -> Path:
    candidates = sorted(path for path in run_dir.glob("*.jsonl") if "debug" not in path.name)
    if len(candidates) != 1:
        names = ", ".join(path.name for path in candidates) or "none"
        raise ValueError(f"expected one non-debug JSONL in {run_dir}, found: {names}")
    return candidates[0]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(event, dict):
                raise ValueError(f"event at {path}:{line_number} is not an object")
            events.append(event)
    return events


def inspect_run(run_dir: Path, repo_root: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise ValueError(f"run directory does not exist: {run_dir}")
    event_log = find_event_log(run_dir)
    events = load_jsonl(event_log)
    started = next(
        (event for event in events if event.get("event_type") == "simulation_started"),
        None,
    )
    if started is None:
        raise ValueError(f"simulation_started is missing from {event_log}")
    ended_events = [event for event in events if event.get("event_type") == "simulation_ended"]
    ended = ended_events[-1] if ended_events else None
    config = started.get("scenario_config")
    if not isinstance(config, dict):
        config = {}
    registered = [event for event in events if event.get("event_type") == "agent_registered"]
    model_providers = sorted(
        {
            (str(event.get("model", "unknown")), str(event.get("provider", "unknown")))
            for event in registered
        }
    )
    rounds = [
        event.get("round_number")
        for event in events
        if event.get("event_type") == "round_advanced"
        and isinstance(event.get("round_number"), int)
    ]
    resolved_config = run_dir / "replace_config.json"
    if not resolved_config.exists():
        resolved_config = run_dir / "config.json"
    if resolved_config.exists():
        resolved_config_ref = relative_path(resolved_config, repo_root)
        resolved_config_hash = sha256_file(resolved_config)
    else:
        # Fresh runs historically did not persist a standalone config.json.
        # Their simulation_started snapshot is the authoritative resolved
        # configuration (including defaults added to the launch input).
        resolved_config_ref = (
            f"{relative_path(event_log, repo_root)}"
            "#simulation_started.scenario_config"
        )
        resolved_config_hash = sha256_json(config)
    manifest_path = run_dir / "replace_manifest.json"
    manifest: dict[str, Any] | None = None
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            manifest = loaded
    event_counts = Counter(str(event.get("event_type", "unknown")) for event in events)
    result: dict[str, Any] = {
        "run_id": started.get("run_id"),
        "run_dir": relative_path(run_dir, repo_root),
        "scenario": started.get("scenario_name"),
        "completed": ended is not None,
        "completion_reason": ended.get("reason") if ended else None,
        "total_cost_usd": ended.get("total_cost_usd") if ended else None,
        "started_at": started.get("timestamp"),
        "ended_at": ended.get("timestamp") if ended else None,
        "event_count": len(events),
        "event_type_counts": dict(sorted(event_counts.items())),
        "rounds": {
            "configured": config.get("round_count"),
            "first_advanced": min(rounds) if rounds else None,
            "last_advanced": max(rounds) if rounds else None,
        },
        "seed": config.get("seed"),
        "model_providers": [
            {"model": model, "provider": provider} for model, provider in model_providers
        ],
        "event_log": relative_path(event_log, repo_root),
        "event_log_sha256": sha256_file(event_log),
        "resolved_config": resolved_config_ref,
        "resolved_config_sha256": resolved_config_hash,
        "source": manifest,
    }
    return result


def render_run_markdown(facts: dict[str, Any]) -> str:
    models = ", ".join(f"{item['provider']}:{item['model']}" for item in facts["model_providers"])
    source = facts.get("source") or {}
    lines = [
        f"- Run: `{facts['run_dir']}`",
        f"- Scenario: `{facts['scenario']}`",
        f"- Completed: `{str(facts['completed']).lower()}`",
        f"- Completion reason: `{facts['completion_reason']}`",
        f"- API cost: `{facts['total_cost_usd']}`",
        f"- Model/provider: `{models or 'unknown'}`",
        f"- Seed: `{facts['seed']}`",
        f"- Configured rounds: `{facts['rounds']['configured']}`",
        f"- Last advanced round: `{facts['rounds']['last_advanced']}`",
        f"- Event log: `{facts['event_log']}`",
        f"- Event-log SHA-256: `{facts['event_log_sha256']}`",
        f"- Resolved config: `{facts['resolved_config']}`",
        f"- Config SHA-256: `{facts['resolved_config_sha256']}`",
    ]
    if source:
        lines.extend(
            [
                f"- Source run: `{source.get('source_run_id')}`",
                f"- Fork boundary: round `{source.get('round_start')}`",
                f"- Target event: `{source.get('target_event_id')}`",
            ]
        )
    return "\n".join(lines)


def render_template(args: argparse.Namespace) -> str:
    repo_root = Path(args.repo_root).resolve()
    commit, dirty = git_state(repo_root)
    opened = args.date or date.today().isoformat()
    metadata = {
        "schema_version": 1,
        "experiment_id": args.experiment_id,
        "base_commit": commit,
        "worktree_dirty": dirty,
        "commands": [],
        "configs": [],
        "runs": [],
    }
    record = json.dumps(metadata, indent=2, sort_keys=True)
    return f"""# {args.experiment_id} — {args.title}

**Status:** planned
**Date opened:** {opened}
**Date closed:** —

<!-- experiment-record:v1
{record}
-->

## Question

Pending.

## Expected decision

Pending.

## Design

Pending.

## Outcomes inspected

Pending.

## Provenance

- Base commit: `{commit}`
- Worktree dirty at planning: `{str(dirty).lower()}`
- Exact command: pending
- Config: pending
- Model/provider: pending
- Seed: pending
- Rounds: pending
- Source/fork boundary: pending

## Result

Pending.

## Outcome

Pending.

## Validity limitations

Pending.

## What it changed

Pending.

## Traps found

Pending.
"""


def parse_record(text: str) -> dict[str, Any]:
    match = RECORD_PATTERN.search(text)
    if match is None:
        raise ValueError("missing experiment-record:v1 JSON block")
    record = json.loads(match.group(1))
    if not isinstance(record, dict):
        raise ValueError("experiment-record:v1 must contain a JSON object")
    return record


def validate_record(path: Path, repo_root: Path, phase: str) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []
    headings = re.findall(r"^## (.+?)\s*$", text, flags=re.MULTILINE)
    missing = [section for section in REQUIRED_SECTIONS if section not in headings]
    if missing:
        errors.append(f"missing sections: {', '.join(missing)}")
    positions = [headings.index(section) for section in REQUIRED_SECTIONS if section in headings]
    if positions != sorted(positions):
        errors.append("required sections are out of order")
    status_match = re.search(r"^\*\*Status:\*\*\s*(.+)$", text, flags=re.MULTILINE)
    status = status_match.group(1).strip().lower() if status_match else ""
    if not status:
        errors.append("missing **Status:** line")
    effective_phase = phase
    if phase == "auto":
        effective_phase = "complete" if status.startswith(("complete", "invalid")) else "planned"
    try:
        record = parse_record(text)
    except (ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        return errors, warnings
    required_keys = {
        "schema_version",
        "experiment_id",
        "base_commit",
        "worktree_dirty",
        "commands",
        "configs",
        "runs",
    }
    absent = sorted(required_keys - set(record))
    if absent:
        errors.append(f"record block missing keys: {', '.join(absent)}")
    if record.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    commit = record.get("base_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        errors.append("base_commit must be a 40-character lowercase Git SHA")
    dirty = record.get("worktree_dirty")
    if not isinstance(dirty, bool):
        errors.append("worktree_dirty must be boolean")
    elif dirty:
        warnings.append("run was planned from a dirty worktree; commit alone cannot reproduce code")
    commands = record.get("commands")
    configs = record.get("configs")
    runs = record.get("runs")
    preregistered_text = text.split("## Result", maxsplit=1)[0]
    if re.search(r"(?im)^.*\bpending\b.*$", preregistered_text):
        errors.append("pre-run sections still contain pending placeholders")
    if not isinstance(commands, list) or not commands:
        errors.append("record requires at least one exact command before launch")
    elif isinstance(configs, list):
        recorded_config_paths = {
            item.get("path") for item in configs if isinstance(item, dict)
        }
        for index, command in enumerate(commands):
            if not isinstance(command, str):
                errors.append(f"commands[{index}] must be a string")
                continue
            try:
                argv = shlex.split(command)
            except ValueError as exc:
                errors.append(f"commands[{index}] is not valid shell syntax: {exc}")
                continue
            is_run_command = any(
                argv[offset : offset + 3] == ["-m", "glossogen", "run"]
                for offset in range(max(0, len(argv) - 2))
            )
            if not is_run_command:
                continue
            if "--knobs" in argv:
                errors.append(
                    f"commands[{index}] uses obsolete --knobs; glossogen run expects --config"
                )
            if "--config" not in argv:
                errors.append(f"commands[{index}] glossogen run is missing --config")
                continue
            config_index = argv.index("--config") + 1
            if config_index >= len(argv):
                errors.append(f"commands[{index}] --config has no path")
                continue
            command_config = argv[config_index]
            if command_config not in recorded_config_paths:
                errors.append(
                    f"commands[{index}] config is not hashed in the record: {command_config}"
                )
    if not isinstance(configs, list) or not configs:
        errors.append("record requires at least one config artifact before launch")
    if effective_phase == "complete":
        if not isinstance(runs, list) or not runs:
            errors.append("completed record requires at least one run artifact")
        if re.search(r"(?im)^\s*Pending\.\s*$", text):
            errors.append("completed record still contains a Pending. placeholder")
        if re.search(r"^\*\*Date closed:\*\*\s*[—-]\s*$", text, re.MULTILINE):
            errors.append("completed record requires a close date")
    if isinstance(configs, list):
        for index, item in enumerate(configs):
            if not isinstance(item, dict):
                errors.append(f"configs[{index}] must be an object")
                continue
            config_path = item.get("path")
            expected_hash = item.get("sha256")
            if not isinstance(config_path, str):
                errors.append(f"configs[{index}].path must be a string")
                continue
            absolute = repo_root / config_path
            if not absolute.is_file():
                errors.append(f"config does not exist: {config_path}")
            elif expected_hash != sha256_file(absolute):
                errors.append(f"config hash mismatch: {config_path}")
    if isinstance(runs, list):
        for index, item in enumerate(runs):
            if not isinstance(item, dict):
                errors.append(f"runs[{index}] must be an object")
                continue
            run_path = item.get("run_dir")
            if not isinstance(run_path, str):
                errors.append(f"runs[{index}].run_dir must be a string")
                continue
            try:
                facts = inspect_run(repo_root / run_path, repo_root)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            included = item.get("included", True)
            if included and not facts["completed"]:
                errors.append(f"included run is not complete: {run_path}")
            for key in ("event_log_sha256", "resolved_config_sha256"):
                expected = item.get(key)
                actual = facts.get(key)
                if expected is None:
                    if effective_phase == "complete":
                        errors.append(f"runs[{index}] missing {key}")
                elif expected != actual:
                    errors.append(f"{key} mismatch for {run_path}")
            if item.get("completed") is not None and item.get("completed") != facts["completed"]:
                errors.append(f"completion status mismatch for {run_path}")
            if (
                item.get("total_cost_usd") is not None
                and item.get("total_cost_usd") != facts["total_cost_usd"]
            ):
                errors.append(f"cost mismatch for {run_path}")
    return errors, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("render-template")
    template.add_argument("--experiment-id", required=True, type=str.upper)
    template.add_argument("--title", required=True)
    template.add_argument("--repo-root", default=".")
    template.add_argument("--date")

    inspect = subparsers.add_parser("inspect-run")
    inspect.add_argument("run_dir")
    inspect.add_argument("--repo-root", default=".")
    inspect.add_argument("--format", choices=("json", "markdown"), default="json")

    validate = subparsers.add_parser("validate-record")
    validate.add_argument("record")
    validate.add_argument("--repo-root", default=".")
    validate.add_argument("--phase", choices=("auto", "planned", "complete"), default="auto")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "render-template":
            print(render_template(args), end="")
            return 0
        if args.command == "inspect-run":
            facts = inspect_run(Path(args.run_dir), Path(args.repo_root))
            if args.format == "markdown":
                print(render_run_markdown(facts))
            else:
                print(json.dumps(facts, indent=2, sort_keys=True))
            return 0
        if args.command == "validate-record":
            errors, warnings = validate_record(
                Path(args.record), Path(args.repo_root).resolve(), args.phase
            )
            for warning in warnings:
                print(f"WARNING: {warning}")
            for error in errors:
                print(f"ERROR: {error}")
            if errors:
                return 1
            print("OK: experiment record is valid")
            return 0
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
