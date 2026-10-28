"""The export downloads, requested over HTTP from runs on disk.

The routers' own tests call the handlers with the selection resolver stubbed and
the run records built in memory. These go through the app instead, so the run is
resolved, read from its log and written into the archive by the code that serves
it. The run carries an event no class in this build declares, which every
download has to step over.
"""

import csv
import io
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest

from glossogen.run_file_paths import debug_log_path, event_log_path
from tests.fakes.local_app import (
    GROUP_API,
    build_local_app,
    local_client,
    one_round_run_events,
    unreadable_record,
    write_event_log,
)

SCENARIO = "veyru"
RUN_DIR_NAME = "1770000100"
RUN_ID = f"{SCENARIO}/{RUN_DIR_NAME}"


@pytest.fixture(name="run_dir")
def run_dir_fixture(tmp_path: Path) -> Path:
    """One finished veyru run with a debug log, under ``tmp_path/runs``."""
    run_dir = write_event_log(
        runs_dir=tmp_path / "runs",
        scenario_name=SCENARIO,
        run_dir_name=RUN_DIR_NAME,
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name=RUN_DIR_NAME, finished=True
        ),
        extra_records=[(3, unreadable_record(event_id="u1", seconds=2))],
    )
    debug_log_path(run_dir=run_dir, scenario_name=SCENARIO).write_bytes(b"{}\n")
    return run_dir


@pytest.fixture(name="client")
def client_fixture(run_dir: Path) -> httpx.AsyncClient:
    """A client for an app serving the runs directory that holds ``run_dir``."""
    return local_client(app=build_local_app(runs_dir=run_dir.parent.parent))


def explicit_selection() -> dict[str, Any]:
    """A selection naming the one run by id."""
    return {"kind": "explicit", "run_ids": [RUN_ID]}


async def test_the_run_zip_holds_its_folder_and_each_agents_trajectory(
    client: httpx.AsyncClient, run_dir: Path
) -> None:
    async with client:
        response = await client.get(f"{GROUP_API}/runs/{RUN_ID}/export/zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f'filename="{RUN_DIR_NAME}.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        log_bytes = archive.read(f"{RUN_DIR_NAME}/{SCENARIO}.jsonl")
    assert log_bytes == event_log_path(run_dir=run_dir, scenario_name=SCENARIO).read_bytes()
    assert f"{RUN_DIR_NAME}/{SCENARIO}_debug.jsonl" not in names
    trajectories = [name for name in names if name.startswith(f"{RUN_DIR_NAME}/atif/")]
    assert len(trajectories) == 1
    assert "field_observer" in trajectories[0]


async def test_a_bundle_imports_into_another_server_as_the_same_run(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    async with client:
        exported = await client.get(f"{GROUP_API}/runs/{RUN_ID}/export/bundle")
    assert exported.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(exported.content), mode="r:gz") as bundle:
        names = bundle.getnames()
    assert f"{SCENARIO}.jsonl" in names
    assert f"{SCENARIO}_debug.jsonl" not in names

    other_runs_dir = tmp_path / "other_runs"
    other_runs_dir.mkdir()
    async with local_client(app=build_local_app(runs_dir=other_runs_dir)) as other:
        imported = await other.post(
            f"{GROUP_API}/runs/import",
            files={"file": ("bundle.tar.gz", exported.content, "application/gzip")},
        )
        assert imported.status_code == 200
        detail = await other.get(f"{GROUP_API}/runs/{imported.json()['run_id']}")

    assert detail.status_code == 200
    assert [m["text"] for m in detail.json()["messages"]] == ["symptoms"]


async def test_the_raw_export_nests_the_run_under_its_scenario(
    client: httpx.AsyncClient, run_dir: Path
) -> None:
    async with client:
        response = await client.post(
            f"{GROUP_API}/runs/export/raw",
            json={"selection": explicit_selection(), "include_logs": True, "include_atif": False},
        )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        log_bytes = archive.read(f"{RUN_ID}/{SCENARIO}.jsonl")
    assert log_bytes == event_log_path(run_dir=run_dir, scenario_name=SCENARIO).read_bytes()
    assert f"{RUN_ID}/{SCENARIO}_debug.jsonl" in names
    assert "manifest.csv" in names
    assert not any("/atif/" in name for name in names)


async def test_the_message_table_carries_what_was_said(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.post(
            f"{GROUP_API}/runs/export/csv",
            json={
                "selection": explicit_selection(),
                "frames": ["message_level"],
                "columns": ["status"],
                "metrics": [],
                "repeat_run_columns": False,
                "include_metric_summaries": False,
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [(row["run_id"], row["message_id"], row["text"]) for row in rows] == [
        (RUN_ID, "m1", "symptoms")
    ]


MALFORMED_RUN_DIR_NAME = "1770000200"
MALFORMED_RUN_ID = f"{SCENARIO}/{MALFORMED_RUN_DIR_NAME}"


def write_malformed_run(runs_dir: Path) -> Path:
    """A finished run with a ``message_sent`` record that lacks its message.

    The type is one this build declares, so the log reader raises on it rather than
    skipping it, as it does for an old run whose events have since gained fields.
    """
    malformed = (
        b'{"event_id":"bad","event_type":"message_sent","timestamp":'
        b'"2026-01-01T00:00:04+00:00","round_number":1}'
    )
    return write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name=MALFORMED_RUN_DIR_NAME,
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name=MALFORMED_RUN_DIR_NAME, finished=True
        ),
        extra_records=[(4, malformed)],
    )


async def test_a_run_whose_log_does_not_parse_zips_without_trajectories(
    client: httpx.AsyncClient, run_dir: Path
) -> None:
    malformed_dir = write_malformed_run(runs_dir=run_dir.parent.parent)

    async with client:
        response = await client.get(f"{GROUP_API}/runs/{MALFORMED_RUN_ID}/export/zip")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        log_bytes = archive.read(f"{MALFORMED_RUN_DIR_NAME}/{SCENARIO}.jsonl")
    assert log_bytes == event_log_path(run_dir=malformed_dir, scenario_name=SCENARIO).read_bytes()
    assert not any("/atif/" in name for name in names)


async def test_a_run_whose_log_does_not_parse_leaves_the_others_trajectories_in_the_raw_export(
    client: httpx.AsyncClient, run_dir: Path
) -> None:
    write_malformed_run(runs_dir=run_dir.parent.parent)

    async with client:
        response = await client.post(
            f"{GROUP_API}/runs/export/raw",
            json={
                "selection": {"kind": "explicit", "run_ids": [RUN_ID, MALFORMED_RUN_ID]},
                "include_logs": False,
                "include_atif": True,
            },
        )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
    assert f"{MALFORMED_RUN_ID}/{SCENARIO}.jsonl" in names
    assert not any(name.startswith(f"{MALFORMED_RUN_ID}/atif/") for name in names)
    assert any(name.startswith(f"{RUN_ID}/atif/") for name in names)


async def test_a_run_whose_last_line_is_half_written_zips_without_trajectories(
    client: httpx.AsyncClient, run_dir: Path
) -> None:
    """A live run's log can end mid-line while the zip is being built."""
    live_dir = write_event_log(
        runs_dir=run_dir.parent.parent,
        scenario_name=SCENARIO,
        run_dir_name="1770000300",
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name="1770000300", finished=False
        ),
        extra_records=[],
    )
    log_path = event_log_path(run_dir=live_dir, scenario_name=SCENARIO)
    log_path.write_bytes(log_path.read_bytes() + b'{"event_id":"half","event_ty')

    async with client:
        response = await client.get(f"{GROUP_API}/runs/{SCENARIO}/1770000300/export/zip")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
    assert "1770000300/veyru.jsonl" in names
    assert not any("/atif/" in name for name in names)
