"""Drive 50 baseline veyru opus-4.7 runs (10 configs x 5 reps) at concurrency=3.

After each sim finishes successfully, writes labels.json with the standard
baseline tags plus `no_specialist`, so the new batch is distinguishable from
the older baseline batches.

Idempotent: at startup, scans existing run directories under runs/veyru/ and
counts how many runs already exist per (budget, pm) cell with matching labels
(``baseline`` + ``no_specialist`` + ``opus-4.7`` + ``budget=<N>`` +
``postmortem=true|false``). Only queues the missing reps to reach REPS per
cell, so re-running the script after a partial run continues where it left off
instead of duplicating work.
"""

import asyncio
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import NamedTuple, cast


class Job(NamedTuple):
    config: str
    budget: int
    pm: str
    pm_label: str
    rep: int


CONCURRENCY = 3
RUNS_DIR = Path("runs")
VEYRU_RUNS_DIR = RUNS_DIR / "veyru"
DRIVER_LOG = RUNS_DIR / "baseline_no_specialist_opus47_driver.log"
STDOUT_LOG_DIR = RUNS_DIR / "_no_specialist_opus47_stdouts"
STDOUT_LOG_DIR.mkdir(parents=True, exist_ok=True)

LABELS_BASE = ["baseline", "no_specialist", "opus-4.7", "single_team"]
BUDGETS = [150, 250, 450, 800, 2000]
PM_VARIANTS = [
    ("on", "postmortem=true", "knobs_baseline_budget_{budget}.json"),
    ("off", "postmortem=false", "knobs_baseline_no_postmortem_budget_{budget}.json"),
]
REPS = 5


def count_existing_runs() -> Counter[tuple[int, str]]:
    """Count completed runs per (budget, pm_label) using labels.json files.

    A run is counted only when its labels include every entry in LABELS_BASE
    plus a ``budget=<N>`` label and a ``postmortem=true|false`` label.
    """
    counts: Counter[tuple[int, str]] = Counter()
    if not VEYRU_RUNS_DIR.exists():
        return counts
    for run_dir in VEYRU_RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        labels_path = run_dir / "labels.json"
        if not labels_path.exists():
            continue
        try:
            labels = json.loads(labels_path.read_text())
        except Exception:
            continue
        if not isinstance(labels, list):
            continue
        typed_labels = cast(list[str], labels)
        if not all(tag in typed_labels for tag in LABELS_BASE):
            continue
        budget = None
        pm_label = None
        for label in typed_labels:
            if label.startswith("budget="):
                value = label.split("=", 1)[1]
                if value.isdigit():
                    budget = int(value)
            if label in ("postmortem=true", "postmortem=false"):
                pm_label = label
        if budget is None or pm_label is None:
            continue
        counts[(budget, pm_label)] += 1
    return counts


def build_queue() -> list[Job]:
    """Build the work queue, skipping (budget, pm) cells already at REPS."""
    existing = count_existing_runs()
    queue: list[Job] = []
    for budget in BUDGETS:
        for pm_state, pm_label, cfg_template in PM_VARIANTS:
            cfg_file = f"src/glossogen/scenarios/veyru/{cfg_template.format(budget=budget)}"
            already = existing[(budget, pm_label)]
            remaining = REPS - already
            if remaining <= 0:
                continue
            for rep in range(already, already + remaining):
                queue.append(
                    Job(
                        config=cfg_file,
                        budget=budget,
                        pm=pm_state,
                        pm_label=pm_label,
                        rep=rep,
                    )
                )
    return queue


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with DRIVER_LOG.open("a") as f:
        f.write(line + "\n")


RUN_DIR_RE = re.compile(r"Run directory:\s+(runs/veyru/[0-9_]+)")


def find_run_dir(stdout_log: Path) -> Path | None:
    if not stdout_log.exists():
        return None
    text = stdout_log.read_text(errors="replace")
    match = RUN_DIR_RE.search(text)
    if not match:
        return None
    return Path(match.group(1))


async def launch_job(idx: int, job: Job) -> None:
    stdout_log = STDOUT_LOG_DIR / f"job_{idx:03d}.log"
    cmd = (
        "VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru "
        "--model claude-opus-4-7 --provider anthropic --runs-dir ./runs "
        f"--config {job.config}"
    )
    log(f"START idx={idx:03d} budget={job.budget} pm={job.pm} rep={job.rep} -> {stdout_log}")
    with stdout_log.open("w") as f:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=f, stderr=asyncio.subprocess.STDOUT
        )
        rc = await proc.wait()
    log(f"EXIT  idx={idx:03d} rc={rc}")
    if rc != 0:
        log(f"FAIL  idx={idx:03d} non-zero exit; not labelling")
        return
    run_dir = find_run_dir(stdout_log)
    if run_dir is None:
        log(f"WARN  idx={idx:03d} could not parse run dir from stdout")
        return
    labels = sorted(LABELS_BASE + [f"budget={job.budget}", job.pm_label])
    labels_path = run_dir / "labels.json"
    labels_path.write_text(json.dumps(labels))
    log(f"LABEL idx={idx:03d} {run_dir.name} {labels}")


async def worker(worker_id: int, queue: asyncio.Queue[tuple[int, Job]]) -> None:
    while True:
        try:
            idx, job = queue.get_nowait()
        except asyncio.QueueEmpty:
            log(f"worker {worker_id} drained queue, exiting")
            return
        try:
            await launch_job(idx, job)
        finally:
            queue.task_done()


async def main() -> None:
    jobs = build_queue()
    log(f"== driver start: {len(jobs)} jobs, concurrency={CONCURRENCY} ==")
    queue: asyncio.Queue[tuple[int, Job]] = asyncio.Queue()
    for i, job in enumerate(jobs):
        queue.put_nowait((i, job))
    workers = [asyncio.create_task(worker(i, queue)) for i in range(CONCURRENCY)]
    await asyncio.gather(*workers)
    log("== driver done ==")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
