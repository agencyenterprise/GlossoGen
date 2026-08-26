"""Tests for the reusable atomic-inventory K2 campaign runner."""

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from glossogen.scenarios.benjamin_atomic_inventory.scripts.run_k2_campaign import (
    K2CampaignManifest,
    load_k2_manifest,
)
from glossogen.scenarios.benjamin_release_pipeline.scripts.run_campaign import jobs_for_stage


def _manifest() -> dict[str, object]:
    """Return a complete synthetic K2 manifest."""
    seeds = [765101, 765109, 765121]
    cells = ["k2_A_unspecified_observed", "k2_A_unspecified_unobserved"]
    configs = [
        {
            "stage": "k2",
            "cell_id": cell,
            "seed": seed,
            "path": f"configs/{cell}_{seed}.json",
        }
        for seed in seeds
        for cell in cells
    ]
    return {
        "experiment_id": "EXP-070",
        "scenario": "benjamin_atomic_inventory",
        "seeds": seeds,
        "models": ["claude-sonnet-5", "claude-haiku-4-5-20251001"],
        "configs": configs,
        "stages": {
            "k2": {
                "cell_order": cells,
                "replicas_per_seed": 0,
                "seed_schedule": seeds * 10,
            }
        },
    }


def test_manifest_expands_to_thirty_runs_per_cell(tmp_path: Path) -> None:
    """Freeze two interleaved cells with 30 trajectories each."""
    manifest_path = tmp_path / "campaign.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    manifest = load_k2_manifest(path=manifest_path)
    jobs = jobs_for_stage(manifest=manifest, stage_name="k2", repo_root=tmp_path)

    assert len(jobs) == 60
    assert [job.cell_id for job in jobs[::2]] == ["k2_A_unspecified_observed"] * 30
    assert [job.cell_id for job in jobs[1::2]] == ["k2_A_unspecified_unobserved"] * 30
    assert {job.seed for job in jobs} == {765101, 765109, 765121}


def test_manifest_rejects_underpowered_schedule() -> None:
    """K2 cannot silently launch fewer than 30 trajectories per cell."""
    manifest = _manifest()
    stages = manifest["stages"]
    assert isinstance(stages, dict)
    stage = cast(dict[str, object], stages["k2"])
    stage["seed_schedule"] = [765101] * 29
    with pytest.raises(ValidationError, match="exactly 30"):
        K2CampaignManifest.model_validate(manifest)
