"""Launch the frozen capacity-crossroads baseline-balance screen."""

import argparse
import asyncio
import re
import shlex
import sys
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, model_validator

from glossogen.evaluation.log_reader import load_events
from glossogen.scenarios.benjamin_release_pipeline.scripts.run_campaign import (
    CampaignConfig,
    JobResult,
    RunJob,
    StagePlan,
    jobs_for_stage,
    validate_run_events,
)

SCENARIO_NAME = "benjamin_capacity_crossroads"
STAGE_NAME = "balance"


class BalanceScreenManifest(BaseModel):
    """Immutable three-variant baseline screen for two model families."""

    experiment_id: str
    scenario: str
    screen_version: Literal["temptation_sweep", "paired_revision"] = "temptation_sweep"
    seeds: list[int]
    models: list[str]
    configs: list[CampaignConfig]
    stages: dict[str, StagePlan]

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        """Require three cells, four order seeds, and two replicas per seed."""
        if re.fullmatch(r"EXP-\d{3}", self.experiment_id) is None:
            raise ValueError("campaign manifest must identify one EXP-NNN record")
        if self.scenario != SCENARIO_NAME:
            raise ValueError(f"campaign scenario must be {SCENARIO_NAME}")
        if len(self.seeds) != 4 or len(set(self.seeds)) != 4:
            raise ValueError("balance screen must use four distinct order seeds")
        expected_models = {
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
        }
        if set(self.models) != expected_models:
            raise ValueError("balance screen must include Sonnet 5 and Haiku 4.5")
        if set(self.stages) != {STAGE_NAME}:
            raise ValueError("balance screen manifest must contain only balance")
        stage = self.stages[STAGE_NAME]
        if self.screen_version == "paired_revision":
            expected_cells = {"balance_paired_matched_priority"}
        else:
            expected_cells = {
                "balance_routine_delay",
                "balance_missed_window",
                "balance_service_interruption",
            }
        if set(stage.cell_order) != expected_cells:
            raise ValueError("balance screen must contain all three temptation cells")
        if stage.replicas_per_seed != 2 or stage.seed_schedule:
            raise ValueError("balance screen must use two replicas for each order seed")
        config_keys = {(config.stage, config.cell_id, config.seed) for config in self.configs}
        if len(config_keys) != len(self.configs):
            raise ValueError("campaign config assignments must be unique")
        for cell_id in stage.cell_order:
            for seed in self.seeds:
                if (STAGE_NAME, cell_id, seed) not in config_keys:
                    raise ValueError(f"missing balance config for cell={cell_id}, seed={seed}")
        return self


def load_balance_manifest(path: Path) -> BalanceScreenManifest:
    """Read and validate the immutable balance-screen manifest."""
    return BalanceScreenManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _parse_args() -> argparse.Namespace:
    """Parse one family-specific balance-screen invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--provider", type=str, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--max-concurrency", type=int, required=True)
    parser.add_argument("--max-agent-turns", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _run_root(job: RunJob, runs_dir: Path, model: str, experiment_id: str) -> Path:
    """Return the isolated output root for one trajectory."""
    return (
        runs_dir
        / "covenant-game"
        / experiment_id
        / model
        / job.stage
        / job.cell_id
        / f"seed-{job.seed}"
        / f"replica-{job.replica_index:02d}"
    )


def _simulation_command(
    job: RunJob,
    output_root: Path,
    model: str,
    provider: str,
    max_agent_turns: int,
) -> list[str]:
    """Build one secret-free simulation command."""
    return [
        sys.executable,
        "-m",
        "glossogen",
        "run",
        SCENARIO_NAME,
        "--model",
        model,
        "--provider",
        provider,
        "--runs-dir",
        str(output_root),
        "--config",
        str(job.config_path),
        "--max-agent-turns",
        str(max_agent_turns),
    ]


def publish_frontend_link(
    run_dir: Path,
    runs_dir: Path,
    job: RunJob,
    model: str,
    experiment_id: str,
) -> Path:
    """Expose one nested run in the frontend as soon as its directory exists."""
    scenario_root = runs_dir / SCENARIO_NAME
    scenario_root.mkdir(parents=True, exist_ok=True)
    safe_model = model.replace("/", "--")
    link_name = (
        f"{run_dir.name}_{experiment_id}__{safe_model}__{job.stage}__{job.cell_id}__"
        f"seed-{job.seed}__replica-{job.replica_index:02d}"
    )
    link_path = scenario_root / link_name
    if link_path.is_symlink() and link_path.resolve() == run_dir.resolve():
        return link_path
    if link_path.exists() or link_path.is_symlink():
        raise ValueError(f"frontend run link already exists: {link_path}")
    link_path.symlink_to(run_dir.resolve(), target_is_directory=True)
    return link_path


async def _discover_and_publish(
    process: asyncio.subprocess.Process,
    output_root: Path,
    runs_dir: Path,
    job: RunJob,
    model: str,
    experiment_id: str,
) -> tuple[Path | None, Path | None]:
    """Publish a live link after the unique run directory appears."""
    scenario_root = output_root / SCENARIO_NAME
    while True:
        if scenario_root.is_dir():
            run_dirs = sorted(path for path in scenario_root.iterdir() if path.is_dir())
            if len(run_dirs) > 1:
                raise ValueError(
                    f"expected at most one run under {scenario_root}, found {len(run_dirs)}"
                )
            if len(run_dirs) == 1:
                run_dir = run_dirs[0]
                link_path = publish_frontend_link(
                    run_dir=run_dir,
                    runs_dir=runs_dir,
                    job=job,
                    model=model,
                    experiment_id=experiment_id,
                )
                return run_dir, link_path
        if process.returncode is not None:
            return None, None
        await asyncio.sleep(0.1)


async def _validate_run(run_dir: Path) -> tuple[bool, str]:
    """Require a normal end and one agent-completed mechanical endpoint."""
    log_path = run_dir / f"{SCENARIO_NAME}.jsonl"
    if not log_path.is_file():
        return False, f"missing event log: {log_path}"
    events = await load_events(log_path=log_path)
    validation = validate_run_events(events=events)
    return validation.valid, validation.reason


async def _run_job(
    job: RunJob,
    runs_dir: Path,
    model: str,
    provider: str,
    max_agent_turns: int,
    dry_run: bool,
    experiment_id: str,
) -> JobResult:
    """Launch, live-publish, and validate one baseline trajectory."""
    output_root = _run_root(
        job=job,
        runs_dir=runs_dir,
        model=model,
        experiment_id=experiment_id,
    )
    scenario_root = output_root / SCENARIO_NAME
    existing_run_dirs: list[Path] = []
    if scenario_root.is_dir():
        existing_run_dirs = sorted(
            path for path in scenario_root.iterdir() if path.is_dir()
        )
    valid_existing: list[Path] = []
    for existing_run_dir in existing_run_dirs:
        valid, _reason = await _validate_run(run_dir=existing_run_dir)
        if valid:
            valid_existing.append(existing_run_dir)
    if len(valid_existing) > 1:
        print(
            f"[{job.ordinal:03d}] multiple valid artifacts already exist under "
            f"{scenario_root}",
            flush=True,
        )
        return JobResult(job=job, return_code=6, run_dir=None)
    if len(valid_existing) == 1:
        run_dir = valid_existing[0]
        link_path = publish_frontend_link(
            run_dir=run_dir,
            runs_dir=runs_dir,
            job=job,
            model=model,
            experiment_id=experiment_id,
        )
        print(
            f"[{job.ordinal:03d}] valid-existing={run_dir} frontend={link_path}",
            flush=True,
        )
        return JobResult(job=job, return_code=0, run_dir=run_dir)
    command = _simulation_command(
        job=job,
        output_root=output_root,
        model=model,
        provider=provider,
        max_agent_turns=max_agent_turns,
    )
    print(f"[{job.ordinal:03d}] {shlex.join(command)}", flush=True)
    if dry_run:
        return JobResult(job=job, return_code=0, run_dir=None)
    process = await asyncio.create_subprocess_exec(*command)
    try:
        run_dir, link_path = await _discover_and_publish(
            process=process,
            output_root=output_root,
            runs_dir=runs_dir,
            job=job,
            model=model,
            experiment_id=experiment_id,
        )
    except ValueError as exc:
        print(f"[{job.ordinal:03d}] {exc}", flush=True)
        await process.wait()
        return JobResult(job=job, return_code=5, run_dir=None)
    if link_path is not None:
        print(f"[{job.ordinal:03d}] frontend-live={link_path}", flush=True)
    return_code = await process.wait()
    if run_dir is None:
        if return_code != 0:
            return JobResult(job=job, return_code=return_code, run_dir=None)
        return JobResult(job=job, return_code=2, run_dir=None)
    valid, reason = await _validate_run(run_dir=run_dir)
    if valid:
        if return_code != 0:
            print(
                f"[{job.ordinal:03d}] accepted valid artifact despite subprocess "
                f"teardown exit={return_code}",
                flush=True,
            )
        return JobResult(job=job, return_code=0, run_dir=run_dir)
    if not valid:
        print(f"[{job.ordinal:03d}] invalid run artifact: {reason}", flush=True)
        return JobResult(job=job, return_code=3, run_dir=run_dir)
    raise AssertionError("unreachable validation state")


async def run_balance_stage(
    jobs: list[RunJob],
    runs_dir: Path,
    model: str,
    provider: str,
    max_agent_turns: int,
    max_concurrency: int,
    dry_run: bool,
    experiment_id: str,
) -> list[JobResult]:
    """Run every frozen job unless an operational failure stops new dispatch."""
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least one")
    queue: asyncio.Queue[RunJob] = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)
    failures = asyncio.Event()
    results: list[JobResult] = []

    async def worker() -> None:
        """Run queued jobs until exhausted or another worker reports a failure."""
        while not queue.empty() and not failures.is_set():
            job = await queue.get()
            result = await _run_job(
                job=job,
                runs_dir=runs_dir,
                model=model,
                provider=provider,
                max_agent_turns=max_agent_turns,
                dry_run=dry_run,
                experiment_id=experiment_id,
            )
            results.append(result)
            queue.task_done()
            if result.return_code != 0:
                failures.set()

    worker_count = min(max_concurrency, len(jobs))
    await asyncio.gather(*(worker() for _ in range(worker_count)))
    return sorted(results, key=lambda result: result.job.ordinal)


async def _async_main(args: argparse.Namespace) -> int:
    """Validate and launch the complete baseline screen for one family."""
    repo_root = Path(__file__).resolve().parents[5]
    manifest = load_balance_manifest(path=args.manifest.resolve())
    if args.model not in manifest.models:
        raise ValueError(f"model is not preregistered in manifest: {args.model}")
    jobs = jobs_for_stage(manifest=manifest, stage_name=STAGE_NAME, repo_root=repo_root)
    results = await run_balance_stage(
        jobs=jobs,
        runs_dir=args.runs_dir.resolve(),
        model=args.model,
        provider=args.provider,
        max_agent_turns=args.max_agent_turns,
        max_concurrency=args.max_concurrency,
        dry_run=args.dry_run,
        experiment_id=manifest.experiment_id,
    )
    failures = [result for result in results if result.return_code != 0]
    print(
        f"stage={STAGE_NAME} planned={len(jobs)} completed={len(results)} "
        f"failures={len(failures)} dry_run={args.dry_run}",
        flush=True,
    )
    if failures:
        return 1
    if len(results) != len(jobs):
        return 2
    return 0


def main() -> int:
    """Run the baseline-balance screen."""
    return asyncio.run(_async_main(args=_parse_args()))


if __name__ == "__main__":
    sys.exit(main())
