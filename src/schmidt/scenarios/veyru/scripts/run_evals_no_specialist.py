"""Run evaluators on all no_specialist veyru runs at concurrency=3.

Scans runs/veyru/ for directories with the 'no_specialist' label. Skips runs
that already have any eval: label. Runs all evaluators except
field_observer_transparency. Evaluations are run as they complete; new runs
added by the sim driver will be picked up on subsequent script invocations.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

CONCURRENCY = 3
RUNS_DIR = Path("runs/veyru")
DRIVER_LOG = Path("runs/eval_no_specialist_driver.log")
STDOUT_LOG_DIR = Path("runs/_eval_no_specialist_stdouts")
STDOUT_LOG_DIR.mkdir(parents=True, exist_ok=True)

EVALUATORS = ",".join(
    [
        "content_filter_refusal",
        "language_emergence",
        "language_strangeness",
        "neologism",
        "round_ended_idle",
        "round_ended_timeout",
        "round_success",
        "shorthand_codes",
        "slang_emergence",
    ]
)


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with DRIVER_LOG.open("a") as f:
        f.write(line + "\n")


def find_pending_runs() -> list[Path]:
    pending: list[Path] = []
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        labels_path = run_dir / "labels.json"
        if not labels_path.exists():
            continue
        labels = json.loads(labels_path.read_text())
        if "no_specialist" not in labels:
            continue
        if any(label.startswith("eval:") for label in labels):
            continue
        pending.append(run_dir)
    return pending


async def eval_run(idx: int, run_dir: Path) -> None:
    stdout_log = STDOUT_LOG_DIR / f"eval_{idx:03d}_{run_dir.name}.log"
    cmd = (
        "VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate veyru "
        f"--run-dir {run_dir} "
        f"--evaluators {EVALUATORS} "
        "--model claude-sonnet-4-6 --provider anthropic"
    )
    log(f"START idx={idx:03d} run={run_dir.name} -> {stdout_log.name}")
    with stdout_log.open("w") as f:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=f, stderr=asyncio.subprocess.STDOUT
        )
        rc = await proc.wait()
    if rc != 0:
        log(f"FAIL  idx={idx:03d} run={run_dir.name} rc={rc}")
    else:
        log(f"DONE  idx={idx:03d} run={run_dir.name}")


async def worker(worker_id: int, queue: asyncio.Queue[tuple[int, Path]]) -> None:
    while True:
        try:
            idx, run_dir = queue.get_nowait()
        except asyncio.QueueEmpty:
            log(f"worker {worker_id} drained queue, exiting")
            return
        try:
            await eval_run(idx=idx, run_dir=run_dir)
        finally:
            queue.task_done()


async def main() -> None:
    pending = find_pending_runs()
    log(f"== eval driver start: {len(pending)} runs to evaluate, concurrency={CONCURRENCY} ==")
    queue: asyncio.Queue[tuple[int, Path]] = asyncio.Queue()
    for i, run_dir in enumerate(pending):
        queue.put_nowait((i, run_dir))
    workers = [asyncio.create_task(worker(worker_id=i, queue=queue)) for i in range(CONCURRENCY)]
    await asyncio.gather(*workers)
    log("== eval driver done ==")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
