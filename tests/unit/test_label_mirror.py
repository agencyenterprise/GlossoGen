"""The labels mirror: which copy a listing reads, and what healing would rewrite.

Disk is the source of truth and the ``runs`` row mirrors it. Pinned here without
a live database: a descriptor's mirrored labels answer without touching disk and
the file answers only when the row was never mirrored, and the healing planner
rewrites exactly the drifted rows. The repairs that write rows run against a stub
pool with ``update_run_labels`` replaced by a recorder, so they show which rows
each repair writes and that none of them raises; the SQL itself stays untested,
like the rest of ``queries.py``.
"""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple
from uuid import UUID, uuid4

import orjson
import pytest
from fastapi import Request

from glossogen.db.rows import RunRow
from glossogen.models.event import RunStatus
from glossogen.run_storage.run_discovery import ResolvedRun, RunDescriptor
from glossogen.run_storage.run_summary_models import RunSummary
from glossogen.server.identity.identity_model import Identity
from glossogen.server.runs import label_mirror
from glossogen.server.runs.label_mirror import (
    LabelMirrorUpdate,
    backfill_run_label_mirror,
    heal_label_mirror,
    heal_run_labels_after_read,
    plan_label_mirror_updates,
)
from glossogen.server.runs.listing import descriptor_labels
from tests.fakes.db_pool import CountingPool

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
        evaluation_scores=[],
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
        round_results=[],
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


def test_an_unmirrored_descriptor_whose_file_is_not_a_list_reads_as_unlabelled(
    tmp_path: Path,
) -> None:
    """A hand-edited ``labels.json`` holding an object never reaches a summary as labels."""
    run_dir = tmp_path / "veyru" / "100"
    run_dir.mkdir(parents=True)
    (run_dir / "labels.json").write_bytes(orjson.dumps({"labels": ["baseline_oss"]}))

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


# --- what the repairs write ---------------------------------------------------------


class LabelWrite(NamedTuple):
    """One ``update_run_labels`` call."""

    group_id: UUID
    scenario: str
    run_dir_name: str
    labels: list[str]


class RecordingLabelWrites:
    """Stands in for ``update_run_labels``; raises for runs named in ``failing``."""

    def __init__(self, failing: set[str]) -> None:
        self.failing = failing
        self.writes: list[LabelWrite] = []

    async def __call__(
        self,
        conn: object,  # noqa: ARG002 — signature-required
        group_id: UUID,
        scenario: str,
        run_dir_name: str,
        labels: list[str],
    ) -> None:
        if run_dir_name in self.failing:
            raise RuntimeError(f"connection lost writing {run_dir_name}")
        self.writes.append(
            LabelWrite(
                group_id=group_id, scenario=scenario, run_dir_name=run_dir_name, labels=labels
            )
        )


def record_label_writes(monkeypatch: pytest.MonkeyPatch, failing: set[str]) -> RecordingLabelWrites:
    recorder = RecordingLabelWrites(failing=failing)
    monkeypatch.setattr(target=label_mirror, name="update_run_labels", value=recorder)
    return recorder


def request_for_group(pool: CountingPool, group_id: UUID) -> Request:
    """A request whose app has ``pool`` and whose identity is in ``group_id``."""
    app = SimpleNamespace(state=SimpleNamespace(db_pool=pool.as_db_pool()))
    request = Request(scope={"type": "http", "method": "GET", "headers": [], "app": app})
    request.state.identity = Identity(
        user_id="researcher", active_group_id=group_id, is_local_mode=False
    )
    return request


def resolved(run_dir_name: str, db_labels: list[str] | None) -> ResolvedRun:
    return ResolvedRun(
        run_dir=Path("/runs/veyru") / run_dir_name, scenario_name="veyru", db_labels=db_labels
    )


async def test_healing_a_page_writes_only_the_drifted_rows_in_the_callers_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = record_label_writes(monkeypatch=monkeypatch, failing=set())
    group_id = uuid4()

    await heal_label_mirror(
        pool=CountingPool().as_db_pool(),
        group_id=group_id,
        descriptors=[
            descriptor(run_dir_name="100", labels=["baseline_oss"]),
            descriptor(run_dir_name="200", labels=["stale"]),
        ],
        summaries=[
            summary(run_dir_name="100", labels=["baseline_oss"]),
            summary(run_dir_name="200", labels=["fresh"]),
        ],
    )

    assert writes.writes == [
        LabelWrite(group_id=group_id, scenario="veyru", run_dir_name="200", labels=["fresh"])
    ]


async def test_healing_a_page_with_no_drift_takes_no_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_label_writes(monkeypatch=monkeypatch, failing=set())
    pool = CountingPool()

    await heal_label_mirror(
        pool=pool.as_db_pool(),
        group_id=uuid4(),
        descriptors=[descriptor(run_dir_name="100", labels=["baseline_oss"])],
        summaries=[summary(run_dir_name="100", labels=["baseline_oss"])],
    )

    assert pool.connections_taken == 0


async def test_a_failed_page_heal_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The listing that triggered the heal has its response already; a repair must not fail it."""
    record_label_writes(monkeypatch=monkeypatch, failing={"100"})

    await heal_label_mirror(
        pool=CountingPool().as_db_pool(),
        group_id=uuid4(),
        descriptors=[descriptor(run_dir_name="100", labels=None)],
        summaries=[summary(run_dir_name="100", labels=["baseline_oss"])],
    )

    assert "Failed to heal the run-labels mirror" in caplog.text


async def test_reading_one_run_repairs_a_never_mirrored_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = record_label_writes(monkeypatch=monkeypatch, failing=set())
    group_id = uuid4()

    await heal_run_labels_after_read(
        request=request_for_group(pool=CountingPool(), group_id=group_id),
        resolved=resolved(run_dir_name="100", db_labels=None),
        run_dir_name="100",
        disk_labels=[],
    )

    assert writes.writes == [
        LabelWrite(group_id=group_id, scenario="veyru", run_dir_name="100", labels=[])
    ]


async def test_reading_one_run_whose_row_matches_takes_no_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_label_writes(monkeypatch=monkeypatch, failing=set())
    pool = CountingPool()

    await heal_run_labels_after_read(
        request=request_for_group(pool=pool, group_id=uuid4()),
        resolved=resolved(run_dir_name="100", db_labels=["baseline_oss"]),
        run_dir_name="100",
        disk_labels=["baseline_oss"],
    )

    assert pool.connections_taken == 0


async def test_a_failed_single_run_heal_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    record_label_writes(monkeypatch=monkeypatch, failing={"100"})

    await heal_run_labels_after_read(
        request=request_for_group(pool=CountingPool(), group_id=uuid4()),
        resolved=resolved(run_dir_name="100", db_labels=["stale"]),
        run_dir_name="100",
        disk_labels=["baseline_oss"],
    )

    assert "Failed to heal the labels mirror for run veyru/100" in caplog.text


# --- the startup backfill -----------------------------------------------------------


def unmirrored_row(group_id: UUID, run_dir_name: str) -> RunRow:
    return RunRow(
        id=int(run_dir_name),
        group_id=group_id,
        scenario="veyru",
        run_dir_name=run_dir_name,
        status="completed",
        created_at=TIMESTAMP,
        created_by_user_id=None,
        source_run_scenario=None,
        source_run_dir_name=None,
        evaluation_content_hash=None,
        labels=None,
    )


def unmirrored_rows(monkeypatch: pytest.MonkeyPatch, rows: list[RunRow]) -> None:
    async def fake_list_runs_missing_labels(
        conn: object,  # noqa: ARG001 — signature-required
    ) -> list[RunRow]:
        return rows

    monkeypatch.setattr(
        target=label_mirror,
        name="list_runs_missing_labels",
        value=fake_list_runs_missing_labels,
    )


async def test_the_backfill_writes_each_row_in_its_own_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The backfill spans every group; a row written under another group's id is a no-op."""
    group_a = uuid4()
    group_b = uuid4()
    run_dir_with_labels(runs_dir=tmp_path, run_dir_name="100", labels=["baseline_oss"])
    run_dir_with_labels(runs_dir=tmp_path, run_dir_name="200", labels=["budget=800"])
    unmirrored_rows(
        monkeypatch=monkeypatch,
        rows=[
            unmirrored_row(group_id=group_a, run_dir_name="100"),
            unmirrored_row(group_id=group_b, run_dir_name="200"),
        ],
    )
    writes = record_label_writes(monkeypatch=monkeypatch, failing=set())

    await backfill_run_label_mirror(pool=CountingPool().as_db_pool(), runs_dir=tmp_path)

    assert writes.writes == [
        LabelWrite(group_id=group_a, scenario="veyru", run_dir_name="100", labels=["baseline_oss"]),
        LabelWrite(group_id=group_b, scenario="veyru", run_dir_name="200", labels=["budget=800"]),
    ]


async def test_the_backfill_writes_a_run_with_no_labels_file_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Left ``NULL``, the row would be rescanned on every boot."""
    group_id = uuid4()
    unmirrored_rows(
        monkeypatch=monkeypatch, rows=[unmirrored_row(group_id=group_id, run_dir_name="100")]
    )
    writes = record_label_writes(monkeypatch=monkeypatch, failing=set())

    await backfill_run_label_mirror(pool=CountingPool().as_db_pool(), runs_dir=tmp_path)

    assert writes.writes == [
        LabelWrite(group_id=group_id, scenario="veyru", run_dir_name="100", labels=[])
    ]


async def test_a_failed_backfill_chunk_does_not_stop_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    group_id = uuid4()
    monkeypatch.setattr(target=label_mirror, name="_BACKFILL_CHUNK_SIZE", value=1)
    unmirrored_rows(
        monkeypatch=monkeypatch,
        rows=[
            unmirrored_row(group_id=group_id, run_dir_name="100"),
            unmirrored_row(group_id=group_id, run_dir_name="200"),
        ],
    )
    writes = record_label_writes(monkeypatch=monkeypatch, failing={"100"})

    await backfill_run_label_mirror(pool=CountingPool().as_db_pool(), runs_dir=tmp_path)

    assert [write.run_dir_name for write in writes.writes] == ["200"]
    assert "Run-labels backfill chunk failed (1 rows starting at 0)" in caplog.text
