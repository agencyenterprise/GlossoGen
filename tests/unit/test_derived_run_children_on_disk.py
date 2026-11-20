"""The run detail's ``children`` list without a database.

The children are found from each run's derivation manifests, and only they are
enriched into summaries: the run detail page asks for this on every view, and a
runs directory holds thousands of runs that are nobody's children.
"""

from pathlib import Path

import pytest

from glossogen.run_storage import run_discovery
from glossogen.run_storage.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.run_storage.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.run_storage.run_summary_models import RunSummary
from glossogen.server.runs import derived_run_references
from tests.fakes.local_app import (
    GROUP_API,
    build_local_app,
    local_client,
    one_round_run_events,
    write_event_log,
)

SCENARIO = "veyru"
PARENT = "1770000100"


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
    """A replace-agent run (``replaced_agent_id`` set) or fork-at-round run (``None``)."""
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


def write_family(runs_dir: Path) -> None:
    """The parent, three children of every derivation kind, and runs that are not its children.

    ``1770000500`` is the cross-run child's source B, which does not make it a parent;
    ``1770000600`` is a child of ``1770000500``.
    """
    write_run(runs_dir=runs_dir, run_dir_name=PARENT)
    write_replace_child(
        runs_dir=runs_dir,
        run_dir_name="1770000200",
        source_run_dir_name=PARENT,
        replaced_agent_id="field_observer",
    )
    write_replace_child(
        runs_dir=runs_dir,
        run_dir_name="1770000300",
        source_run_dir_name=PARENT,
        replaced_agent_id=None,
    )
    write_cross_run_child(
        runs_dir=runs_dir,
        run_dir_name="1770000400",
        source_a_dir_name=PARENT,
        source_b_dir_name="1770000500",
    )
    write_run(runs_dir=runs_dir, run_dir_name="1770000500")
    write_replace_child(
        runs_dir=runs_dir,
        run_dir_name="1770000600",
        source_run_dir_name="1770000500",
        replaced_agent_id="field_observer",
    )


async def children_over_http(runs_dir: Path, run_dir_name: str) -> list[str]:
    """The run ids in ``GET /runs/{scenario}/{run}``'s ``children``, in response order."""
    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.get(f"{GROUP_API}/runs/{SCENARIO}/{run_dir_name}")
    assert response.status_code == 200, response.text
    return [child["run_id"] for child in response.json()["children"]]


async def test_every_kind_of_derivation_is_a_child_newest_first(tmp_path: Path) -> None:
    write_family(runs_dir=tmp_path)

    assert await children_over_http(runs_dir=tmp_path, run_dir_name=PARENT) == [
        f"{SCENARIO}/1770000400",
        f"{SCENARIO}/1770000300",
        f"{SCENARIO}/1770000200",
    ]
    assert await children_over_http(runs_dir=tmp_path, run_dir_name="1770000500") == [
        f"{SCENARIO}/1770000600",
    ]


async def test_only_the_children_are_built_into_summaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_family(runs_dir=tmp_path)
    for unrelated in range(20):
        write_run(runs_dir=tmp_path, run_dir_name=str(1_770_001_000 + unrelated))
    built: list[str] = []
    build_summary = run_discovery.build_summary

    async def counting_build_summary(
        scenario_name: str, timestamp_dir: Path, evaluation_content_hash: str | None
    ) -> RunSummary | None:
        built.append(timestamp_dir.name)
        return await build_summary(
            scenario_name=scenario_name,
            timestamp_dir=timestamp_dir,
            evaluation_content_hash=evaluation_content_hash,
        )

    # Under both names a summary is built by: the run-discovery module's own and
    # the one the children lookup imported.
    monkeypatch.setattr(run_discovery, "build_summary", counting_build_summary)
    monkeypatch.setattr(derived_run_references, "build_summary", counting_build_summary)

    await children_over_http(runs_dir=tmp_path, run_dir_name=PARENT)

    assert sorted(built) == ["1770000200", "1770000300", "1770000400"]


async def test_a_run_whose_manifest_cannot_be_read_is_left_out(tmp_path: Path) -> None:
    write_family(runs_dir=tmp_path)
    broken = write_run(runs_dir=tmp_path, run_dir_name="1770000700")
    (broken / REPLACE_MANIFEST_FILENAME).write_text("{not json")

    assert await children_over_http(runs_dir=tmp_path, run_dir_name=PARENT) == [
        f"{SCENARIO}/1770000400",
        f"{SCENARIO}/1770000300",
        f"{SCENARIO}/1770000200",
    ]
