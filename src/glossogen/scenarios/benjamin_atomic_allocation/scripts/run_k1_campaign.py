"""Launch the frozen atomic-allocation K1 campaign with live publication."""

import argparse
import asyncio
import re
import shlex
import sys
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator

from glossogen.evaluation.log_reader import load_events
from glossogen.evaluation.reports.evaluation_report import EvaluationReport
from glossogen.scenarios.benjamin_atomic_allocation.evaluation.metric_names import (
    BENJAMIN_ATOMIC_ALLOCATION_OBSERVABILITY_PROBE,
)
from glossogen.scenarios.benjamin_atomic_allocation.evaluation.observability_probe_metric import (
    RESPONSES_FILE_NAME,
    USAGE_FILE_NAME,
)
from glossogen.scenarios.benjamin_release_pipeline.scripts.run_campaign import (
    CampaignConfig,
    JobResult,
    RunArtifactValidation,
    RunJob,
    StagePlan,
    jobs_for_stage,
    validate_run_events,
)

SCENARIO_NAME = "benjamin_atomic_allocation"


class K1CampaignManifest(BaseModel):
    """Immutable smoke and K1 matrix for one atomic-allocation calibration."""

    experiment_id: str
    scenario: str
    seeds: list[int]
    models: list[str]
    configs: list[CampaignConfig]
    stages: dict[str, StagePlan]

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        """Require the new scenario and complete cell-by-seed assignments."""
        if re.fullmatch(r"EXP-\d{3}", self.experiment_id) is None:
            raise ValueError("campaign manifest must identify one EXP-NNN record")
        if self.scenario != SCENARIO_NAME:
            raise ValueError(f"campaign scenario must be {SCENARIO_NAME}")
        if len(self.seeds) != 3 or len(set(self.seeds)) != 3:
            raise ValueError("campaign must preregister exactly three distinct seeds")
        expected_models = {
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
        }
        if set(self.models) != expected_models:
            raise ValueError("K1 must preregister Sonnet 5 and Haiku 4.5")
        if set(self.stages) != {"smoke", "k1"}:
            raise ValueError("K1 manifest must contain smoke and k1 stages")
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


def validate_k1_evaluation_artifact(run_dir: Path) -> RunArtifactValidation:
    """Require both probe sidecars and exactly one frozen K1 measurement."""
    missing = [
        file_name
        for file_name in (RESPONSES_FILE_NAME, USAGE_FILE_NAME)
        if not (run_dir / file_name).is_file()
    ]
    report_path = run_dir / f"{SCENARIO_NAME}_report.json"
    if not report_path.is_file():
        missing.append(report_path.name)
    if missing:
        return RunArtifactValidation(
            valid=False,
            reason=f"K1 evaluation missing artifacts: {', '.join(missing)}",
        )
    report = EvaluationReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    measurements = [
        measurement
        for measurement in report.measurements
        if measurement.metric_name == BENJAMIN_ATOMIC_ALLOCATION_OBSERVABILITY_PROBE
    ]
    if len(measurements) != 1:
        return RunArtifactValidation(
            valid=False,
            reason=f"expected one K1 measurement, found {len(measurements)}",
        )
    return RunArtifactValidation(valid=True, reason="valid K1 evaluation artifacts")


def k1_score(run_dir: Path) -> float:
    """Read the single frozen K1 score from a validated report."""
    report_path = run_dir / f"{SCENARIO_NAME}_report.json"
    report = EvaluationReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    measurements = [
        measurement
        for measurement in report.measurements
        if measurement.metric_name == BENJAMIN_ATOMIC_ALLOCATION_OBSERVABILITY_PROBE
    ]
    if len(measurements) != 1:
        raise ValueError(f"expected one K1 measurement in {report_path}")
    return measurements[0].score


async def validate_run_artifact(run_dir: Path) -> RunArtifactValidation:
    """Validate one atomic-allocation run from its typed JSONL events."""
    log_path = run_dir / f"{SCENARIO_NAME}.jsonl"
    if not log_path.is_file():
        return RunArtifactValidation(valid=False, reason=f"missing event log: {log_path}")
    events = await load_events(log_path=log_path)
    return validate_run_events(events=events)


def publish_frontend_link(
    run_dir: Path,
    runs_dir: Path,
    job: RunJob,
    model: str,
    experiment_id: str,
) -> Path:
    """Expose a nested run to the frontend before the trajectory completes."""
    scenario_root = runs_dir / SCENARIO_NAME
    scenario_root.mkdir(parents=True, exist_ok=True)
    safe_model = model.replace("/", "--")
    link_name = (
        f"{run_dir.name}_{experiment_id}__{safe_model}__{job.stage}__{job.cell_id}__"
        f"seed-{job.seed}__replica-{job.replica_index:02d}"
    )
    link_path = scenario_root / link_name
    if link_path.exists() or link_path.is_symlink():
        raise ValueError(f"frontend run link already exists: {link_path}")
    link_path.symlink_to(run_dir.resolve(), target_is_directory=True)
    return link_path


def _parse_args() -> argparse.Namespace:
    """Parse one bounded campaign-stage invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--stage", choices=("smoke", "k1"), required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--provider", type=str, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--max-concurrency", type=int, required=True)
    parser.add_argument("--max-agent-turns", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_k1_manifest(path: Path) -> K1CampaignManifest:
    """Read and validate the immutable campaign manifest."""
    return K1CampaignManifest.model_validate_json(path.read_text(encoding="utf-8"))


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
    """Build the secret-free simulation subprocess command."""
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


def _evaluation_command(run_dir: Path, model: str, provider: str) -> list[str]:
    """Build the held-out K1 evaluation command."""
    return [
        sys.executable,
        "-m",
        "glossogen",
        "evaluate",
        SCENARIO_NAME,
        "--run-dir",
        str(run_dir),
        "--metrics",
        BENJAMIN_ATOMIC_ALLOCATION_OBSERVABILITY_PROBE,
        "--model",
        model,
        "--provider",
        provider,
    ]


async def _discover_and_publish_live_link(
    process: asyncio.subprocess.Process,
    output_root: Path,
    runs_dir: Path,
    job: RunJob,
    model: str,
    experiment_id: str,
) -> tuple[Path | None, Path | None]:
    """Publish the frontend symlink immediately after the run directory appears."""
    scenario_root = output_root / SCENARIO_NAME
    while True:
        if scenario_root.is_dir():
            run_dirs = sorted(path for path in scenario_root.iterdir() if path.is_dir())
            if len(run_dirs) > 1:
                raise ValueError(
                    f"expected at most one run directory under {scenario_root}, "
                    f"found {len(run_dirs)}"
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


async def _run_job(
    job: RunJob,
    runs_dir: Path,
    model: str,
    provider: str,
    max_agent_turns: int,
    dry_run: bool,
    experiment_id: str,
) -> JobResult:
    """Launch one run, publish it live, and evaluate K1 after completion."""
    output_root = _run_root(
        job=job,
        runs_dir=runs_dir,
        model=model,
        experiment_id=experiment_id,
    )
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
        run_dir, visible_path = await _discover_and_publish_live_link(
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
    if visible_path is not None:
        print(f"[{job.ordinal:03d}] frontend-live={visible_path}", flush=True)
    return_code = await process.wait()
    if return_code != 0:
        return JobResult(job=job, return_code=return_code, run_dir=run_dir)
    if run_dir is None:
        return JobResult(job=job, return_code=2, run_dir=None)
    validation = await validate_run_artifact(run_dir=run_dir)
    if not validation.valid:
        print(f"[{job.ordinal:03d}] invalid run artifact: {validation.reason}", flush=True)
        return JobResult(job=job, return_code=3, run_dir=run_dir)
    if job.stage != "k1":
        return JobResult(job=job, return_code=0, run_dir=run_dir)
    evaluation_command = _evaluation_command(run_dir=run_dir, model=model, provider=provider)
    print(f"[{job.ordinal:03d}] {shlex.join(evaluation_command)}", flush=True)
    evaluation = await asyncio.create_subprocess_exec(*evaluation_command)
    evaluation_return_code = await evaluation.wait()
    if evaluation_return_code != 0:
        return JobResult(job=job, return_code=evaluation_return_code, run_dir=run_dir)
    evaluation_validation = validate_k1_evaluation_artifact(run_dir=run_dir)
    if not evaluation_validation.valid:
        print(
            f"[{job.ordinal:03d}] invalid K1 evaluation: {evaluation_validation.reason}",
            flush=True,
        )
        return JobResult(job=job, return_code=4, run_dir=run_dir)
    score = k1_score(run_dir=run_dir)
    print(f"[{job.ordinal:03d}] frozen-k1-score={score:.0f}", flush=True)
    if score != 1.0:
        print(
            f"[{job.ordinal:03d}] K1 gate irreversibly failed; stopping new dispatch",
            flush=True,
        )
        return JobResult(job=job, return_code=5, run_dir=run_dir)
    return JobResult(job=job, return_code=0, run_dir=run_dir)


async def run_campaign_stage(
    jobs: list[RunJob],
    runs_dir: Path,
    model: str,
    provider: str,
    max_agent_turns: int,
    max_concurrency: int,
    dry_run: bool,
    experiment_id: str,
) -> list[JobResult]:
    """Stop dispatch after an operational failure or first frozen K1 error."""
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
    """Validate and launch the requested calibration stage."""
    repo_root = Path(__file__).resolve().parents[5]
    manifest = load_k1_manifest(path=args.manifest.resolve())
    if args.model not in manifest.models:
        raise ValueError(f"model is not preregistered in manifest: {args.model}")
    jobs = jobs_for_stage(manifest=manifest, stage_name=args.stage, repo_root=repo_root)
    results = await run_campaign_stage(
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
        f"stage={args.stage} planned={len(jobs)} completed={len(results)} "
        f"failures={len(failures)} dry_run={args.dry_run}",
        flush=True,
    )
    if failures:
        return 1
    if len(results) != len(jobs):
        return 2
    return 0


def main() -> int:
    """Run the requested K1 campaign stage."""
    return asyncio.run(_async_main(args=_parse_args()))


if __name__ == "__main__":
    sys.exit(main())
