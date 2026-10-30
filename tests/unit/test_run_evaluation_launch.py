"""Starting an evaluation of a run over HTTP.

The endpoint refuses a request before launching anything when evaluations are
off, the run is still live, another evaluation of it is running, the judge
provider is unknown, the run's scenario is not installed, or no metric is named.
Whether a metric belongs to the run's scenario is covered in
``test_scenario_metric_listings.py``.

``subprocess.Popen`` is replaced with the recorder in
``tests/fakes/evaluation_launches.py``, so nothing is launched. ``os.kill`` is
replaced by a fake process table, which is how both the simulation's and the
evaluation's manifests are judged live.
"""

import os
import subprocess
from pathlib import Path

import pytest

from glossogen.eval_manifest import write_eval_manifest
from glossogen.models.event import RunStatus, SimulationEnded
from glossogen.run_file_paths import event_log_path
from glossogen.server.feature_flags import FeatureFlags
from glossogen.stream_manifest import StreamManifest, write_manifest
from tests.fakes.evaluation_launches import RecordedLaunch, record_evaluation_launches
from tests.fakes.local_app import (
    GROUP_API,
    at_second,
    build_local_app,
    local_client,
    one_round_run_events,
    write_event_log,
)

SCENARIO = "veyru"
RUN = "1770000100"
LIVE_PID = 424242
DEAD_PID = LIVE_PID + 1
EVALUATE_URL = f"{GROUP_API}/runs/{SCENARIO}/{RUN}/evaluate"
REQUEST_BODY = {
    "model": "claude-haiku-4-5-20251001",
    "provider": "anthropic",
    "metrics": ["mean_chars_per_message", "gzip_compression_ratio"],
}


@pytest.fixture(name="launches")
def launches_fixture(monkeypatch: pytest.MonkeyPatch) -> list[RecordedLaunch]:
    """Record evaluation launches instead of starting a process."""
    return record_evaluation_launches(monkeypatch=monkeypatch)


def _kill_where_only_live_pid_exists(pid: int, sig: int) -> None:
    _ = sig
    if pid != LIVE_PID:
        raise ProcessLookupError(pid)


@pytest.fixture(autouse=True)
def process_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only ``LIVE_PID`` is alive, and no signal reaches a real process."""
    monkeypatch.setattr(os, "kill", _kill_where_only_live_pid_exists)


def _write_run(runs_dir: Path, finished: bool) -> Path:
    return write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name=RUN,
        events=one_round_run_events(scenario_name=SCENARIO, run_dir_name=RUN, finished=finished),
        extra_records=[],
    )


def _end_log(run_dir: Path, reason: RunStatus) -> None:
    ended = SimulationEnded(
        round_number=1,
        timestamp=at_second(10),
        reason=reason,
        total_messages=1,
        total_cost_usd=0.0,
    )
    with event_log_path(run_dir=run_dir, scenario_name=SCENARIO).open("ab") as log_file:
        log_file.write(ended.model_dump_json().encode() + b"\n")


def _write_stream_manifest(run_dir: Path, pid: int) -> None:
    write_manifest(
        run_dir=run_dir,
        manifest=StreamManifest(host="127.0.0.1", port=1, run_id=f"{SCENARIO}/{RUN}", pid=pid),
    )


async def test_a_finished_run_launches_the_evaluate_command_it_was_asked_for(
    tmp_path: Path, launches: list[RecordedLaunch]
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=True)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(EVALUATE_URL, json=REQUEST_BODY)

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "started"}
    assert len(launches) == 1
    command = launches[0].command
    assert command[1:5] == ["-m", "glossogen", "evaluate", SCENARIO]
    assert command[command.index("--run-dir") + 1] == str(run_dir)
    assert (
        command[command.index("--metrics") + 1] == "mean_chars_per_message,gzip_compression_ratio"
    )
    assert command[command.index("--model") + 1] == "claude-haiku-4-5-20251001"
    assert command[command.index("--provider") + 1] == "anthropic"
    assert launches[0].stdout_path == str(run_dir / "eval_stdout.log")
    assert launches[0].start_new_session


@pytest.mark.parametrize(
    "ending",
    [
        pytest.param(RunStatus.KILLED, id="killed"),
        pytest.param(RunStatus.ERROR, id="errored"),
        pytest.param(None, id="no end event and no live process"),
        pytest.param(DEAD_PID, id="no end event and a manifest naming a dead process"),
    ],
)
async def test_a_run_that_stopped_without_completing_can_be_evaluated(
    tmp_path: Path, launches: list[RecordedLaunch], ending: RunStatus | int | None
) -> None:
    """A crashed run has no ``simulation_ended``; with no live process it counts as errored."""
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=False)
    if isinstance(ending, RunStatus):
        _end_log(run_dir=run_dir, reason=ending)
    elif isinstance(ending, int):
        _write_stream_manifest(run_dir=run_dir, pid=ending)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(EVALUATE_URL, json=REQUEST_BODY)

    assert response.status_code == 200, response.text
    assert len(launches) == 1


async def test_a_live_run_is_refused(tmp_path: Path, launches: list[RecordedLaunch]) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=False)
    _write_stream_manifest(run_dir=run_dir, pid=LIVE_PID)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(EVALUATE_URL, json=REQUEST_BODY)

    assert response.status_code == 422
    assert launches == []


async def test_a_run_already_being_evaluated_is_refused(
    tmp_path: Path, launches: list[RecordedLaunch]
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=True)
    write_eval_manifest(run_dir=run_dir, pid=LIVE_PID)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(EVALUATE_URL, json=REQUEST_BODY)

    assert response.status_code == 409
    assert launches == []


async def test_an_evaluation_manifest_left_by_a_dead_process_does_not_block_a_new_one(
    tmp_path: Path, launches: list[RecordedLaunch]
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir, finished=True)
    write_eval_manifest(run_dir=run_dir, pid=DEAD_PID)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(EVALUATE_URL, json=REQUEST_BODY)

    assert response.status_code == 200, response.text
    assert len(launches) == 1


async def test_a_provider_that_cannot_judge_is_refused(
    tmp_path: Path, launches: list[RecordedLaunch]
) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir=runs_dir, finished=True)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(
            EVALUATE_URL, json={**REQUEST_BODY, "provider": "not_a_provider"}
        )

    assert response.status_code == 422
    assert "not_a_provider" in response.json()["detail"]
    assert launches == []


async def test_a_run_of_a_scenario_that_is_not_installed_is_refused(
    tmp_path: Path, launches: list[RecordedLaunch]
) -> None:
    runs_dir = tmp_path / "runs"
    write_event_log(
        runs_dir=runs_dir,
        scenario_name="not_installed",
        run_dir_name=RUN,
        events=one_round_run_events(scenario_name="not_installed", run_dir_name=RUN, finished=True),
        extra_records=[],
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(
            f"{GROUP_API}/runs/not_installed/{RUN}/evaluate", json=REQUEST_BODY
        )

    assert response.status_code == 422
    assert "not_installed" in response.json()["detail"]
    assert launches == []


async def test_evaluations_turned_off_refuse_every_request(
    tmp_path: Path, launches: list[RecordedLaunch]
) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir=runs_dir, finished=True)
    app = build_local_app(runs_dir=runs_dir)
    app.state.feature_flags = FeatureFlags(evaluations_enabled=False)

    async with local_client(app=app) as client:
        response = await client.post(EVALUATE_URL, json=REQUEST_BODY)

    assert response.status_code == 403
    assert launches == []


async def test_an_unknown_run_answers_404(tmp_path: Path, launches: list[RecordedLaunch]) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(EVALUATE_URL, json=REQUEST_BODY)

    assert response.status_code == 404
    assert launches == []


def _refuse_to_start(args: list[str], **kwargs: object) -> None:
    _ = (args, kwargs)
    raise OSError("no such interpreter")


async def test_a_launch_that_fails_to_start_answers_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir=runs_dir, finished=True)
    monkeypatch.setattr(subprocess, "Popen", _refuse_to_start)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(EVALUATE_URL, json=REQUEST_BODY)

    assert response.status_code == 503


async def test_an_empty_metric_list_is_refused(
    tmp_path: Path, launches: list[RecordedLaunch]
) -> None:
    """``--metrics ''`` would fail inside the detached process, where nobody sees it."""
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir=runs_dir, finished=True)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.post(EVALUATE_URL, json={**REQUEST_BODY, "metrics": []})

    assert response.status_code == 422
    assert launches == []
