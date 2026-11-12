"""Each run is parsed with the platform's events and its own scenario's, nothing else.

The scenario comes from the run's first line. Two scenarios here, ``alpha`` and
``beta``, declare an event with the same ``event_type``: a run of either reads it
as its own class, which is what a single union over every scenario could not do.
"""

import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any, Literal

import orjson
import pytest

from glossogen.models.event import MessageSent, UnrecognizedEvent, fixed_event_type
from glossogen.models.event_base import EventBase
from glossogen.run_export.message_event_scan import scan_message_events
from glossogen.run_storage import event_parsing
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.event_parsing import (
    ScenarioCatalogNotLoaded,
    parse_event,
    parse_event_bytes,
    run_event_parser,
)
from glossogen.scenario_contract import catalog
from glossogen.scenario_contract.catalog import current_scenario_catalog, scenario_catalog_installed
from glossogen.scenarios.veyru.scenario import VeyruScenario

FIXED_TIME = "2026-01-01T00:00:00+00:00"


class AlphaPing(EventBase):
    """``alpha``'s event."""

    event_type: Literal["ping"] = "ping"
    alpha_field: int


class BetaPing(EventBase):
    """``beta``'s event, under the same ``event_type`` as ``alpha``'s."""

    event_type: Literal["ping"] = "ping"
    beta_field: str


class AlphaScenario(VeyruScenario):
    """A scenario declaring ``AlphaPing``."""

    @classmethod
    def event_types(cls) -> tuple[type[EventBase], ...]:
        return (AlphaPing,)


class BetaScenario(VeyruScenario):
    """A scenario declaring ``BetaPing``."""

    @classmethod
    def event_types(cls) -> tuple[type[EventBase], ...]:
        return (BetaPing,)


@pytest.fixture(autouse=True)
def alpha_and_beta_loaded() -> Generator[None]:
    """Make the process catalog hold ``alpha`` and ``beta`` besides the built-ins."""
    loaded = (
        current_scenario_catalog()
        .including(name="alpha", scenario_cls=AlphaScenario)
        .including(name="beta", scenario_cls=BetaScenario)
    )
    with scenario_catalog_installed(catalog=loaded):
        yield


def row(event_type: str, **fields: Any) -> dict[str, Any]:
    """One raw event row."""
    return {
        "event_id": f"{event_type}-{len(fields)}",
        "event_type": event_type,
        "timestamp": FIXED_TIME,
        "round_number": 1,
        **fields,
    }


def start_row(scenario_name: str) -> dict[str, Any]:
    """The ``simulation_started`` row naming the run's scenario."""
    return row(
        event_type="simulation_started",
        run_id=f"{scenario_name}/1",
        scenario_name=scenario_name,
        scenario_description="",
        channel_ids=["link"],
        scenario_config={},
        provider="anthropic",
    ) | {"round_number": 0}


def message_row(message_id: str) -> dict[str, Any]:
    """A ``message_sent`` row."""
    return row(
        event_type="message_sent",
        token_count=1,
        message={
            "message_id": message_id,
            "channel_id": "link",
            "sender_agent_id": "agent_a",
            "sender_display_name": "Agent A",
            "text": "hi",
            "timestamp": FIXED_TIME,
            "round_number": 1,
        },
    )


def write_log(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write raw JSONL rows."""
    path.write_bytes(b"".join(orjson.dumps(item) + b"\n" for item in rows))
    return path


async def test_a_run_reads_its_own_scenarios_events(tmp_path: Path) -> None:
    log = write_log(
        path=tmp_path / "alpha.jsonl",
        rows=[start_row(scenario_name="alpha"), row(event_type="ping", alpha_field=3)],
    )

    _, ping = await load_events(log_path=log)

    assert isinstance(ping, AlphaPing)
    assert ping.alpha_field == 3


async def test_two_scenarios_may_declare_the_same_event_type(tmp_path: Path) -> None:
    """No reader holds both, so the same name is two different events."""
    log = write_log(
        path=tmp_path / "beta.jsonl",
        rows=[start_row(scenario_name="beta"), row(event_type="ping", beta_field="b")],
    )

    _, ping = await load_events(log_path=log)

    assert isinstance(ping, BetaPing)
    assert ping.beta_field == "b"


async def test_an_event_the_runs_scenario_does_not_declare_is_kept_unrecognized_and_counted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Another scenario's event in this run is not parsed with that scenario's class."""
    log = write_log(
        path=tmp_path / "alpha.jsonl",
        rows=[
            start_row(scenario_name="alpha"),
            row(event_type="veyru_stabilization_judged"),
            row(event_type="veyru_stabilization_judged"),
            message_row(message_id="m1"),
        ],
    )

    with caplog.at_level(logging.WARNING):
        events = await load_events(log_path=log)

    assert [type(event).__name__ for event in events] == [
        "SimulationStarted",
        "UnrecognizedEvent",
        "UnrecognizedEvent",
        "MessageSent",
    ]
    [warning] = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert "scenario 'alpha' does not declare them" in warning.getMessage()
    assert "'veyru_stabilization_judged': 2" in warning.getMessage()


async def test_a_run_whose_scenario_is_not_loaded_reads_its_platform_events_and_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One warning names the missing scenario, rather than one per event type."""
    log = write_log(
        path=tmp_path / "gone.jsonl",
        rows=[
            start_row(scenario_name="gone_scenario"),
            row(event_type="gone_round_opened"),
            message_row(message_id="m1"),
            row(event_type="gone_round_closed"),
            row(event_type="gone_round_opened"),
        ],
    )

    with caplog.at_level(logging.WARNING):
        events = await load_events(log_path=log)

    assert [type(event).__name__ for event in events] == [
        "SimulationStarted",
        "UnrecognizedEvent",
        "MessageSent",
        "UnrecognizedEvent",
        "UnrecognizedEvent",
    ]
    assert [event.event_type for event in events if isinstance(event, UnrecognizedEvent)] == [
        "gone_round_opened",
        "gone_round_closed",
        "gone_round_opened",
    ]
    [warning] = [record for record in caplog.records if record.levelno == logging.WARNING]
    message = warning.getMessage()
    assert "made by scenario 'gone_scenario', which this process has not loaded" in message
    assert "'gone_round_closed': 1" in message
    assert "'gone_round_opened': 2" in message


async def test_a_read_before_any_catalog_has_loaded_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parsing with the platform's events alone would drop every scenario event silently."""
    log = write_log(path=tmp_path / "alpha.jsonl", rows=[start_row(scenario_name="alpha")])

    # Undone inside the test: the fixture that loads alpha and beta restores the
    # process catalog, and must not have this patch undone after it.
    with monkeypatch.context() as patch:
        patch.setattr(event_parsing, "_installed", None)
        with pytest.raises(ScenarioCatalogNotLoaded, match="No scenario catalog has been loaded"):
            await load_events(log_path=log)
        with pytest.raises(ScenarioCatalogNotLoaded):
            parse_event(raw=start_row(scenario_name="alpha"), scenario_name="alpha")


def test_a_single_event_is_parsed_with_the_scenario_it_is_given() -> None:
    raw = row(event_type="ping", alpha_field=1)

    assert isinstance(parse_event(raw=raw, scenario_name="alpha"), AlphaPing)
    assert isinstance(
        parse_event_bytes(
            raw_bytes=orjson.dumps(row(event_type="ping", beta_field="x")), scenario_name="beta"
        ),
        BetaPing,
    )


def test_a_single_event_its_scenario_does_not_declare_is_unrecognized() -> None:
    raw = row(event_type="ping", alpha_field=1)

    event = parse_event(raw=raw, scenario_name="veyru")

    assert isinstance(event, UnrecognizedEvent)
    assert event.event_type == "ping"
    assert event.model_dump(mode="json") == raw


def test_a_malformed_event_of_a_declared_type_still_raises() -> None:
    with pytest.raises(ValueError):
        parse_event(raw=row(event_type="ping", alpha_field="not a number"), scenario_name="alpha")


def test_the_parser_is_built_once_per_scenario() -> None:
    assert run_event_parser(scenario_name="alpha") is run_event_parser(scenario_name="alpha")
    assert run_event_parser(scenario_name="alpha") is not run_event_parser(scenario_name="beta")


def test_the_message_scan_reads_the_scenario_from_the_first_line(tmp_path: Path) -> None:
    log = write_log(
        path=tmp_path / "alpha.jsonl",
        rows=[start_row(scenario_name="alpha"), message_row(message_id="m1")],
    )

    scan = scan_message_events(log_path=log)

    assert [event.message.message_id for event in scan.messages] == ["m1"]
    assert all(isinstance(event, MessageSent) for event in scan.messages)


def test_the_message_scan_refuses_a_log_without_a_start_event(tmp_path: Path) -> None:
    log = write_log(path=tmp_path / "orphan.jsonl", rows=[message_row(message_id="m1")])

    with pytest.raises(ValueError, match="First event is not SimulationStarted"):
        scan_message_events(log_path=log)


def test_restoring_no_catalog_leaves_the_readers_without_a_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A block that installs a catalog in a process that had none puts that state back."""
    loaded = current_scenario_catalog()

    with monkeypatch.context() as patch:
        patch.setattr(catalog, "_current", None)
        patch.setattr(event_parsing, "_installed", None)
        with scenario_catalog_installed(catalog=loaded):
            assert run_event_parser(scenario_name="alpha").scenario_loaded
        with pytest.raises(ScenarioCatalogNotLoaded):
            run_event_parser(scenario_name="alpha")


def test_a_single_event_without_rounds_is_given_round_zero_and_its_message_the_same() -> None:
    """Logs from before ``round_number`` was on every event still parse one line at a time."""
    raw = message_row(message_id="m1")
    del raw["round_number"]
    del raw["message"]["round_number"]

    event = parse_event(raw=raw, scenario_name="alpha")

    assert isinstance(event, MessageSent)
    assert event.round_number == 0
    assert event.message.round_number == 0


class StringTyped(EventBase):
    """A string ``event_type`` with a string default: nothing can dispatch on it."""

    event_type: str = "string_typed"


class Mismatched(EventBase):
    """A literal that disagrees with its default."""

    event_type: Literal["one"] = "other"  # pyright: ignore[reportAssignmentType]


@pytest.mark.parametrize(
    ("event_cls", "expected"),
    [(AlphaPing, "ping"), (StringTyped, None), (Mismatched, None)],
)
def test_only_a_literal_matching_its_default_is_a_fixed_event_type(
    event_cls: type[EventBase], expected: str | None
) -> None:
    assert fixed_event_type(event_cls=event_cls) == expected
