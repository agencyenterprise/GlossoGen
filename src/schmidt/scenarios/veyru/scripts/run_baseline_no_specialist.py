"""Drive 50 baseline veyru sonnet-4.6 runs (10 configs x 5 reps) at concurrency=3.

After each sim finishes successfully, writes labels.json with the standard
baseline tags plus `no_specialist`, so the new batch is distinguishable from
the older baseline batch.
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import NamedTuple


class Job(NamedTuple):
    config: str
    budget: int
    pm: str
    pm_label: str
    rep: int


CONCURRENCY = 3
RUNS_DIR = Path("runs")
DRIVER_LOG = RUNS_DIR / "baseline_no_specialist_driver.log"
STDOUT_LOG_DIR = RUNS_DIR / "_no_specialist_stdouts"
STDOUT_LOG_DIR.mkdir(parents=True, exist_ok=True)

LABELS_BASE = ["baseline", "no_specialist", "sonnet-4.6", "single_team"]
BUDGETS = [150, 250, 450, 800, 2000]
PM_VARIANTS = [
    ("on", "postmortem=true", "knobs_baseline_budget_{budget}.json"),
    ("off", "postmortem=false", "knobs_baseline_no_postmortem_budget_{budget}.json"),
]
REPS = 5


def build_queue() -> list[Job]:
    queue: list[Job] = []
    for budget in BUDGETS:
        for pm_state, pm_label, cfg_template in PM_VARIANTS:
            cfg_file = f"src/schmidt/scenarios/veyru/{cfg_template.format(budget=budget)}"
            for rep in range(REPS):
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
        "VIRTUAL_ENV= uv run --no-sync python -m schmidt run veyru "
        "--model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs "
        f"--config {job.config}"
    )
    log(f"START idx={idx:03d} budget={job.budget} pm={job.pm} " f"rep={job.rep} -> {stdout_log}")
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
