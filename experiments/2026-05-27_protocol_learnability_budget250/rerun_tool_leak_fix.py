"""Re-run tool_leak-affected replace-agent runs with the fixed history builder.

Reads a spec list (produced from the affected runs' manifests) and re-executes
each as a fresh ``glossogen replace-agent`` run on the current (fixed) code, which
no longer leaks the predecessor's pre-floor ``stabilize_veyru`` history. Each new
run is labelled with the original run's labels (minus ``tool_leak``) plus
``rerun=tool_leak_fix``, and the old→new mapping is recorded.

Concurrency is per-provider (default 6): an ``openai`` queue (gpt-5.4) and an
``anthropic`` queue (claude sonnet + opus, shared cap) advance in parallel. Each
``replace-agent`` invocation spawns a detached sim and returns immediately; the
queue gates new launches on the count of live sim subprocesses for that provider.

Idempotent: specs whose old run id is already in the mapping file are skipped, so
a preflight (``--max-launches 2``) can be followed by an unlimited run that
continues the remainder.
"""

import argparse
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import NamedTuple

_REPO = Path(__file__).resolve().parents[2]
_RUNS_DIR = _REPO / "runs"
_KNOBS_PATH = Path("/tmp/rerun_tool_leak_pm_off_knobs.json")
_LOG_PATH = Path("/tmp/rerun_tool_leak_fix.log")
_NEW_RUN_RE = re.compile(r"new_run_id=veyru/(\d+)")


class RerunSpec(NamedTuple):
    """One affected run to re-execute."""

    old_run: str
    src: str
    round_start: int
    rounds_after_swap: int
    floor: int
    model: str
    provider: str
    labels: list[str]


def _log(message: str) -> None:
    """Append a timestamped line to the orchestrator log and stdout."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    with _LOG_PATH.open("a") as handle:
        handle.write(line + "\n")


def _load_specs(spec_file: Path) -> list[RerunSpec]:
    """Load re-run specs from the JSON produced during planning."""
    raw = json.loads(spec_file.read_text())
    specs: list[RerunSpec] = []
    for entry in raw:
        specs.append(
            RerunSpec(
                old_run=entry["run"],
                src=entry["src"],
                round_start=entry["round_start"],
                rounds_after_swap=entry["rounds_after_swap"],
                floor=entry["floor"],
                model=entry["model"],
                provider=entry["provider"],
                labels=entry["labels"],
            )
        )
    return specs


def _count_running(model_pattern: str) -> int:
    """Count live ``glossogen run veyru --resume`` sims for a model pattern."""
    result = subprocess.run(
        ["pgrep", "-f", f"-m glossogen run veyru --model {model_pattern}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _read_mapping(mapping_path: Path) -> dict[str, str]:
    """Load the old_run -> new_run mapping (empty when absent)."""
    if not mapping_path.exists():
        return {}
    return json.loads(mapping_path.read_text())


def _append_mapping(mapping_path: Path, old_run: str, new_run: str, lock: threading.Lock) -> None:
    """Record one old->new mapping entry under a lock."""
    with lock:
        mapping = _read_mapping(mapping_path=mapping_path)
        mapping[old_run] = new_run
        mapping_path.write_text(json.dumps(mapping, indent=2))


def _apply_labels(new_run: str, labels: list[str]) -> None:
    """Write the new run's labels.json (original labels + rerun tag, no tool_leak)."""
    new_labels = [label for label in labels if label != "tool_leak"]
    if "rerun=tool_leak_fix" not in new_labels:
        new_labels.append("rerun=tool_leak_fix")
    (_RUNS_DIR / "veyru" / new_run / "labels.json").write_text(json.dumps(new_labels))


def _launch_one(spec: RerunSpec, mapping_path: Path, lock: threading.Lock) -> None:
    """Run one replace-agent re-run, then label the new run and record the mapping."""
    _log(f"[{spec.model}] launching src={spec.src} (replacing old={spec.old_run})")
    result = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "python",
            "-m",
            "glossogen",
            "replace-agent",
            "veyru",
            "--source-run-dir",
            str(_RUNS_DIR / spec.src),
            "--round-start",
            str(spec.round_start),
            "--rounds-after-swap",
            str(spec.rounds_after_swap),
            "--replaced-agent-id",
            "field_observer",
            "--history-from-round",
            str(spec.floor),
            "--model",
            spec.model,
            "--provider",
            spec.provider,
            "--runs-dir",
            str(_RUNS_DIR),
            "--knobs",
            str(_KNOBS_PATH),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        env={**os.environ, "VIRTUAL_ENV": ""},
        check=False,
    )
    match = _NEW_RUN_RE.search(result.stdout + result.stderr)
    if match is None:
        _log(f"[{spec.model}] ERROR no new_run_id for src={spec.src}: {result.stderr[-300:]}")
        return
    new_run = match.group(1)
    _apply_labels(new_run=new_run, labels=spec.labels)
    _append_mapping(mapping_path=mapping_path, old_run=spec.old_run, new_run=new_run, lock=lock)
    _log(f"[{spec.model}] launched new_run=veyru/{new_run} (src={spec.src})")
    time.sleep(2)


def _process_queue(
    specs: list[RerunSpec],
    model_pattern: str,
    cap: int,
    mapping_path: Path,
    lock: threading.Lock,
    max_launches: int | None,
    launched_counter: list[int],
) -> None:
    """Launch a provider's specs, gating on the live-sim count for its model pattern."""
    for spec in specs:
        with lock:
            done = _read_mapping(mapping_path=mapping_path)
            if spec.old_run in done:
                continue
            if max_launches is not None and launched_counter[0] >= max_launches:
                return
            launched_counter[0] += 1
        while _count_running(model_pattern=model_pattern) >= cap:
            time.sleep(30)
        _launch_one(spec=spec, mapping_path=mapping_path, lock=lock)
    _log(f"[{model_pattern}] queue complete")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-file", type=Path, required=True)
    parser.add_argument("--mapping-file", type=Path, required=True)
    parser.add_argument("--cap", type=int, default=6)
    parser.add_argument("--max-launches", type=int, default=None)
    args = parser.parse_args()

    _KNOBS_PATH.write_text(json.dumps({"postmortem_disabled_at_start": True}))
    specs = _load_specs(spec_file=args.spec_file)
    openai_specs = [s for s in specs if s.provider == "openai"]
    anthropic_specs = [s for s in specs if s.provider == "anthropic"]
    _log(
        f"=== rerun start: {len(specs)} specs "
        f"(openai={len(openai_specs)}, anthropic={len(anthropic_specs)}) "
        f"cap={args.cap} max_launches={args.max_launches} ==="
    )

    lock = threading.Lock()
    launched_counter = [0]
    threads = [
        threading.Thread(
            target=_process_queue,
            kwargs={
                "specs": openai_specs,
                "model_pattern": "gpt-5.4",
                "cap": args.cap,
                "mapping_path": args.mapping_file,
                "lock": lock,
                "max_launches": args.max_launches,
                "launched_counter": launched_counter,
            },
        ),
        threading.Thread(
            target=_process_queue,
            kwargs={
                "specs": anthropic_specs,
                "model_pattern": "claude-",
                "cap": args.cap,
                "mapping_path": args.mapping_file,
                "lock": lock,
                "max_launches": args.max_launches,
                "launched_counter": launched_counter,
            },
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    _log("=== rerun launch phase complete ===")


if __name__ == "__main__":
    main()
