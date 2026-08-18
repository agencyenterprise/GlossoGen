"""The message table: what a row says, and what an unreadable event costs.

The regression worth pinning hardest is the one that reached a user. This table
is the only one that reads event logs, and a log written before a scenario event
gained a required field no longer validates against today's model. Parsing every
line failed the whole export on an event the table would have discarded, so 48
container_yard runs on disk here could not be exported at all. Only the two event
types the table is built from are parsed now, and the rest of the log is never
looked at.

The per-message numbers are recomputed at export time rather than read from a
report, so they are checked against the helpers the metrics use rather than
against literals: the point is that the two agree, not what the number is.
"""

import asyncio
import csv
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from pydantic import ValidationError

from glossogen.evaluation.log_reader import load_events
from glossogen.evaluation.metric_core.character_entropy import character_entropy_bits
from glossogen.evaluation.metric_core.gzip_compression import gzip_compression_ratio
from glossogen.models.event import RunStatus
from glossogen.run_export.csv_export_archive import build_legend_frame
from glossogen.run_export.export_request_models import (
    CsvExportRequest,
    ExportFrame,
    FilterRunSelection,
)
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.message_event_scan import scan_message_events
from glossogen.run_export.message_level_frame import build_message_level_frame
from glossogen.run_export.primary_channel_resolution import (
    candidate_configs,
    resolve_primary_channels,
)
from glossogen.run_export.run_message_records import load_run_messages
from glossogen.scenario_loader import get_scenario_class
from glossogen.server.runs.models import AgentModelSummary, RunSummary

SCENARIO = "container_yard_stacking"
RUN_DIR_NAME = "1782210438"
RUN_ID = f"{SCENARIO}/{RUN_DIR_NAME}"

# Recorded before the event gained yard_slot_count / initial_row / batch. Kept
# verbatim rather than built from the model, because a model that can still emit
# it is a model that has not drifted, and the drift is the whole point.
STALE_CASE_EVENT: dict[str, object] = {
    "event_id": "ed2e2edd-5a00-4c00-9000-000000000001",
    "event_type": "container_yard_case_started",
    "timestamp": "2026-05-04T18:53:43+00:00",
    "round_number": 1,
    "case_number": 1,
    "target": {"row": 1, "stack": 1, "tier": 1},
}


def message_event(
    message_id: str,
    round_number: int,
    channel_id: str,
    sender_agent_id: str,
    text: str,
) -> dict[str, object]:
    """One `message_sent` line, as the logger writes it."""
    return {
        "event_id": f"msg-event-{message_id}",
        "event_type": "message_sent",
        "timestamp": "2026-05-04T18:53:44+00:00",
        "round_number": round_number,
        "token_count": 4,
        "message": {
            "message_id": message_id,
            "channel_id": channel_id,
            "sender_agent_id": sender_agent_id,
            "sender_display_name": "Yard Lead",
            "text": text,
            "timestamp": "2026-05-04T18:53:44+00:00",
            "round_number": round_number,
        },
    }


def send_result_event(message_id: str, pristine_text: str) -> dict[str, object]:
    """The `send_message` tool result that carries the text the sender composed."""
    return {
        "event_id": f"tool-result-{message_id}",
        "event_type": "tool_result_received",
        "timestamp": "2026-05-04T18:53:44+00:00",
        "round_number": 1,
        "agent_id": "yard_lead",
        "tool_name": "send_message",
        "call_id": f"call-{message_id}",
        "arguments": {"channel_id": "link", "text": pristine_text},
        "result": orjson.dumps({"status": "sent", "message_id": message_id}).decode(),
    }


def write_log(run_dir: Path, lines: list[dict[str, object]]) -> None:
    """Write a JSONL event log from raw event dicts."""
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = b"\n".join(orjson.dumps(line) for line in lines) + b"\n"
    (run_dir / f"{SCENARIO}.jsonl").write_bytes(payload)


def make_summary(run_dir: Path) -> RunSummary:
    """A summary pointing at a run directory on disk."""
    return make_summary_for(run_dir=run_dir, scenario_name=SCENARIO)


def make_summary_for(run_dir: Path, scenario_name: str) -> RunSummary:
    """A summary naming the scenario, for the cases where that is what is under test."""
    return RunSummary(
        run_id=RUN_ID,
        scenario_name=scenario_name,
        scenario_description="",
        scenario_config={},
        timestamp=datetime(2026, 5, 4, 18, 53, 43, tzinfo=UTC),
        total_messages=2,
        total_cost_usd=1.25,
        duration_seconds=600.0,
        status=RunStatus.SCENARIO_COMPLETE,
        has_evaluation=False,
        evaluation_in_progress=False,
        run_dir=str(run_dir),
        fork_source=None,
        replace_agent_source=None,
        cross_run_replace_agent_source=None,
        resume_at_round_source=None,
        models=["claude-sonnet-4-6"],
        provider="anthropic",
        agent_models=[
            AgentModelSummary(
                agent_id="yard_lead",
                role_name="Yard Lead",
                model="claude-sonnet-4-6",
                provider="anthropic",
            )
        ],
        labels=[],
        has_note=False,
        current_round=2,
        evaluation_content_hash=None,
    )


@pytest.fixture(name="run_dir")
def run_dir_fixture(tmp_path: Path) -> Path:
    """A run whose log carries a stale scenario event alongside two messages."""
    run_dir = tmp_path / "runs" / SCENARIO / RUN_DIR_NAME
    write_log(
        run_dir=run_dir,
        lines=[
            STALE_CASE_EVENT,
            message_event(
                message_id="m1",
                round_number=1,
                channel_id="link",
                sender_agent_id="yard_lead",
                text="AAAA",
            ),
            {
                "event_id": "round-advance-2",
                "event_type": "round_advanced",
                "timestamp": "2026-05-04T18:54:00+00:00",
                "round_number": 2,
                "trigger": "all_agents_idle",
            },
            message_event(
                message_id="m2",
                round_number=2,
                channel_id="link",
                sender_agent_id="yard_lead",
                text="second",
            ),
        ],
    )
    return run_dir


# --- the regression -------------------------------------------------------------


def test_an_event_that_no_longer_validates_does_not_lose_the_messages(run_dir: Path) -> None:
    """The failure that reached a user: one stale scenario event 500'd the whole export."""
    scan = scan_message_events(log_path=run_dir / f"{SCENARIO}.jsonl")

    assert [event.message.message_id for event in scan.messages] == ["m1", "m2"]
    assert scan.skipped_count == 0


def test_the_full_event_loader_still_rejects_that_same_log(run_dir: Path) -> None:
    """Pins why the scan exists: the tolerant read is not the general one going soft."""
    with pytest.raises(ValidationError):
        asyncio.run(load_events(log_path=run_dir / f"{SCENARIO}.jsonl"))


def test_a_message_event_that_cannot_be_parsed_is_counted(tmp_path: Path) -> None:
    """A dropped message is a missing row, so it is reported rather than passed over."""
    run_dir = tmp_path / "runs" / SCENARIO / RUN_DIR_NAME
    broken = message_event(
        message_id="m1",
        round_number=1,
        channel_id="link",
        sender_agent_id="yard_lead",
        text="hello",
    )
    del broken["message"]
    write_log(
        run_dir=run_dir,
        lines=[
            broken,
            message_event(
                message_id="m2",
                round_number=1,
                channel_id="link",
                sender_agent_id="yard_lead",
                text="fine",
            ),
        ],
    )
    scan = scan_message_events(log_path=run_dir / f"{SCENARIO}.jsonl")

    assert [event.message.message_id for event in scan.messages] == ["m2"]
    assert scan.skipped_count == 1


def test_a_truncated_final_line_is_skipped(tmp_path: Path) -> None:
    """A run still being written is exported while its last line is half-flushed."""
    run_dir = tmp_path / "runs" / SCENARIO / RUN_DIR_NAME
    run_dir.mkdir(parents=True)
    good = orjson.dumps(
        message_event(
            message_id="m1",
            round_number=1,
            channel_id="link",
            sender_agent_id="yard_lead",
            text="hello",
        )
    )
    (run_dir / f"{SCENARIO}.jsonl").write_bytes(good + b'\n{"event_type": "message_se')
    scan = scan_message_events(log_path=run_dir / f"{SCENARIO}.jsonl")

    assert [event.message.message_id for event in scan.messages] == ["m1"]
    assert scan.skipped_count == 1


# --- what a row carries ---------------------------------------------------------


def test_the_round_is_backfilled_from_the_running_round(run_dir: Path) -> None:
    """Logs predating round_number on EventBase still land their messages in a round."""
    messages = load_run_messages(summary=make_summary(run_dir=run_dir)).messages

    assert [message.round_number for message in messages] == [1, 2]


def test_the_message_index_restarts_per_round_and_channel(tmp_path: Path) -> None:
    """The index is the position in that conversation, not in the run."""
    run_dir = tmp_path / "runs" / SCENARIO / RUN_DIR_NAME
    write_log(
        run_dir=run_dir,
        lines=[
            message_event("m1", 1, "link", "yard_lead", "a"),
            message_event("m2", 1, "link", "yard_lead", "b"),
            message_event("m3", 1, "postmortem", "yard_lead", "c"),
            message_event("m4", 2, "link", "yard_lead", "d"),
        ],
    )
    messages = load_run_messages(summary=make_summary(run_dir=run_dir)).messages

    assert [message.index_in_round for message in messages] == [1, 2, 1, 1]


def test_the_text_is_what_the_sender_composed_with_the_delivery_beside_it(
    tmp_path: Path,
) -> None:
    """Under a channel transform the difference is the experiment, so both are kept."""
    run_dir = tmp_path / "runs" / SCENARIO / RUN_DIR_NAME
    write_log(
        run_dir=run_dir,
        lines=[
            send_result_event(message_id="m1", pristine_text="lift 12"),
            message_event("m1", 1, "link", "yard_lead", "lXft 12"),
        ],
    )
    # Nothing was dropped, so the pristine text really was indexed rather than
    # the send result quietly failing to parse and the delivered text standing in.
    assert scan_message_events(log_path=run_dir / f"{SCENARIO}.jsonl").skipped_count == 0

    [message] = load_run_messages(summary=make_summary(run_dir=run_dir)).messages

    assert message.text == "lift 12"
    assert message.delivered_text == "lXft 12"
    assert message.chars == len("lift 12")


def test_the_per_message_numbers_match_the_metric_helpers(run_dir: Path) -> None:
    """Recomputed at export time, so what they must equal is what the metrics compute."""
    [first, _] = load_run_messages(summary=make_summary(run_dir=run_dir)).messages

    assert first.character_entropy_bits == character_entropy_bits(text="AAAA")
    assert first.gzip_compression_ratio == gzip_compression_ratio(text="AAAA")


def test_a_message_with_no_repetition_sidecar_carries_no_factor(run_dir: Path) -> None:
    """The metric writes that sidecar, and most runs never ran it."""
    messages = load_run_messages(summary=make_summary(run_dir=run_dir)).messages

    assert [message.repetition_factor for message in messages] == [None, None]


def test_the_repetition_factor_joins_on_message_id(run_dir: Path) -> None:
    """The sidecar is keyed by message_id, which is what makes the join exact."""
    (run_dir / "language_repetition_messages.jsonl").write_bytes(
        orjson.dumps({"message_id": "m2", "repetition_factor": 2.5}) + b"\n"
    )
    messages = load_run_messages(summary=make_summary(run_dir=run_dir)).messages

    assert [message.repetition_factor for message in messages] == [None, 2.5]


# --- the frame ------------------------------------------------------------------


def frame_rows(run_dir: Path, repeat_run_columns: bool) -> list[dict[str, str]]:
    """Build the message frame for one run and read its rows back as dicts."""
    frame = build_message_level_frame(
        records=[ExportRunRecord(summary=make_summary(run_dir=run_dir), report=None)],
        columns=["status"],
        repeat_run_columns=repeat_run_columns,
    )
    return [dict(zip(frame.header, row)) for row in frame.rows]


def test_the_frame_carries_one_row_per_message_with_the_sender_resolved(
    run_dir: Path,
) -> None:
    """Grouping by model is the point, and a message event carries neither model nor role."""
    rows = frame_rows(run_dir=run_dir, repeat_run_columns=False)

    assert len(rows) == 2
    assert rows[0]["run_id"] == RUN_ID
    assert rows[0]["text"] == "AAAA"
    assert rows[0]["sender_agent_id"] == "yard_lead"
    assert rows[0]["sender_role"] == "Yard Lead"
    assert rows[0]["sender_model"] == "claude-sonnet-4-6"


def test_the_row_says_whether_its_channel_was_the_primary_one(run_dir: Path) -> None:
    """The scenario declares which channel the task ran on, so the row can be filtered on it."""
    rows = frame_rows(run_dir=run_dir, repeat_run_columns=False)

    assert rows[0]["channel_id"] == "link"
    assert rows[0]["is_primary_channel"] == "True"
    assert rows[0]["team_id"] == ""


def test_a_scenario_that_cannot_be_resolved_leaves_the_team_columns_empty(
    run_dir: Path,
) -> None:
    """Empty reads as not known. Writing False would claim the channel is not primary."""
    # The log is named after the scenario, so the same events are read under the
    # name of a scenario nothing installed answers to.
    unknown = "a_scenario_nobody_shipped"
    (run_dir / f"{unknown}.jsonl").write_bytes((run_dir / f"{SCENARIO}.jsonl").read_bytes())
    frame = build_message_level_frame(
        records=[
            ExportRunRecord(
                summary=make_summary_for(run_dir=run_dir, scenario_name=unknown),
                report=None,
            )
        ],
        columns=[],
        repeat_run_columns=False,
    )
    rows = [dict(zip(frame.header, row)) for row in frame.rows]

    assert rows[0]["is_primary_channel"] == ""
    assert rows[0]["team_id"] == ""


def test_repeating_run_columns_widens_the_message_table(run_dir: Path) -> None:
    """Each row stands alone with no join back to the run table."""
    narrow = frame_rows(run_dir=run_dir, repeat_run_columns=False)
    wide = frame_rows(run_dir=run_dir, repeat_run_columns=True)

    assert "status" not in narrow[0]
    assert wide[0]["status"] == "scenario_complete"


def test_a_run_whose_log_is_missing_does_not_fail_the_others(tmp_path: Path) -> None:
    """One unreadable run must not cost an export every other run's messages."""
    missing = tmp_path / "runs" / SCENARIO / "9999999999"
    missing.mkdir(parents=True)
    frame = build_message_level_frame(
        records=[ExportRunRecord(summary=make_summary(run_dir=missing), report=None)],
        columns=[],
        repeat_run_columns=False,
    )

    assert list(frame.rows) == []


def test_the_frame_reads_back_as_csv(run_dir: Path, tmp_path: Path) -> None:
    """Text cells carry model output, so the round trip through csv is worth pinning."""
    frame = build_message_level_frame(
        records=[ExportRunRecord(summary=make_summary(run_dir=run_dir), report=None)],
        columns=[],
        repeat_run_columns=False,
    )
    path = tmp_path / "message_level.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(frame.header)
        writer.writerows(frame.rows)

    rows = list(csv.DictReader(path.open(newline="")))
    assert [row["text"] for row in rows] == ["AAAA", "second"]


# --- resolving the primary channel across knob-schema drift ---------------------


def test_a_config_predating_a_new_knob_still_resolves_its_primary_channel() -> None:
    """The common case on real data: 50 of 52 container_yard runs here predate two knobs.

    Neither knob has anything to do with which channel is primary, so failing to
    resolve would empty a column for a whole scenario over an unrelated field.
    """
    scenario_cls = get_scenario_class(name="veyru")
    full = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    aged = {key: value for key, value in full.items() if key != "easy_round_numbers"}

    resolved = resolve_primary_channels(scenario_name="veyru", scenario_config=aged)

    assert resolved.resolved
    assert resolved.team_by_channel == {"link": ""}


def test_the_recorded_config_is_tried_before_any_preset_fills_it() -> None:
    """A run that rebuilds on its own config must never be read through a preset's values."""
    scenario_cls = get_scenario_class(name="veyru")
    full = scenario_cls.load_knobs_preset(preset_name="knobs_default")

    [first, *_] = candidate_configs(scenario_cls=scenario_cls, scenario_config=full)

    assert first == full


def test_the_run_own_values_win_over_the_preset_it_is_filled_from() -> None:
    """Backfilling supplies only what a run predates; anything it recorded is its own."""
    scenario_cls = get_scenario_class(name="veyru")
    full = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    aged = {key: value for key, value in full.items() if key != "easy_round_numbers"}
    aged["round_count"] = 3

    [_, backfilled, *_] = candidate_configs(scenario_cls=scenario_cls, scenario_config=aged)

    assert backfilled["round_count"] == 3
    assert "easy_round_numbers" in backfilled


def test_every_preset_is_offered_not_only_the_first() -> None:
    """One backfill can trip a cross-field validator while another still fits."""
    scenario_cls = get_scenario_class(name="veyru")
    full = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    aged = {key: value for key, value in full.items() if key != "easy_round_numbers"}

    candidates = list(candidate_configs(scenario_cls=scenario_cls, scenario_config=aged))

    # The recorded config, plus a backfill from each preset that fills something.
    assert len(candidates) > 2
    assert len(scenario_cls.knobs_preset_names()) > 1


def test_a_scenario_that_is_not_installed_resolves_to_nothing() -> None:
    """Runs of a scenario since removed are still exported, without those columns."""
    resolved = resolve_primary_channels(
        scenario_name="a_scenario_nobody_shipped",
        scenario_config={},
    )

    assert not resolved.resolved
    assert resolved.team_by_channel == {}


def test_a_two_team_scenario_names_the_team_behind_each_channel() -> None:
    """The team dimension a Measurement has no field for is known here from the channel."""
    scenario_cls = get_scenario_class(name="spot_the_difference")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")

    resolved = resolve_primary_channels(scenario_name="spot_the_difference", scenario_config=config)

    assert resolved.resolved
    assert sorted(resolved.team_by_channel.items()) == [("link_a", "team_a"), ("link_b", "team_b")]


# --- the legend -----------------------------------------------------------------


def test_the_legend_carries_units_for_the_message_columns() -> None:
    """Nothing else in the export says what `character_entropy_bits` is measured in."""
    request = CsvExportRequest(
        selection=FilterRunSelection(
            kind="filters",
            scenario=[],
            labels=[],
            run_id_contains=None,
            status=None,
            contains_agent_id=None,
        ),
        frames=[ExportFrame.MESSAGE_LEVEL],
        columns=[],
        metrics=[],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    legend = build_legend_frame(records=[], request=request)
    rows = {row[0]: dict(zip(legend.header, row)) for row in legend.rows}

    assert rows["character_entropy_bits"]["unit"] == "bits/char (lower = more repetitive)"
    assert rows["text"]["group"] == "message_level"
    # Emitted on every row by construction, so a coverage count would answer
    # a question nobody asked of them.
    assert rows["text"]["runs_with_value"] == ""


def test_the_legend_only_describes_the_tables_that_were_written() -> None:
    """A legend naming columns of a table the caller never asked for reads as a bug."""
    request = CsvExportRequest(
        selection=FilterRunSelection(
            kind="filters",
            scenario=[],
            labels=[],
            run_id_contains=None,
            status=None,
            contains_agent_id=None,
        ),
        frames=[ExportFrame.ROUND_LEVEL],
        columns=[],
        metrics=[],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    legend = build_legend_frame(records=[], request=request)
    columns = {row[0] for row in legend.rows}

    assert "round_number" in columns
    assert "text" not in columns
