"""Run detail lists the lines no loaded class declares, in the order the log holds them."""

from pathlib import Path

import orjson

from glossogen.models.event import RunStatus, SimulationEnded, SimulationStarted
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.server.runs.detail_reader import load_run_detail
from glossogen.server.runs.models import RunDetailResponse, UnrecognizedEventEntry
from tests.fakes.local_app import at_second, write_event_log

SCENARIO = "move_a_box"


def unrecognized_line(*, event_id: str, event_type: str, second: int) -> bytes:
    """Return a log line of an event type no loaded scenario declares."""
    return orjson.dumps(
        {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": at_second(seconds=second).isoformat(),
            "board": [[1, 2], [3, None]],
        }
    )


async def detail_with_lines(
    tmp_path: Path, extra_records: list[tuple[int, bytes]]
) -> RunDetailResponse:
    """Write a start and an end with ``extra_records`` between them, and read the detail."""
    started = SimulationStarted(
        round_number=0,
        timestamp=at_second(seconds=0),
        run_id=f"{SCENARIO}/1770000100",
        scenario_name=SCENARIO,
        scenario_description="",
        channel_ids=[],
        provider="anthropic",
        scenario_config={},
    )
    ended = SimulationEnded(
        round_number=0,
        timestamp=at_second(seconds=100),
        reason=RunStatus.SCENARIO_COMPLETE,
        total_messages=0,
        total_cost_usd=0.0,
    )
    run_dir = write_event_log(
        runs_dir=tmp_path,
        scenario_name=SCENARIO,
        run_dir_name="1770000100",
        events=[started, ended],
        extra_records=extra_records,
    )
    return await load_run_detail(
        log_path=event_log_path(run_dir=run_dir, scenario_name=SCENARIO), children=[]
    )


async def test_each_unrecognized_line_becomes_an_entry_with_its_payload(tmp_path: Path) -> None:
    """The entry keeps the id, type, round and time, and the whole line as ``payload``."""
    detail = await detail_with_lines(
        tmp_path=tmp_path,
        extra_records=[
            (1, unrecognized_line(event_id="u1", event_type="gone_board_dealt", second=10)),
            (2, unrecognized_line(event_id="u2", event_type="gone_round_scored", second=20)),
        ],
    )

    assert [entry.event_id for entry in detail.unrecognized_events] == ["u1", "u2"]
    entry = detail.unrecognized_events[0]
    assert isinstance(entry, UnrecognizedEventEntry)
    assert entry.event_type == "gone_board_dealt"
    assert entry.round_number == 0
    assert entry.timestamp == at_second(seconds=10)
    assert entry.payload["board"] == [[1, 2], [3, None]]
    assert entry.payload["event_id"] == "u1"


async def test_a_run_with_only_recognized_events_lists_none(tmp_path: Path) -> None:
    """The list is empty, not absent."""
    detail = await detail_with_lines(tmp_path=tmp_path, extra_records=[])

    assert detail.unrecognized_events == []
