"""Launch one frozen EXP-056 stage in an interleaved order."""

import argparse
import asyncio
import shlex
import sys
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator

from glossogen.scenarios.benjamin_stewardship.evaluation.metric_names import (
    BENJAMIN_VISIBILITY_PROBE_METRIC,
)


class CampaignConfig(BaseModel):
    """One immutable scenario config assigned to a cell and seed."""

    stage: str
    cell_id: str
    seed: int
    path: str


class StagePlan(BaseModel):
    """Frozen ordering and replication schedule for one launch stage."""

    cell_order: list[str]
    replicas_per_seed: int
    seed_schedule: list[int]

    @model_validator(mode="after")
    def validate_replication_mode(self) -> Self:
        """Require either balanced seed replication or an explicit seed schedule."""
        balanced = self.replicas_per_seed > 0
        scheduled = bool(self.seed_schedule)
        if balanced == scheduled:
            raise ValueError("a stage must set replicas_per_seed or seed_schedule, but not both")
        return self


class CampaignManifest(BaseModel):
    """Complete immutable launch matrix for EXP-056."""

    experiment_id: str
    scenario: str
    seeds: list[int]
    models: list[str]
    configs: list[CampaignConfig]
    stages: dict[str, StagePlan]

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        """Ensure every stage cell has exactly one config for each required seed."""
        if self.experiment_id != "EXP-056":
            raise ValueError("campaign manifest must identify EXP-056")
        if self.scenario != "benjamin_stewardship":
            raise ValueError("campaign scenario must be benjamin_stewardship")
        if len(self.seeds) != 3 or len(set(self.seeds)) != 3:
            raise ValueError("campaign must preregister exactly three distinct seeds")
        config_keys = {(config.stage, config.cell_id, config.seed) for config in self.configs}
        if len(config_keys) != len(self.configs):
            raise ValueError("campaign config assignments must be unique")
        for stage_name, stage in self.stages.items():
            required_seeds = set(self.seeds)
            if stage.seed_schedule:
                required_seeds = set(stage.seed_schedule)
                if not required_seeds <= set(self.seeds):
                    raise ValueError(f"stage {stage_name} uses an unregistered seed")
            for cell_id in stage.cell_order:
                for seed in required_seeds:
                    if (stage_name, cell_id, seed) not in config_keys:
                        raise ValueError(
                            f"missing config for stage={stage_name}, cell={cell_id}, seed={seed}"
                        )
        return self


class RunJob(BaseModel):
    """One independent simulation launch in the frozen order."""

    ordinal: int
    stage: str
    cell_id: str
    seed: int
    replica_index: int
    config_path: Path


class JobResult(BaseModel):
    """Exit status for one simulation and any required K1 evaluation."""

    job: RunJob
    return_code: int
    run_dir: Path | None


def _parse_args() -> argparse.Namespace:
    """Parse one bounded campaign-stage invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--stage", type=str, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--provider", type=str, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--max-concurrency", type=int, required=True)
    parser.add_argument("--max-agent-turns", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _load_manifest(path: Path) -> CampaignManifest:
    """Read and validate the immutable campaign manifest."""
    return CampaignManifest.model_validate_json(path.read_text(encoding="utf-8"))


def jobs_for_stage(
    manifest: CampaignManifest,
    stage_name: str,
    repo_root: Path,
) -> list[RunJob]:
    """Expand one stage into its exact interleaved run order."""
    if stage_name not in manifest.stages:
        raise ValueError(f"unknown campaign stage: {stage_name}")
    stage = manifest.stages[stage_name]
    by_key = {
        (config.cell_id, config.seed): repo_root / config.path
        for config in manifest.configs
        if config.stage == stage_name
    }
    coordinates: list[tuple[str, int, int]] = []
    if stage.seed_schedule:
        for replica_index, seed in enumerate(stage.seed_schedule, start=1):
            for cell_id in stage.cell_order:
                coordinates.append((cell_id, seed, replica_index))
    else:
        for replica_index in range(1, stage.replicas_per_seed + 1):
            for seed in manifest.seeds:
                for cell_id in stage.cell_order:
                    coordinates.append((cell_id, seed, replica_index))
    return [
        RunJob(
            ordinal=ordinal,
            stage=stage_name,
            cell_id=cell_id,
            seed=seed,
            replica_index=replica_index,
            config_path=by_key[(cell_id, seed)],
        )
        for ordinal, (cell_id, seed, replica_index) in enumerate(coordinates, start=1)
    ]


def _run_root(job: RunJob, runs_dir: Path, model: str) -> Path:
    """Return an isolated output root for one run trajectory."""
    return (
        runs_dir
        / "covenant-game"
        / "EXP-056"
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
    """Build the secret-free exact simulation subprocess command."""
    return [
        sys.executable,
        "-m",
        "glossogen",
        "run",
        "benjamin_stewardship",
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


def _evaluation_command(run_dir: Path, model: str, provider: str) -> list[str]:
    """Build the held-out K1 post-simulation evaluation command."""
    return [
        sys.executable,
        "-m",
        "glossogen",
        "evaluate",
        "benjamin_stewardship",
        "--run-dir",
        str(run_dir),
        "--metrics",
        BENJAMIN_VISIBILITY_PROBE_METRIC,
        "--model",
        model,
        "--provider",
        provider,
    ]


async def _run_job(
    job: RunJob,
    runs_dir: Path,
    model: str,
    provider: str,
    max_agent_turns: int,
    dry_run: bool,
) -> JobResult:
    """Launch one simulation and its K1 probe when applicable."""
    output_root = _run_root(job=job, runs_dir=runs_dir, model=model)
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
    return_code = await process.wait()
    if return_code != 0:
        return JobResult(job=job, return_code=return_code, run_dir=None)
    scenario_root = output_root / "benjamin_stewardship"
    run_dirs = sorted(path for path in scenario_root.iterdir() if path.is_dir())
    if len(run_dirs) != 1:
        print(
            f"[{job.ordinal:03d}] expected one run directory under {scenario_root}, "
            f"found {len(run_dirs)}",
            flush=True,
        )
        return JobResult(job=job, return_code=2, run_dir=None)
    run_dir = run_dirs[0]
    if job.stage != "k1":
        return JobResult(job=job, return_code=0, run_dir=run_dir)
    evaluation_command = _evaluation_command(
        run_dir=run_dir,
        model=model,
        provider=provider,
    )
    print(f"[{job.ordinal:03d}] {shlex.join(evaluation_command)}", flush=True)
    evaluation = await asyncio.create_subprocess_exec(*evaluation_command)
    evaluation_return_code = await evaluation.wait()
    return JobResult(
        job=job,
        return_code=evaluation_return_code,
        run_dir=run_dir,
    )


async def _run_stage(
    jobs: list[RunJob],
    runs_dir: Path,
    model: str,
    provider: str,
    max_agent_turns: int,
    max_concurrency: int,
    dry_run: bool,
) -> list[JobResult]:
    """Consume jobs in frozen order and stop dispatch after the first failure."""
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least one")
    queue: asyncio.Queue[RunJob] = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)
    failures = asyncio.Event()
    results: list[JobResult] = []

    async def worker() -> None:
        """Run queued jobs until exhausted or another worker reports failure."""
        while not queue.empty() and not failures.is_set():
            job = await queue.get()
            result = await _run_job(
                job=job,
                runs_dir=runs_dir,
                model=model,
                provider=provider,
                max_agent_turns=max_agent_turns,
                dry_run=dry_run,
            )
            results.append(result)
            queue.task_done()
            if result.return_code != 0:
                failures.set()

    worker_count = min(max_concurrency, len(jobs))
    await asyncio.gather(*(worker() for _ in range(worker_count)))
    return sorted(results, key=lambda result: result.job.ordinal)


async def _async_main(args: argparse.Namespace) -> int:
    """Validate the requested stage and return a process exit code."""
    repo_root = Path(__file__).resolve().parents[5]
    manifest = _load_manifest(path=args.manifest.resolve())
    if args.model not in manifest.models:
        raise ValueError(f"model is not preregistered in manifest: {args.model}")
    jobs = jobs_for_stage(
        manifest=manifest,
        stage_name=args.stage,
        repo_root=repo_root,
    )
    results = await _run_stage(
        jobs=jobs,
        runs_dir=args.runs_dir.resolve(),
        model=args.model,
        provider=args.provider,
        max_agent_turns=args.max_agent_turns,
        max_concurrency=args.max_concurrency,
        dry_run=args.dry_run,
    )
    failures = [result for result in results if result.return_code != 0]
    print(
        f"stage={args.stage} planned={len(jobs)} completed={len(results)} "
        f"failures={len(failures)} dry_run={args.dry_run}",
        flush=True,
    )
    if failures:
        return 1
    if len(results) != len(jobs):
        return 2
    return 0


def main() -> None:
    """Run the command-line campaign launcher."""
    args = _parse_args()
    raise SystemExit(asyncio.run(_async_main(args=args)))


if __name__ == "__main__":
    main()
