"""Smoke driver: 3 sonnet-4.6 + 5 opus-4.7 runs, budget=150, round_count=20.

All jobs use postmortem=on, seed=42, concurrency=3. Labels each completed run
with `smoke_round20` plus the standard model + budget tags so they are easy to
filter out in analysis later. This is a one-off pre-batch sanity check before
the full 50-job opus-4.7 baseline rerun.
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import NamedTuple


class Job(NamedTuple):
    model: str
    model_label: str
    rep: int


CONCURRENCY = 3
BUDGET = 150
ROUNDS = 20
RUNS_DIR = Path("runs")
DRIVER_LOG = RUNS_DIR / "smoke_8_driver.log"
STDOUT_LOG_DIR = RUNS_DIR / "_smoke_8_stdouts"
STDOUT_LOG_DIR.mkdir(parents=True, exist_ok=True)

CONFIG = "src/schmidt/scenarios/veyru/knobs_baseline_budget_150.json"

LABELS_BASE = [
    "smoke_round20",
    "no_specialist",
    "single_team",
    "postmortem=true",
    f"budget={BUDGET}",
    f"round_count={ROUNDS}",
]


def build_queue() -> list[Job]:
    queue: list[Job] = []
    for rep in range(3):
        queue.append(Job(model="claude-sonnet-4-6", model_label="sonnet-4.6", rep=rep))
    for rep in range(5):
        queue.append(Job(model="claude-opus-4-7", model_label="opus-4.7", rep=rep))
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
    stdout_log = STDOUT_LOG_DIR / f"job_{idx:03d}_{job.model_label}_rep{job.rep}.log"
    cmd = (
        "VIRTUAL_ENV= uv run --no-sync python -m schmidt run veyru "
        f"--model {job.model} --provider anthropic --runs-dir ./runs "
        f"--config {CONFIG} round_count={ROUNDS}"
    )
    log(f"START idx={idx:03d} model={job.model_label} rep={job.rep} -> {stdout_log}")
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
    labels = sorted(LABELS_BASE + [job.model_label])
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
            await launch_job(idx=idx, job=job)
        finally:
            queue.task_done()


async def main() -> None:
    jobs = build_queue()
    log(
        f"== smoke driver start: {len(jobs)} jobs (3 sonnet + 5 opus), "
        f"budget={BUDGET}, rounds={ROUNDS}, concurrency={CONCURRENCY} =="
    )
    queue: asyncio.Queue[tuple[int, Job]] = asyncio.Queue()
    for i, job in enumerate(jobs):
        queue.put_nowait((i, job))
    workers = [asyncio.create_task(worker(worker_id=i, queue=queue)) for i in range(CONCURRENCY)]
    await asyncio.gather(*workers)
    log("== smoke driver done ==")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
