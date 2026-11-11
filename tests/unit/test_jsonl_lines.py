"""Tests for the shared JSONL line readers and the round-number backfill."""

import orjson
import pytest

from glossogen.run_storage.event_parsing import RoundNumberBackfill
from glossogen.run_storage.jsonl_lines import (
    JsonObjectLines,
    MalformedLine,
    MalformedLineReason,
    first_nonblank_line,
    iter_json_objects_skipping_malformed,
    iter_nonblank_lines,
    rewrite_json_objects,
)


def test_nonblank_lines_are_stripped_and_blank_ones_skipped() -> None:
    lines = [b'  {"a": 1}\n', b"\n", b"   \t\n", b'{"b": 2}  \r\n']

    assert list(iter_nonblank_lines(lines=lines)) == [b'{"a": 1}', b'{"b": 2}']


def test_first_nonblank_line_skips_leading_blank_lines() -> None:
    assert first_nonblank_line(lines=[b"\n", b"  \n", b" first \n", b"second\n"]) == b"first"


def test_first_nonblank_line_is_none_for_blank_input() -> None:
    assert first_nonblank_line(lines=[b"\n", b"   \n"]) is None
    assert first_nonblank_line(lines=[]) is None


def test_first_nonblank_line_reads_no_further_than_that_line() -> None:
    consumed: list[bytes] = []

    def lines() -> object:
        for line in (b"\n", b"first\n", b"second\n"):
            consumed.append(line)
            yield line

    assert first_nonblank_line(lines=lines()) == b"first"  # type: ignore[arg-type]
    assert consumed == [b"\n", b"first\n"]


def test_strict_reader_yields_objects_and_tracks_the_line_they_came_from() -> None:
    reader = JsonObjectLines(lines=[b'{"a": 1}\n', b"\n", b' {"b": [2]} \n'])
    seen: list[tuple[int, dict[str, object]]] = []

    for record in reader:
        seen.append((reader.line_number, record))

    assert seen == [(1, {"a": 1}), (3, {"b": [2]})]


def test_strict_reader_raises_on_a_line_that_is_not_json() -> None:
    reader = iter(JsonObjectLines(lines=[b'{"a": 1}\n', b'{"truncat\n']))

    assert next(reader) == {"a": 1}
    with pytest.raises(orjson.JSONDecodeError):
        next(reader)


def test_strict_reader_raises_type_error_on_json_that_is_not_an_object() -> None:
    with pytest.raises(TypeError, match="line 2 is a JSON list"):
        list(JsonObjectLines(lines=[b"{}\n", b"[1, 2]\n"]))


def test_tolerant_reader_reports_each_skipped_line_and_keeps_the_rest() -> None:
    skipped: list[MalformedLine] = []
    lines = [b'{"a": 1}\n', b'{"truncat\n', b"\n", b"[1]\n", b'{"b": 2}\n', b'"text"\n']

    records = list(iter_json_objects_skipping_malformed(lines=lines, on_malformed=skipped.append))

    assert records == [{"a": 1}, {"b": 2}]
    assert skipped == [
        MalformedLine(line_number=2, text=b'{"truncat', reason=MalformedLineReason.NOT_JSON),
        MalformedLine(line_number=4, text=b"[1]", reason=MalformedLineReason.NOT_OBJECT),
        MalformedLine(line_number=6, text=b'"text"', reason=MalformedLineReason.NOT_OBJECT),
    ]


def test_rewrite_applies_the_transform_and_drops_lines_it_returns_none_for() -> None:
    def transform(record: dict[str, object]) -> dict[str, object] | None:
        if record.get("drop"):
            return None
        record["seen"] = True
        return record

    rewritten = rewrite_json_objects(
        lines=b'{"n": 1}\n\n{"n": 2, "drop": true}\n  {"n": 3}  \n'.split(b"\n"),
        transform=transform,
    )

    assert rewritten.line_count == 2
    assert rewritten.content == b'{"n":1,"seen":true}\n{"n":3,"seen":true}\n'


def test_rewrite_that_keeps_nothing_is_a_single_newline() -> None:
    def drop_everything(record: dict[str, object]) -> None:
        del record

    rewritten = rewrite_json_objects(lines=[b'{"n": 1}'], transform=drop_everything)

    assert rewritten == (b"\n", 0)


def test_rewrite_fails_on_a_line_that_is_not_json() -> None:
    with pytest.raises(orjson.JSONDecodeError):
        rewrite_json_objects(lines=[b"{}", b"nope"], transform=lambda record: record)


def test_backfill_gives_events_the_round_most_recently_advanced() -> None:
    backfill = RoundNumberBackfill()
    records = [
        {"event_type": "simulation_started"},
        {"event_type": "round_advanced", "round_number": 1},
        {"event_type": "message_sent"},
        {"event_type": "round_advanced", "round_number": 2},
        {"event_type": "message_sent"},
    ]

    filled = [backfill.apply(record=record) for record in records]

    assert [record["round_number"] for record in filled] == [0, 1, 1, 2, 2]


def test_backfill_keeps_a_recorded_round_and_does_not_change_the_callers_dict() -> None:
    backfill = RoundNumberBackfill()
    backfill.apply(record={"event_type": "round_advanced", "round_number": 3})
    recorded = {"event_type": "message_sent", "round_number": 7}
    missing = {"event_type": "message_sent"}

    assert backfill.apply(record=recorded) is recorded
    assert backfill.apply(record=missing) == {"event_type": "message_sent", "round_number": 3}
    assert missing == {"event_type": "message_sent"}


def test_backfill_ignores_a_round_advanced_without_an_integer_round() -> None:
    backfill = RoundNumberBackfill()
    backfill.observe(record={"event_type": "round_advanced", "round_number": 2})
    backfill.observe(record={"event_type": "round_advanced", "round_number": "3"})
    backfill.observe(record={"event_type": "round_advanced"})

    assert backfill.apply(record={"event_type": "x"})["round_number"] == 2
