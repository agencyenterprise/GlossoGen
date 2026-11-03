"""Reading a derived run's timeline parent back from its manifests.

Bundle import repopulates the runs index's ``source_run_scenario`` /
``source_run_dir_name`` from these, so a wrong answer here detaches an imported
run from its parent in the runs list.
"""

from pathlib import Path

from glossogen.run_derivation.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.run_derivation.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.run_lineage import TimelineParent, read_timeline_parent


def _write_replace_manifest(
    run_dir: Path, source_run_id: str, replaced_agent_id: str | None
) -> None:
    manifest = ReplaceManifest(
        source_run_id=source_run_id,
        source_run_dir=f"runs/{source_run_id}",
        round_start=3,
        rounds_after_swap=2,
        target_event_id="evt-boundary",
        replaced_agent_id=replaced_agent_id,
        replacement_model=None,
        replacement_provider=None,
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        replaced_at=1_700_000_600.0,
    )
    (run_dir / REPLACE_MANIFEST_FILENAME).write_text(manifest.model_dump_json())


def _write_cross_run_manifest(run_dir: Path, source_a_run_id: str, source_b_run_id: str) -> None:
    manifest = CrossRunReplaceManifest(
        source_a_run_id=source_a_run_id,
        source_a_run_dir=f"runs/{source_a_run_id}",
        source_b_run_id=source_b_run_id,
        source_b_run_dir=f"runs/{source_b_run_id}",
        imported_history_source="imported_history.jsonl",
        round_start=2,
        rounds_after_swap=1,
        target_event_id="evt-a",
        source_b_round_end=1,
        source_b_cutoff_event_id="evt-b",
        replaced_agent_id="first_agent",
        imported_model="claude-sonnet-4-6",
        imported_provider="anthropic",
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        replaced_at=1_700_000_600.0,
    )
    (run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME).write_text(manifest.model_dump_json())


def test_a_replace_agent_run_names_its_source_run(tmp_path: Path) -> None:
    _write_replace_manifest(
        run_dir=tmp_path, source_run_id="veyru/1700000000", replaced_agent_id="engineer"
    )

    assert read_timeline_parent(run_dir=tmp_path) == TimelineParent(
        scenario="veyru", run_dir_name="1700000000"
    )


def test_a_fork_at_round_run_names_its_source_run(tmp_path: Path) -> None:
    _write_replace_manifest(
        run_dir=tmp_path, source_run_id="veyru/1700000000_2", replaced_agent_id=None
    )

    assert read_timeline_parent(run_dir=tmp_path) == TimelineParent(
        scenario="veyru", run_dir_name="1700000000_2"
    )


def test_a_cross_run_replace_run_names_source_a_not_the_run_it_imported_from(
    tmp_path: Path,
) -> None:
    _write_cross_run_manifest(
        run_dir=tmp_path,
        source_a_run_id="veyru/1700000000",
        source_b_run_id="signal_game/1690000000",
    )

    assert read_timeline_parent(run_dir=tmp_path) == TimelineParent(
        scenario="veyru", run_dir_name="1700000000"
    )


def test_an_original_run_has_no_timeline_parent(tmp_path: Path) -> None:
    assert read_timeline_parent(run_dir=tmp_path) is None
