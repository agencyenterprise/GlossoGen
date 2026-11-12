"""Reading a run back off disk.

The JSONL event log is the only durable record of a run, so everything that
inspects a finished simulation comes through here: the CLI, the web server, the
metrics, and the fork and resume flows. Reconstruction works off the events
alone, which is what lets a run be evaluated or resumed long after the process
that wrote it exited.

What the events do not carry cannot come back. ``AgentRegistered`` records no
compaction settings, so a rebuilt ``AgentConfig`` reports the default rather
than what the agent ran with.

A log is parsed with the platform's events and the events its own scenario
declares, the scenario its first line names. Any other event is read into an
``UnrecognizedEvent`` holding the line as logged, and counted in one warning: a
log can name a scenario this process has not loaded, or an event its scenario no
longer declares, and neither should cost the reader the rest of the run or the
events themselves. A malformed event of a type the parser does read still
raises, so this does not quietly swallow a corrupt log.
"""

import asyncio
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from glossogen.model_catalog.provider_catalog import Provider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.compaction_config import CompactionConfig
from glossogen.models.event import (
    AgentRegistered,
    SimulationEvent,
    SimulationStarted,
    UnrecognizedEvent,
)
from glossogen.run_storage.event_parsing import (
    RoundNumberBackfill,
    RunEventParser,
    run_event_parser,
    scenario_name_of_run,
)
from glossogen.run_storage.jsonl_lines import JsonObjectLines
from glossogen.run_storage.run_archive import strip_legacy_git_dir

logger = logging.getLogger(__name__)


def _read_and_parse_events(log_path: Path) -> list[SimulationEvent]:
    """Read and parse a JSONL log synchronously.

    Both the file read and the per-line ``orjson`` + Pydantic parse are
    CPU-bound; :func:`load_events` runs this in a worker thread so the parse
    never blocks the server event loop. Raises ValueError when the first line is
    not a ``simulation_started``, since that line names the scenario whose events
    the rest is parsed with.
    """
    strip_legacy_git_dir(run_dir=log_path.parent)
    events: list[SimulationEvent] = []
    unrecognized: Counter[str] = Counter()
    parser: RunEventParser | None = None
    round_numbers = RoundNumberBackfill()
    with open(log_path, mode="rb") as f:
        for record in JsonObjectLines(lines=f):
            if parser is None:
                parser = run_event_parser(
                    scenario_name=scenario_name_of_run(first_record=record, origin=str(log_path))
                )
            backfilled = round_numbers.apply(record=record)
            event_type = record.get("event_type")
            if isinstance(event_type, str) and not parser.declares(event_type=event_type):
                unrecognized[event_type] += 1
                events.append(
                    UnrecognizedEvent.from_record(
                        record=record, round_number=backfilled["round_number"]
                    )
                )
                continue
            events.append(parser.parse(raw=backfilled))
    logger.info("Loaded %d events from %s", len(events), log_path)
    if parser is not None and unrecognized:
        _warn_unrecognized(log_path=log_path, parser=parser, unrecognized=unrecognized)
    return events


def _warn_unrecognized(log_path: Path, parser: RunEventParser, unrecognized: Counter[str]) -> None:
    """Log one warning for the events a read kept unrecognized, with their counts by type."""
    if not parser.scenario_loaded:
        logger.warning(
            "Read %d event(s) of %s as UnrecognizedEvent: the run was made by scenario "
            "%r, which this process has not loaded, so only the platform's events are "
            "parsed. Counts by type: %s",
            sum(unrecognized.values()),
            log_path,
            parser.scenario_name,
            dict(sorted(unrecognized.items())),
        )
        return
    logger.warning(
        "Read %d event(s) of %s as UnrecognizedEvent: scenario %r does not declare them "
        "in event_types(). Counts by type: %s",
        sum(unrecognized.values()),
        log_path,
        parser.scenario_name,
        dict(sorted(unrecognized.items())),
    )


async def load_events(log_path: Path) -> list[SimulationEvent]:
    """Read a JSONL log file and parse each line into a typed SimulationEvent.

    Older JSONL files were written before ``round_number`` was promoted to
    ``EventBase``. This loader backfills the field for every event that
    lacks it, tracking the most recent ``RoundAdvanced`` while walking the
    log so each event receives the round it was emitted in. Lifecycle
    events emitted before round 1 (``simulation_started``,
    ``agent_registered``) get ``round_number=0``. The parser further
    backfills the ``round_number`` on the nested ``message`` payload of
    ``message_sent`` events from the parent event's ``round_number`` for
    runs that predate per-message round tagging.

    The log is parsed with the platform's events and those of the scenario its
    first line names; an event of any other type is returned as an
    ``UnrecognizedEvent`` and counted in one warning.

    Runs the read + parse in a worker thread so the CPU-bound work does not
    block the event loop.
    """
    return await asyncio.to_thread(_read_and_parse_events, log_path)


def extract_agent_configs(events: list[SimulationEvent]) -> list[AgentConfig]:
    """Rebuild each agent's config from the ``AgentRegistered`` event it emitted.

    ``compaction`` is not recorded in that event, so every rebuilt config claims
    the default (disabled). Callers that care what compaction a run actually used
    must read the ``ContextCompacted`` events instead of trusting this field.
    """
    configs: list[AgentConfig] = []
    for event in events:
        if isinstance(event, AgentRegistered):
            configs.append(
                AgentConfig(
                    agent_id=event.agent_id,
                    role_name=event.role_name,
                    system_prompt=event.system_prompt,
                    channel_ids=event.channel_ids,
                    tool_names=event.tool_names,
                    model=event.model,
                    provider=Provider(event.provider),
                    compaction=CompactionConfig(),
                    model_settings=event.model_settings,
                )
            )
    return configs


def extract_simulation_id(events: list[SimulationEvent]) -> str:
    """Find and return the simulation ID from a SimulationStarted event.

    Raises ValueError if no SimulationStarted event is found.
    """
    for event in events:
        if isinstance(event, SimulationStarted):
            return event.event_id
    raise ValueError("No SimulationStarted event found in events")


def extract_scenario_config(events: list[SimulationEvent]) -> dict[str, Any]:
    """Extract the scenario_config dict from the SimulationStarted event.

    Raises ValueError if no SimulationStarted event is found.
    """
    for event in events:
        if isinstance(event, SimulationStarted):
            return dict(event.scenario_config)
    raise ValueError("No SimulationStarted event found in events")
