"""Tests for the destination-release K2 campaign and analysis rules."""

import importlib.util
from pathlib import Path

import pytest

from glossogen.scenarios.benjamin_destination_release.scripts.run_k2_campaign import (
    load_k2_manifest,
)
from glossogen.scenarios.benjamin_release_pipeline.scripts.run_campaign import jobs_for_stage

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = (
    REPO_ROOT
    / "docs"
    / "research"
    / "covenant-game"
    / "experiments"
    / "EXP-061-benjamin-k2-sensitivity"
)


def _load_analysis_module():
    """Load the preregistered analysis without making docs a package."""
    analysis_path = EXPERIMENT_ROOT / "analysis" / "summarize_k2.py"
    spec = importlib.util.spec_from_file_location("exp061_summarize_k2", analysis_path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load EXP-061 analysis")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_expands_to_thirty_matched_pairs() -> None:
    """Freeze 30 observed and 30 unobserved jobs in alternating order."""
    manifest = load_k2_manifest(path=EXPERIMENT_ROOT / "configs" / "campaign.json")
    jobs = jobs_for_stage(manifest=manifest, stage_name="k2", repo_root=REPO_ROOT)
    assert len(jobs) == 60
    assert [job.cell_id for job in jobs[::2]] == ["k2_A_named_observed"] * 30
    assert [job.cell_id for job in jobs[1::2]] == ["k2_A_named_unobserved"] * 30
    assert {job.seed for job in jobs} == {171161, 196613, 221729}


@pytest.mark.parametrize(
    ("observed_successes", "unobserved_successes", "expected"),
    [(30, 9, True), (27, 15, True), (21, 15, False), (15, 15, False)],
)
def test_frozen_k2_rule_requires_a_large_exact_difference(
    observed_successes: int,
    unobserved_successes: int,
    expected: bool,
) -> None:
    """Check representative passing and failing sensitivity tables."""
    analysis = _load_analysis_module()
    observed_rate = observed_successes / 30
    unobserved_rate = unobserved_successes / 30
    gap = observed_rate - unobserved_rate
    p_value = analysis.one_sided_fisher_greater(
        observed_successes=observed_successes,
        observed_total=30,
        unobserved_successes=unobserved_successes,
        unobserved_total=30,
    )
    passed = (
        analysis.HEADROOM_MIN <= unobserved_rate <= analysis.HEADROOM_MAX
        and gap >= analysis.MIN_OBSERVATION_GAP
        and p_value <= analysis.MAX_ONE_SIDED_P
    )
    assert passed is expected
