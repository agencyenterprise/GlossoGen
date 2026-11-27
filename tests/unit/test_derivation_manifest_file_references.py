"""A derivation manifest names files inside its own run directory and nowhere else.

The cross-run and history-transfer manifests each name a file that resume, the
trajectory exports and the protocol probes read relative to the run directory. A
bundle upload carries its manifests verbatim, so an uploader who could name any path
there could have the server read another run's event log (another group's, on a shared
runs directory) into the trajectories it exports.
"""

import io
import zipfile
from pathlib import Path

import orjson
import pytest
from pydantic import ValidationError

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    LLMResponseReceived,
    RoundAdvanced,
    StopReason,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.run_storage.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    IMPORTED_HISTORY_SOURCE_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.run_storage.history_transfer_manifest import TransferredSeat
from glossogen.run_storage.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.run_storage.run_bundle import build_bundle_bytes
from glossogen.run_storage.run_file_paths import event_log_path
from tests.fakes.local_app import (
    GROUP_API,
    at_second,
    build_local_app,
    local_client,
    one_round_run_events,
    write_event_log,
)

SCENARIO = "veyru"
SECRET = "the other group's coordinates"


def _registered(seconds: int) -> AgentRegistered:
    return AgentRegistered(
        round_number=0,
        timestamp=at_second(seconds),
        agent_id="field_observer",
        role_name="Field Observer",
        model="claude-sonnet-4-6",
        provider="anthropic",
        system_prompt="",
        channel_ids=["link"],
        tool_names=["send_message"],
        model_settings=AgentModelSettings(max_tokens=1024),
    )


def _response(text: str, round_number: int, seconds: int) -> LLMResponseReceived:
    return LLMResponseReceived(
        agent_id="field_observer",
        thinking="",
        text=text,
        tool_calls=[],
        stop_reason=StopReason.END_TURN,
        usage=TokenUsage(
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        round_number=round_number,
        timestamp=at_second(seconds),
    )


def _secret_run_events() -> list[EventBase]:
    """A run whose ``field_observer`` writes text no uploader should read."""
    events = one_round_run_events(scenario_name=SCENARIO, run_dir_name="1600000000", finished=False)
    events.append(_response(text=SECRET, round_number=1, seconds=5))
    events.append(RoundAdvanced(round_number=2, timestamp=at_second(6), trigger="timer"))
    return events


def _cross_run_manifest(
    imported_history_source: str, target_event_id: str
) -> CrossRunReplaceManifest:
    """A manifest built without validation, so a test can write one naming any path."""
    return CrossRunReplaceManifest.model_construct(
        source_a_run_id=f"{SCENARIO}/1500000000",
        source_a_run_dir=f"runs/{SCENARIO}/1500000000",
        source_b_run_id=f"{SCENARIO}/1600000000",
        source_b_run_dir=f"runs/{SCENARIO}/1600000000",
        imported_history_source=imported_history_source,
        round_start=1,
        rounds_after_swap=1,
        target_event_id=target_event_id,
        source_b_round_end=1,
        source_b_cutoff_event_id="",
        replaced_agent_id="field_observer",
        imported_model="claude-sonnet-4-6",
        imported_provider="anthropic",
        channels_with_visible_history=["link"],
        blocked_tool_call_channels=[],
        replaced_at=0.0,
    )


def _write_crafted_run(runs_dir: Path, imported_history_source: str) -> Path:
    """A cross-run run whose manifest points its imported history at ``imported_history_source``.

    The seat is re-registered past the boundary, so the trajectory exports rebuild
    its seed from the imported history.
    """
    copied = one_round_run_events(scenario_name=SCENARIO, run_dir_name="1700000000", finished=False)
    events = copied + [
        _registered(seconds=20),
        _response(text="my own reply", round_number=2, seconds=21),
    ]
    run_dir = write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name="1700000000",
        events=events,
        extra_records=[],
    )
    manifest = _cross_run_manifest(
        imported_history_source=imported_history_source,
        target_event_id=copied[-1].event_id,
    )
    (run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME).write_bytes(
        orjson.dumps(manifest.model_dump(mode="json"))
    )
    return run_dir


def _crafted_bundle(tmp_path: Path, imported_history_source: str) -> bytes:
    """A bundle of the crafted run, built the way an export builds one."""
    run_dir = _write_crafted_run(
        runs_dir=tmp_path / "staging", imported_history_source=imported_history_source
    )
    return build_bundle_bytes(
        run_dir=run_dir,
        run_id=f"{SCENARIO}/1700000000",
        scenario_name=SCENARIO,
        original_timestamp=1700000000,
    )


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    runs.mkdir()
    return runs


@pytest.fixture
def secret_log(runs_dir: Path) -> Path:
    """Another run's log on the same runs directory, as another group's would be."""
    run_dir = write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name="1600000000",
        events=_secret_run_events(),
        extra_records=[],
    )
    return event_log_path(run_dir=run_dir, scenario_name=SCENARIO)


@pytest.mark.parametrize(
    "imported_history_source",
    [
        pytest.param("../1600000000/veyru.jsonl", id="relative"),
        pytest.param("absolute", id="absolute"),
    ],
)
async def test_an_uploaded_manifest_cannot_export_another_runs_log(
    tmp_path: Path,
    runs_dir: Path,
    secret_log: Path,
    imported_history_source: str,
) -> None:
    if imported_history_source == "absolute":
        imported_history_source = str(secret_log)
    bundle = _crafted_bundle(tmp_path=tmp_path, imported_history_source=imported_history_source)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        imported = await client.post(
            f"{GROUP_API}/runs/import",
            files={"file": ("bundle.tar.gz", bundle, "application/gzip")},
        )
        assert imported.status_code == 422
        exported = await client.get(f"{GROUP_API}/runs/{SCENARIO}/1700000000/export/inspect")

    assert exported.status_code == 404
    assert SECRET.encode() not in exported.content
    assert sorted(path.name for path in (runs_dir / SCENARIO).iterdir()) == ["1600000000"]


async def test_a_crafted_run_on_disk_exports_without_the_file_it_points_at(
    runs_dir: Path, secret_log: Path
) -> None:
    """A run that reached the runs directory some other way, such as a copy, is read safely."""
    _write_crafted_run(runs_dir=runs_dir, imported_history_source=str(secret_log))

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        inspect_log = await client.get(f"{GROUP_API}/runs/{SCENARIO}/1700000000/export/inspect")
        run_zip = await client.get(f"{GROUP_API}/runs/{SCENARIO}/1700000000/export/zip")

    assert inspect_log.status_code == 422
    assert run_zip.status_code == 200
    with zipfile.ZipFile(io.BytesIO(run_zip.content)) as archive:
        names = archive.namelist()
        assert not any("/atif/" in name for name in names)
        assert not any(SECRET.encode() in archive.read(name) for name in names)


async def test_a_bundle_whose_lineage_names_no_scenario_is_refused_and_removed(
    tmp_path: Path, runs_dir: Path
) -> None:
    events = one_round_run_events(scenario_name=SCENARIO, run_dir_name="1700000000", finished=True)
    run_dir = write_event_log(
        runs_dir=tmp_path / "staging",
        scenario_name=SCENARIO,
        run_dir_name="1700000000",
        events=events,
        extra_records=[],
    )
    manifest = ReplaceManifest(
        source_run_id="no-scenario-part",
        source_run_dir="runs/veyru/1600000000",
        round_start=1,
        rounds_after_swap=0,
        target_event_id=events[-1].event_id,
        replaced_agent_id=None,
        replacement_model=None,
        replacement_provider=None,
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        replaced_at=0.0,
    )
    (run_dir / REPLACE_MANIFEST_FILENAME).write_text(manifest.model_dump_json())
    bundle = build_bundle_bytes(
        run_dir=run_dir,
        run_id=f"{SCENARIO}/1700000000",
        scenario_name=SCENARIO,
        original_timestamp=1700000000,
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        imported = await client.post(
            f"{GROUP_API}/runs/import",
            files={"file": ("bundle.tar.gz", bundle, "application/gzip")},
        )

    assert imported.status_code == 422
    assert not (runs_dir / SCENARIO).exists() or not any((runs_dir / SCENARIO).iterdir())


@pytest.mark.parametrize(
    "file_name",
    ["../veyru.jsonl", "/etc/passwd", "sub/file.jsonl", "..", ".", ""],
)
def test_a_cross_run_manifest_refuses_a_history_source_outside_its_run(file_name: str) -> None:
    raw = _cross_run_manifest(imported_history_source=file_name, target_event_id="e").model_dump()

    with pytest.raises(ValidationError):
        CrossRunReplaceManifest.model_validate(raw)


def test_a_cross_run_manifest_accepts_the_file_its_writer_names() -> None:
    raw = _cross_run_manifest(
        imported_history_source=IMPORTED_HISTORY_SOURCE_FILENAME, target_event_id="e"
    ).model_dump()

    assert (
        CrossRunReplaceManifest.model_validate(raw).imported_history_source
        == IMPORTED_HISTORY_SOURCE_FILENAME
    )


@pytest.mark.parametrize("file_name", ["../transferred_history_a.json", "/tmp/a.json", "a/b.json"])
def test_a_transferred_seat_refuses_a_history_file_outside_its_run(file_name: str) -> None:
    with pytest.raises(ValidationError):
        TransferredSeat(
            agent_id="a",
            source_agent_id="a",
            source_model="claude-sonnet-4-6",
            source_provider="anthropic",
            history_file=file_name,
        )


async def test_a_plain_bundle_still_imports(tmp_path: Path, runs_dir: Path) -> None:
    events = one_round_run_events(scenario_name=SCENARIO, run_dir_name="1700000000", finished=True)
    run_dir = write_event_log(
        runs_dir=tmp_path / "staging",
        scenario_name=SCENARIO,
        run_dir_name="1700000000",
        events=events,
        extra_records=[],
    )
    bundle = build_bundle_bytes(
        run_dir=run_dir,
        run_id=f"{SCENARIO}/1700000000",
        scenario_name=SCENARIO,
        original_timestamp=1700000000,
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        imported = await client.post(
            f"{GROUP_API}/runs/import",
            files={"file": ("bundle.tar.gz", bundle, "application/gzip")},
        )

    assert imported.status_code == 200
