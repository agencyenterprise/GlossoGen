"""Stopping and deleting a run over HTTP.

A live run is one whose directory holds a ``stream.json`` naming a process that
is alive. ``os.kill`` is replaced by a fake process table, so no test signals a
real process: signal 0 asks whether a PID is alive, and SIGTERM is recorded.
"""

import os
import signal
from pathlib import Path

import orjson
import pytest

from glossogen.models.event import RunStatus
from glossogen.run_archive import TRASH_DIR_NAME
from glossogen.run_file_paths import event_log_path
from glossogen.stream_manifest import MANIFEST_FILENAME, StreamManifest, write_manifest
from tests.fakes.local_app import (
    GROUP_API,
    build_local_app,
    local_client,
    one_round_run_events,
    write_event_log,
)

SCENARIO = "veyru"
RUN = "1770000100"
SIMULATION_PID = 424242


class FakeProcessTable:
    """Stands in for ``os.kill``: PIDs in ``alive`` exist, and SIGTERMs are recorded."""

    def __init__(self, alive: set[int]) -> None:
        self.alive = alive
        self.terminated: list[int] = []

    def kill(self, pid: int, sig: int) -> None:
        if pid not in self.alive:
            raise ProcessLookupError(pid)
        if sig == signal.SIGTERM:
            self.terminated.append(pid)


@pytest.fixture
def processes(monkeypatch: pytest.MonkeyPatch) -> FakeProcessTable:
    table = FakeProcessTable(alive={SIMULATION_PID})
    monkeypatch.setattr(os, "kill", table.kill)
    return table


def _write_run(runs_dir: Path, finished: bool) -> Path:
    return write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name=RUN,
        events=one_round_run_events(scenario_name=SCENARIO, run_dir_name=RUN, finished=finished),
        extra_records=[],
    )


def _make_live(run_dir: Path) -> None:
    write_manifest(
        run_dir=run_dir,
        manifest=StreamManifest(
            host="127.0.0.1", port=1, run_id=f"{SCENARIO}/{RUN}", pid=SIMULATION_PID
        ),
    )


def _last_record(run_dir: Path) -> dict[str, object]:
    log_path = event_log_path(run_dir=run_dir, scenario_name=SCENARIO)
    return orjson.loads(log_path.read_bytes().splitlines()[-1])


async def test_stopping_a_live_run_terminates_it_and_ends_its_log(
    tmp_path: Path, processes: FakeProcessTable
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=False)
    _make_live(run_dir=run_dir)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(f"{GROUP_API}/runs/{SCENARIO}/{RUN}/stop")
        detail = await client.get(f"{GROUP_API}/runs/{SCENARIO}/{RUN}")

    assert response.status_code == 204
    assert processes.terminated == [SIMULATION_PID]
    assert not (run_dir / MANIFEST_FILENAME).exists()
    ended = _last_record(run_dir=run_dir)
    assert ended["event_type"] == "simulation_ended"
    assert ended["reason"] == RunStatus.KILLED
    assert (ended["round_number"], ended["total_messages"]) == (1, 1)
    assert detail.json()["status"] == RunStatus.KILLED


def _exit_before_sigterm(pid: int, sig: int) -> None:
    """A process that is alive when the manifest is read and gone by the SIGTERM."""
    if sig == signal.SIGTERM:
        raise ProcessLookupError(pid)


async def test_stopping_a_run_whose_process_exits_before_the_signal_still_ends_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=False)
    _make_live(run_dir=run_dir)
    monkeypatch.setattr(os, "kill", _exit_before_sigterm)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(f"{GROUP_API}/runs/{SCENARIO}/{RUN}/stop")

    assert response.status_code == 204
    assert _last_record(run_dir=run_dir)["reason"] == RunStatus.KILLED
    assert not (run_dir / MANIFEST_FILENAME).exists()


async def test_deleting_a_run_whose_process_exits_before_the_signal_still_trashes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=False)
    _make_live(run_dir=run_dir)
    monkeypatch.setattr(os, "kill", _exit_before_sigterm)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.delete(f"{GROUP_API}/runs/{SCENARIO}/{RUN}")

    assert response.status_code == 204
    trashed_dir = runs_dir / TRASH_DIR_NAME / SCENARIO / RUN
    assert trashed_dir.is_dir()
    assert not (trashed_dir / MANIFEST_FILENAME).exists()


@pytest.mark.parametrize(
    ("manifest_pid", "finished"),
    [
        pytest.param(None, True, id="a finished run"),
        pytest.param(SIMULATION_PID + 1, False, id="a manifest naming a dead process"),
    ],
)
async def test_stopping_a_run_that_is_not_live_is_refused_and_leaves_its_log(
    tmp_path: Path, processes: FakeProcessTable, manifest_pid: int | None, finished: bool
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=finished)
    if manifest_pid is not None:
        write_manifest(
            run_dir=run_dir,
            manifest=StreamManifest(
                host="127.0.0.1", port=1, run_id=f"{SCENARIO}/{RUN}", pid=manifest_pid
            ),
        )
    log_before = event_log_path(run_dir=run_dir, scenario_name=SCENARIO).read_bytes()

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(f"{GROUP_API}/runs/{SCENARIO}/{RUN}/stop")

    assert response.status_code == 409
    assert processes.terminated == []
    assert event_log_path(run_dir=run_dir, scenario_name=SCENARIO).read_bytes() == log_before


async def test_deleting_a_run_moves_it_to_the_trash_and_out_of_the_list(
    tmp_path: Path, processes: FakeProcessTable
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=True)
    log_before = event_log_path(run_dir=run_dir, scenario_name=SCENARIO).read_bytes()

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.delete(f"{GROUP_API}/runs/{SCENARIO}/{RUN}")
        listing = await client.get(f"{GROUP_API}/runs")
        detail = await client.get(f"{GROUP_API}/runs/{SCENARIO}/{RUN}")

    assert response.status_code == 204
    assert not run_dir.exists()
    trashed_dir = runs_dir / TRASH_DIR_NAME / SCENARIO / RUN
    assert event_log_path(run_dir=trashed_dir, scenario_name=SCENARIO).read_bytes() == log_before
    assert listing.json()["runs"] == []
    assert detail.status_code == 404
    assert processes.terminated == []


async def test_deleting_a_live_run_terminates_it_first(
    tmp_path: Path, processes: FakeProcessTable
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=False)
    _make_live(run_dir=run_dir)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.delete(f"{GROUP_API}/runs/{SCENARIO}/{RUN}")

    assert response.status_code == 204
    assert processes.terminated == [SIMULATION_PID]
    trashed_dir = runs_dir / TRASH_DIR_NAME / SCENARIO / RUN
    assert trashed_dir.is_dir()
    assert not (trashed_dir / MANIFEST_FILENAME).exists()


async def test_deleting_a_run_whose_manifest_names_a_dead_process_signals_nothing(
    tmp_path: Path, processes: FakeProcessTable
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=False)
    write_manifest(
        run_dir=run_dir,
        manifest=StreamManifest(
            host="127.0.0.1", port=1, run_id=f"{SCENARIO}/{RUN}", pid=SIMULATION_PID + 1
        ),
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.delete(f"{GROUP_API}/runs/{SCENARIO}/{RUN}")

    assert response.status_code == 204
    assert processes.terminated == []
    assert (runs_dir / TRASH_DIR_NAME / SCENARIO / RUN).is_dir()


async def test_deleting_a_run_name_already_in_the_trash_keeps_both(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir=runs_dir, finished=True)
    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        first = await client.delete(f"{GROUP_API}/runs/{SCENARIO}/{RUN}")
        _write_run(runs_dir=runs_dir, finished=False)
        second = await client.delete(f"{GROUP_API}/runs/{SCENARIO}/{RUN}")

    assert (first.status_code, second.status_code) == (204, 204)
    trash = runs_dir / TRASH_DIR_NAME / SCENARIO
    assert sorted(path.name for path in trash.iterdir()) == [RUN, f"{RUN}.1"]
    assert _last_record(run_dir=trash / RUN)["event_type"] == "simulation_ended"
    assert _last_record(run_dir=trash / f"{RUN}.1")["event_type"] == "message_sent"


@pytest.mark.parametrize("method", ["DELETE", "POST"])
async def test_an_unknown_run_answers_404(
    tmp_path: Path, processes: FakeProcessTable, method: str
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    path = f"{GROUP_API}/runs/{SCENARIO}/{RUN}"
    if method == "POST":
        path = f"{path}/stop"

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.request(method=method, url=path)

    assert response.status_code == 404
    assert processes.terminated == []
