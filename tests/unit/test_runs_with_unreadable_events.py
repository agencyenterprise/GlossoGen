"""A run whose log names an event this build has no class for, served over HTTP.

Such a log comes from a scenario not installed here, or from an event renamed
since the run. The log reader skips those records (``test_log_reader`` covers
that), and these check the pages built on top of it: the run's detail opens, and
the run stays in the list, finished or not.
"""

from pathlib import Path

from glossogen.models.event import RunStatus
from tests.fakes.local_app import (
    GROUP_API,
    build_local_app,
    local_client,
    one_round_run_events,
    unreadable_record,
    write_event_log,
)

SCENARIO = "veyru"


async def test_the_detail_of_a_run_with_unreadable_events_opens(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name="1770000100",
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name="1770000100", finished=True
        ),
        extra_records=[(3, unreadable_record(event_id="u1", seconds=2))],
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.get(f"{GROUP_API}/runs/{SCENARIO}/1770000100")

    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == RunStatus.SCENARIO_COMPLETE
    assert [(m["message_id"], m["round_number"]) for m in detail["messages"]] == [("m1", 1)]


async def test_runs_with_unreadable_events_stay_in_the_list(tmp_path: Path) -> None:
    """The summary looks for the run's end among its last lines; an unknown record is not it.

    The unknown record sits before the end, after it, and in a run that never ended.
    """
    runs_dir = tmp_path / "runs"
    write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name="1770000100",
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name="1770000100", finished=True
        ),
        extra_records=[(4, unreadable_record(event_id="u1", seconds=4))],
    )
    write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name="1770000200",
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name="1770000200", finished=False
        ),
        extra_records=[(4, unreadable_record(event_id="u2", seconds=4))],
    )
    write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name="1770000300",
        events=one_round_run_events(
            scenario_name=SCENARIO, run_dir_name="1770000300", finished=True
        ),
        extra_records=[(5, unreadable_record(event_id="u3", seconds=11))],
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.get(f"{GROUP_API}/runs")

    assert response.status_code == 200
    listed = {run["run_id"]: run for run in response.json()["runs"]}
    assert sorted(listed) == [
        f"{SCENARIO}/1770000100",
        f"{SCENARIO}/1770000200",
        f"{SCENARIO}/1770000300",
    ]
    assert listed[f"{SCENARIO}/1770000100"]["status"] == RunStatus.SCENARIO_COMPLETE
    assert listed[f"{SCENARIO}/1770000300"]["status"] == RunStatus.SCENARIO_COMPLETE
    assert listed[f"{SCENARIO}/1770000200"]["total_messages"] == 1
