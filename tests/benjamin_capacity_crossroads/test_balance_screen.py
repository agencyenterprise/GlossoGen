"""Manifest and dry-run tests for the bounded baseline screen."""

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from glossogen.scenarios.benjamin_capacity_crossroads.scripts.run_balance_screen import (
    BalanceScreenManifest,
    run_balance_stage,
)
from glossogen.scenarios.benjamin_release_pipeline.scripts.run_campaign import jobs_for_stage


def _manifest_payload() -> dict[str, object]:
    """Return one complete three-variant campaign manifest."""
    seeds = [775100, 775101, 775102, 775103]
    cells = [
        "balance_routine_delay",
        "balance_missed_window",
        "balance_service_interruption",
    ]
    configs = [
        {
            "stage": "balance",
            "cell_id": cell,
            "seed": seed,
            "path": f"configs/{cell}_{seed}.json",
        }
        for cell in cells
        for seed in seeds
    ]
    return {
        "experiment_id": "EXP-071",
        "scenario": "benjamin_capacity_crossroads",
        "seeds": seeds,
        "models": ["claude-sonnet-5", "claude-haiku-4-5-20251001"],
        "configs": configs,
        "stages": {
            "balance": {
                "cell_order": cells,
                "replicas_per_seed": 2,
                "seed_schedule": [],
            }
        },
    }


def test_manifest_expands_to_twenty_four_jobs_per_family() -> None:
    """Three variants times four positions times two replicas are immutable."""
    manifest = BalanceScreenManifest.model_validate(_manifest_payload())
    jobs = jobs_for_stage(
        manifest=manifest,
        stage_name="balance",
        repo_root=Path("/repo"),
    )
    assert len(jobs) == 24
    assert {job.cell_id for job in jobs} == set(manifest.stages["balance"].cell_order)
    assert {job.seed for job in jobs} == set(manifest.seeds)


def test_dry_run_dispatches_every_job_without_filesystem_outputs(tmp_path: Path) -> None:
    """Dry-run mode exercises the complete immutable dispatch plan."""
    manifest = BalanceScreenManifest.model_validate(_manifest_payload())
    jobs = jobs_for_stage(
        manifest=manifest,
        stage_name="balance",
        repo_root=tmp_path,
    )
    results = asyncio.run(
        run_balance_stage(
            jobs=jobs,
            runs_dir=tmp_path / "runs",
            model="claude-sonnet-5",
            provider="anthropic",
            max_agent_turns=8,
            max_concurrency=4,
            dry_run=True,
            experiment_id="EXP-071",
        )
    )
    assert len(results) == 24
    assert all(result.return_code == 0 for result in results)
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scenario", "benjamin_atomic_inventory"),
        ("seeds", [775100, 775101, 775102]),
        ("models", ["claude-sonnet-5"]),
    ],
)
def test_manifest_rejects_incomplete_design(field: str, value: object) -> None:
    """The launcher rejects drift from scenario, seed, or family scope."""
    payload = _manifest_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        BalanceScreenManifest.model_validate(payload)
