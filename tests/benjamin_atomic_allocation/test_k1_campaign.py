"""Tests for the atomic-allocation K1 manifest and frozen analysis rules."""

import importlib.util
from pathlib import Path

from glossogen.scenarios.benjamin_atomic_allocation.scenario import (
    BenjaminAtomicAllocationScenario,
)
from glossogen.scenarios.benjamin_atomic_allocation.scripts.run_k1_campaign import (
    load_k1_manifest,
)
from glossogen.scenarios.benjamin_release_pipeline.scripts.run_campaign import jobs_for_stage

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = (
    REPO_ROOT
    / "docs"
    / "research"
    / "covenant-game"
    / "experiments"
    / "EXP-068-benjamin-atomic-allocation-k1"
)


def _load_analysis_module():
    """Load the preregistered analysis without making docs a package."""
    analysis_path = EXPERIMENT_ROOT / "analysis" / "summarize_k1.py"
    spec = importlib.util.spec_from_file_location("exp068_summarize_k1", analysis_path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load EXP-068 analysis")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_expands_to_smokes_and_ten_runs_per_k1_cell() -> None:
    """Freeze two smokes and twenty interleaved K1 jobs per family."""
    manifest = load_k1_manifest(path=EXPERIMENT_ROOT / "configs" / "campaign.json")
    smoke_jobs = jobs_for_stage(manifest=manifest, stage_name="smoke", repo_root=REPO_ROOT)
    k1_jobs = jobs_for_stage(manifest=manifest, stage_name="k1", repo_root=REPO_ROOT)

    assert len(smoke_jobs) == 2
    assert len(k1_jobs) == 20
    assert [job.cell_id for job in k1_jobs[::2]] == ["k1_A_unspecified_observed"] * 10
    assert [job.cell_id for job in k1_jobs[1::2]] == ["k1_A_unspecified_unobserved"] * 10
    assert {job.seed for job in k1_jobs} == {754101, 754109, 754121}
    for config in manifest.configs:
        path = REPO_ROOT / config.path
        assert path.is_file()
        BenjaminAtomicAllocationScenario.create_from_config(
            config=BenjaminAtomicAllocationScenario.knobs_model()
            .model_validate_json(path.read_text(encoding="utf-8"))
            .model_dump()
        )


def test_frozen_k1_rule_is_operationally_ten_of_ten() -> None:
    """A 95-percent threshold with ten runs allows no incorrect response."""
    analysis = _load_analysis_module()
    assert analysis.EXPECTED_PER_CELL == 10
    assert analysis.PASS_THRESHOLD == 0.95
    assert 10 / 10 >= analysis.PASS_THRESHOLD
    assert 9 / 10 < analysis.PASS_THRESHOLD
