"""The labels mirror: which copy a listing reads, and what healing would rewrite.

Disk is the source of truth and the ``runs`` row mirrors it. Pinned here without
a live database: a descriptor's mirrored labels answer without touching disk and
the file answers only when the row was never mirrored, and the healing planner
rewrites exactly the drifted rows. The DB shells around these stay untested,
like the rest of ``queries.py``.
"""

from datetime import UTC, datetime
from pathlib import Path

import orjson

from glossogen.models.event import RunStatus
from glossogen.server.runs.discovery import RunDescriptor
from glossogen.server.runs.label_mirror import (
    LabelMirrorUpdate,
    plan_label_mirror_updates,
)
from glossogen.server.runs.listing import descriptor_labels
from glossogen.server.runs.models import RunSummary

TIMESTAMP = datetime(2026, 8, 25, tzinfo=UTC)


def descriptor(run_dir_name: str, labels: list[str] | None) -> RunDescriptor:
    """A veyru run's descriptor carrying the row's mirrored labels."""
    return RunDescriptor(
        scenario_name="veyru",
        run_dir_name=run_dir_name,
        timestamp=TIMESTAMP,
        evaluation_content_hash=None,
        labels=labels,
    )


def summary(run_dir_name: str, labels: list[str]) -> RunSummary:
    """A veyru run's summary carrying what labels.json holds."""
    return RunSummary(
        run_id=f"veyru/{run_dir_name}",
        scenario_name="veyru",
        scenario_description="",
        scenario_config={},
        timestamp=TIMESTAMP,
        total_messages=0,
        total_cost_usd=0.0,
        duration_seconds=0.0,
        status=RunStatus.SCENARIO_COMPLETE,
        has_evaluation=False,
        evaluation_in_progress=False,
        run_dir=f"/runs/veyru/{run_dir_name}",
        fork_source=None,
        replace_agent_source=None,
        cross_run_replace_agent_source=None,
        fork_at_round_source=None,
        models=[],
        provider="anthropic",
        agent_models=[],
        labels=labels,
        has_note=False,
        current_round=0,
        evaluation_content_hash=None,
    )


def run_dir_with_labels(runs_dir: Path, run_dir_name: str, labels: list[str]) -> None:
    """Write a run dir holding only a labels.json."""
    run_dir = runs_dir / "veyru" / run_dir_name
    run_dir.mkdir(parents=True)
    (run_dir / "labels.json").write_bytes(orjson.dumps(labels))


# --- which copy a listing reads ---------------------------------------------------


def test_a_mirrored_descriptor_answers_without_the_file(tmp_path: Path) -> None:
    """The file on disk disagrees on purpose: the mirror must be what answered."""
    run_dir_with_labels(runs_dir=tmp_path, run_dir_name="100", labels=["something_else"])

    labels = descriptor_labels(
        descriptor=descriptor(run_dir_name="100", labels=["baseline_oss"]),
        runs_dir=tmp_path,
    )

    assert labels == ["baseline_oss"]


def test_a_mirrored_empty_list_is_an_answer_not_a_fallback(tmp_path: Path) -> None:
    """``[]`` means the run is known to have no labels, even when the file has some."""
    run_dir_with_labels(runs_dir=tmp_path, run_dir_name="100", labels=["baseline_oss"])

    labels = descriptor_labels(
        descriptor=descriptor(run_dir_name="100", labels=[]),
        runs_dir=tmp_path,
    )

    assert labels == []


def test_an_unmirrored_descriptor_falls_back_to_the_file(tmp_path: Path) -> None:
    run_dir_with_labels(runs_dir=tmp_path, run_dir_name="100", labels=["baseline_oss"])

    labels = descriptor_labels(
        descriptor=descriptor(run_dir_name="100", labels=None),
        runs_dir=tmp_path,
    )

    assert labels == ["baseline_oss"]


def test_an_unmirrored_descriptor_with_no_file_reads_as_unlabelled(tmp_path: Path) -> None:
    labels = descriptor_labels(
        descriptor=descriptor(run_dir_name="100", labels=None),
        runs_dir=tmp_path,
    )

    assert labels == []


# --- what healing would rewrite ---------------------------------------------------


def test_a_row_matching_its_file_plans_nothing() -> None:
    updates = plan_label_mirror_updates(
        descriptors=[descriptor(run_dir_name="100", labels=["baseline_oss"])],
        summaries=[summary(run_dir_name="100", labels=["baseline_oss"])],
    )

    assert updates == []


def test_a_drifted_row_is_rewritten_to_what_the_file_says() -> None:
    updates = plan_label_mirror_updates(
        descriptors=[descriptor(run_dir_name="100", labels=["stale"])],
        summaries=[summary(run_dir_name="100", labels=["baseline_oss", "budget=800"])],
    )

    assert updates == [
        LabelMirrorUpdate(
            scenario_name="veyru",
            run_dir_name="100",
            labels=["baseline_oss", "budget=800"],
        )
    ]


def test_a_never_mirrored_row_is_seeded_even_when_unlabelled() -> None:
    updates = plan_label_mirror_updates(
        descriptors=[descriptor(run_dir_name="100", labels=None)],
        summaries=[summary(run_dir_name="100", labels=[])],
    )

    assert updates == [LabelMirrorUpdate(scenario_name="veyru", run_dir_name="100", labels=[])]


def test_a_summary_with_no_descriptor_plans_nothing() -> None:
    """A run enriched from a filesystem walk, or deleted mid-request, has no row to fix."""
    updates = plan_label_mirror_updates(
        descriptors=[],
        summaries=[summary(run_dir_name="100", labels=["baseline_oss"])],
    )

    assert updates == []
