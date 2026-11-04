"""The branches view: which runs it lists as sources, and how many children each has.

Without a database the sources come from each run's manifests on disk; with one,
from an aggregate over the ``runs`` table, which is replaced here by a fake that
returns rows. Either way a source is listed only when its own directory still
holds a readable run.
"""

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from glossogen.db.rows import DerivedSourceCountRow
from glossogen.run_derivation.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.run_derivation.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.server.runs import branch_sources
from glossogen.server.runs.branch_sources import list_branch_sources
from tests.fakes.db_pool import CountingPool
from tests.fakes.local_app import (
    GROUP_API,
    build_local_app,
    local_client,
    one_round_run_events,
    write_event_log,
)

SCENARIO = "veyru"


def write_run(runs_dir: Path, run_dir_name: str) -> Path:
    """A finished one-round veyru run."""
    return write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name=run_dir_name,
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name=run_dir_name, finished=True
        ),
        extra_records=[],
    )


def write_replace_child(
    runs_dir: Path, run_dir_name: str, source_run_dir_name: str, replaced_agent_id: str | None
) -> None:
    """A run derived from ``source_run_dir_name``.

    ``replaced_agent_id`` set makes it a replace-agent run; ``None`` makes it a
    fork-at-round run. Both name their parent the same way.
    """
    run_dir = write_run(runs_dir=runs_dir, run_dir_name=run_dir_name)
    replacement_model = None
    replacement_provider = None
    if replaced_agent_id is not None:
        replacement_model = "claude-haiku-4-5-20251001"
        replacement_provider = "anthropic"
    manifest = ReplaceManifest(
        source_run_id=f"{SCENARIO}/{source_run_dir_name}",
        source_run_dir=f"runs/{SCENARIO}/{source_run_dir_name}",
        round_start=1,
        rounds_after_swap=1,
        target_event_id="evt-boundary",
        replaced_agent_id=replaced_agent_id,
        replacement_model=replacement_model,
        replacement_provider=replacement_provider,
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        replaced_at=1_770_000_000.0,
    )
    (run_dir / REPLACE_MANIFEST_FILENAME).write_text(manifest.model_dump_json())


def write_cross_run_child(
    runs_dir: Path, run_dir_name: str, source_a_dir_name: str, source_b_dir_name: str
) -> None:
    """A cross-run replace-agent run continuing A's timeline with B's agent."""
    run_dir = write_run(runs_dir=runs_dir, run_dir_name=run_dir_name)
    manifest = CrossRunReplaceManifest(
        source_a_run_id=f"{SCENARIO}/{source_a_dir_name}",
        source_a_run_dir=f"runs/{SCENARIO}/{source_a_dir_name}",
        source_b_run_id=f"{SCENARIO}/{source_b_dir_name}",
        source_b_run_dir=f"runs/{SCENARIO}/{source_b_dir_name}",
        imported_history_source="imported_history.jsonl",
        round_start=1,
        rounds_after_swap=1,
        target_event_id="evt-a",
        source_b_round_end=1,
        source_b_cutoff_event_id="evt-b",
        replaced_agent_id="field_observer",
        imported_model="claude-haiku-4-5-20251001",
        imported_provider="anthropic",
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        replaced_at=1_770_000_000.0,
    )
    (run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME).write_text(manifest.model_dump_json())


async def branches_over_http(runs_dir: Path) -> dict[str, int]:
    """``GET /branches`` on a database-less app, as ``{source run id: derived count}``.

    A dict keeps insertion order, so comparing ``list(...)`` checks the order too.
    """
    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.get(f"{GROUP_API}/branches")
    assert response.status_code == 200, response.text
    return {
        source["source_run"]["run_id"]: source["derived_count"]
        for source in response.json()["sources"]
    }


# --- without a database ---------------------------------------------------------


async def test_every_kind_of_derivation_counts_toward_its_parent(tmp_path: Path) -> None:
    write_run(runs_dir=tmp_path, run_dir_name="1770000100")
    write_replace_child(
        runs_dir=tmp_path,
        run_dir_name="1770000200",
        source_run_dir_name="1770000100",
        replaced_agent_id="field_observer",
    )
    write_replace_child(
        runs_dir=tmp_path,
        run_dir_name="1770000300",
        source_run_dir_name="1770000100",
        replaced_agent_id=None,
    )
    write_cross_run_child(
        runs_dir=tmp_path,
        run_dir_name="1770000400",
        source_a_dir_name="1770000100",
        source_b_dir_name="1770000050",
    )
    write_run(runs_dir=tmp_path, run_dir_name="1770000050")

    assert await branches_over_http(runs_dir=tmp_path) == {f"{SCENARIO}/1770000100": 3}


async def test_a_cross_run_child_counts_toward_source_a_only(tmp_path: Path) -> None:
    """Source B lent an agent, not a timeline: it is not a branch point."""
    write_run(runs_dir=tmp_path, run_dir_name="1770000100")
    write_run(runs_dir=tmp_path, run_dir_name="1770000150")
    write_cross_run_child(
        runs_dir=tmp_path,
        run_dir_name="1770000200",
        source_a_dir_name="1770000100",
        source_b_dir_name="1770000150",
    )

    assert await branches_over_http(runs_dir=tmp_path) == {f"{SCENARIO}/1770000100": 1}


async def test_sources_are_listed_newest_parent_first(tmp_path: Path) -> None:
    for parent, child in [("1770000100", "1770000900"), ("1770000500", "1770000600")]:
        write_run(runs_dir=tmp_path, run_dir_name=parent)
        write_replace_child(
            runs_dir=tmp_path,
            run_dir_name=child,
            source_run_dir_name=parent,
            replaced_agent_id="field_observer",
        )

    branches = await branches_over_http(runs_dir=tmp_path)

    assert list(branches) == [f"{SCENARIO}/1770000500", f"{SCENARIO}/1770000100"]


async def test_children_of_a_deleted_parent_list_no_source(tmp_path: Path) -> None:
    write_replace_child(
        runs_dir=tmp_path,
        run_dir_name="1770000200",
        source_run_dir_name="1770000100",
        replaced_agent_id="field_observer",
    )

    assert await branches_over_http(runs_dir=tmp_path) == {}


async def test_a_derived_run_is_itself_a_source_when_derived_from(tmp_path: Path) -> None:
    """Grandchildren count toward their own parent, not the root."""
    write_run(runs_dir=tmp_path, run_dir_name="1770000100")
    write_replace_child(
        runs_dir=tmp_path,
        run_dir_name="1770000200",
        source_run_dir_name="1770000100",
        replaced_agent_id=None,
    )
    write_replace_child(
        runs_dir=tmp_path,
        run_dir_name="1770000300",
        source_run_dir_name="1770000200",
        replaced_agent_id=None,
    )

    assert await branches_over_http(runs_dir=tmp_path) == {
        f"{SCENARIO}/1770000200": 1,
        f"{SCENARIO}/1770000100": 1,
    }


# --- with a database ------------------------------------------------------------


class FakeSourceCounts:
    """Stands in for ``list_derived_source_counts``: returns ``rows`` and records the group."""

    def __init__(self, rows: list[DerivedSourceCountRow]) -> None:
        self.rows = rows
        self.groups_asked: list[UUID] = []

    async def __call__(
        self,
        conn: object,  # noqa: ARG002 — signature-required
        group_id: UUID,
    ) -> list[DerivedSourceCountRow]:
        self.groups_asked.append(group_id)
        return self.rows


def use_source_counts(
    monkeypatch: pytest.MonkeyPatch, rows: list[DerivedSourceCountRow]
) -> FakeSourceCounts:
    fake = FakeSourceCounts(rows=rows)
    monkeypatch.setattr(target=branch_sources, name="list_derived_source_counts", value=fake)
    return fake


async def test_the_database_path_keeps_the_query_order_and_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The query sorts newest first; enrichment runs concurrently and must not reorder."""
    write_run(runs_dir=tmp_path, run_dir_name="1770000100")
    write_run(runs_dir=tmp_path, run_dir_name="1770000500")
    group_id = uuid4()
    counts = use_source_counts(
        monkeypatch=monkeypatch,
        rows=[
            DerivedSourceCountRow(scenario=SCENARIO, run_dir_name="1770000500", derived_count=1),
            DerivedSourceCountRow(scenario=SCENARIO, run_dir_name="1770000100", derived_count=4),
        ],
    )

    sources = await list_branch_sources(
        pool=CountingPool().as_db_pool(), runs_dir=tmp_path, group_id=group_id
    )

    assert [(s.source_run.run_id, s.derived_count) for s in sources] == [
        (f"{SCENARIO}/1770000500", 1),
        (f"{SCENARIO}/1770000100", 4),
    ]
    assert counts.groups_asked == [group_id]


async def test_the_database_path_skips_a_source_whose_directory_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_run(runs_dir=tmp_path, run_dir_name="1770000100")
    use_source_counts(
        monkeypatch=monkeypatch,
        rows=[
            DerivedSourceCountRow(scenario=SCENARIO, run_dir_name="1770000500", derived_count=2),
            DerivedSourceCountRow(scenario=SCENARIO, run_dir_name="1770000100", derived_count=1),
        ],
    )

    sources = await list_branch_sources(
        pool=CountingPool().as_db_pool(), runs_dir=tmp_path, group_id=uuid4()
    )

    assert [s.source_run.run_id for s in sources] == [f"{SCENARIO}/1770000100"]
