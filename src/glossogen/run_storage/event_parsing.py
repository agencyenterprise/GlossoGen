"""Event parsing for JSONL log readers, with one parser per scenario.

A run logs the platform's events and the events its own scenario declares, and
its first line, ``simulation_started``, names that scenario. A run is parsed with
exactly those types: :func:`run_event_parser` returns the parser for a scenario
name, and :func:`parse_event` / :func:`parse_event_bytes` parse one event of a
run with it. A line of any other ``event_type`` is read into an
:class:`~glossogen.models.event.UnrecognizedEvent` that keeps the line as logged.

Which event types a scenario declares is answered by a lookup the scenario
catalog installs when it loads (:func:`install_scenario_event_types`). This
module never imports scenario code. A read before any lookup is installed raises
:class:`ScenarioCatalogNotLoaded`. A scenario the lookup does not know gets a
parser over the platform's events alone.

``round_number`` is required on every event but older JSONL logs predate
its promotion to ``EventBase`` and lack it on lifecycle events. When
parsing a single event in isolation (e.g. the first/last line of a log)
we default missing ``round_number`` to ``0``. Readers that walk a whole log
pass each line through ``RoundNumberBackfill`` first, which tracks the running
round across the file and backfills with the correct value.
"""

from collections.abc import Callable
from typing import Any, NamedTuple

import orjson
from pydantic import TypeAdapter

from glossogen.models.event import (
    SimulationEvent,
    UnrecognizedEvent,
    core_event_types,
    fixed_event_type,
    parser_for,
)
from glossogen.models.event_base import EventBase

ScenarioEventTypesLookup = Callable[[str], tuple[type[EventBase], ...] | None]
"""Answers the event types a scenario declares, by scenario name, or None for an unknown one."""

_SIMULATION_STARTED = "simulation_started"


class ScenarioCatalogNotLoaded(RuntimeError):
    """Raised by a scenario lookup, or a run read, made before this process loaded its catalog."""


class RunEventParser(NamedTuple):
    """The parser for one scenario's runs, and which event types it reads.

    ``scenario_loaded`` is False when this process has no scenario by that name:
    the parser then reads the platform's events only, and every scenario event of
    the run is an :class:`~glossogen.models.event.UnrecognizedEvent`.
    """

    scenario_name: str
    scenario_loaded: bool
    adapter: TypeAdapter[EventBase]
    event_types: frozenset[str]

    def declares(self, event_type: str) -> bool:
        """Return whether ``event_type`` is a platform event or one this scenario declares."""
        return event_type in self.event_types

    def parse(self, raw: dict[str, Any]) -> SimulationEvent:
        """Validate a raw event dict into a typed event, backfilling legacy round numbers.

        An event whose ``event_type`` this parser does not declare is returned as an
        :class:`~glossogen.models.event.UnrecognizedEvent` holding ``raw`` unchanged.
        A declared event that does not validate raises.

        Backfills two fields that older JSONL logs may omit:

        - the event's own ``round_number`` (promoted to ``EventBase`` after the
          original schema), defaulted to ``0`` for lifecycle events when missing;
        - the ``round_number`` on the nested ``message`` of a ``message_sent``
          event, defaulted to the parent event's ``round_number`` when missing.

        Single-event callers rely on this default; full-log loaders that track
        the running round across the file (e.g.
        ``glossogen.run_storage.event_log_reader.load_events``) pass each record
        through :class:`RoundNumberBackfill` first.
        """
        event_type = raw.get("event_type")
        if isinstance(event_type, str) and not self.declares(event_type=event_type):
            return UnrecognizedEvent.from_record(
                record=raw, round_number=raw.get("round_number", 0)
            )
        if "round_number" not in raw:
            raw = {**raw, "round_number": 0}
        if raw.get("event_type") == "message_sent":
            message = raw.get("message")
            if isinstance(message, dict) and "round_number" not in message:
                raw = {**raw, "message": {**message, "round_number": raw["round_number"]}}
        return self.adapter.validate_python(raw)


class _InstalledLookup(NamedTuple):
    """The installed lookup and the parsers built from it so far, by scenario name."""

    lookup: ScenarioEventTypesLookup
    parsers: dict[str, RunEventParser]


_installed: _InstalledLookup | None = None


def install_scenario_event_types(lookup: ScenarioEventTypesLookup | None) -> None:
    """Make ``lookup`` answer which event types each scenario declares, or remove it.

    Called by the scenario catalog whenever it becomes the process's current one.
    Parsers built from a previous lookup are dropped.
    """
    global _installed
    if lookup is None:
        _installed = None
        return
    _installed = _InstalledLookup(lookup=lookup, parsers={})


def run_event_parser(scenario_name: str) -> RunEventParser:
    """Return the parser for runs of ``scenario_name``, building it on first use.

    Raises :class:`ScenarioCatalogNotLoaded` when no scenario catalog has
    installed its lookup yet.
    """
    installed = _installed
    if installed is None:
        raise ScenarioCatalogNotLoaded(
            "No scenario catalog has been loaded in this process, so no run can be "
            "parsed yet: which events a run may hold depends on its scenario. The "
            "glossogen CLI loads the catalog before running a command; code that runs "
            "outside the CLI calls "
            "glossogen.scenario_contract.catalog.load_scenario_catalog first."
        )
    cached = installed.parsers.get(scenario_name)
    if cached is not None:
        return cached
    declared = installed.lookup(scenario_name)
    event_types = (*core_event_types(), *(declared or ()))
    parser = RunEventParser(
        scenario_name=scenario_name,
        scenario_loaded=declared is not None,
        adapter=parser_for(event_types=event_types),
        event_types=frozenset(
            discriminator
            for discriminator in (fixed_event_type(event_cls=cls) for cls in event_types)
            if discriminator is not None
        ),
    )
    installed.parsers[scenario_name] = parser
    return parser


def scenario_name_of_run(first_record: dict[str, Any], origin: str) -> str:
    """Return the scenario a run's first record names.

    Raises ValueError when the record is not a ``simulation_started`` naming a
    scenario. ``origin`` names the log in the message.
    """
    scenario_name = first_record.get("scenario_name")
    if first_record.get("event_type") != _SIMULATION_STARTED or not isinstance(scenario_name, str):
        raise ValueError(f"First event is not SimulationStarted in {origin}")
    return scenario_name


class RoundNumberBackfill:
    """Gives each event of a legacy log the round it was emitted in.

    Logs written before ``round_number`` was promoted to ``EventBase`` omit it.
    Walking the log in order, the round an event belongs to is the one most
    recently opened by a ``round_advanced``, and ``0`` before the first. One
    instance covers one pass over one log.
    """

    def __init__(self) -> None:
        self._running_round = 0

    def observe(self, record: dict[str, Any]) -> None:
        """Advance the running round when ``record`` is a ``round_advanced`` with an integer one."""
        if record.get("event_type") == "round_advanced":
            advanced = record.get("round_number")
            if isinstance(advanced, int):
                self._running_round = advanced

    def apply(self, record: dict[str, Any]) -> dict[str, Any]:
        """Observe ``record``, then return it with ``round_number`` set when it had none.

        A record that already carries one is returned as it is; one that lacks it
        is copied, so the caller's dict is never changed.
        """
        self.observe(record=record)
        if "round_number" in record:
            return record
        return {**record, "round_number": self._running_round}


def parse_event(raw: dict[str, Any], scenario_name: str) -> SimulationEvent:
    """Validate one raw event of a ``scenario_name`` run into a typed event.

    See :meth:`RunEventParser.parse` for the fields it backfills.
    """
    return run_event_parser(scenario_name=scenario_name).parse(raw=raw)


def parse_event_bytes(raw_bytes: bytes, scenario_name: str) -> SimulationEvent:
    """Parse one JSON-encoded event of a ``scenario_name`` run into a typed event."""
    return parse_event(raw=orjson.loads(raw_bytes), scenario_name=scenario_name)
