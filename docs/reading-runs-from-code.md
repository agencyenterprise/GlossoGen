# Reading runs from your own code

A script or notebook that reads a run's event log has to load a scenario catalog
first, because which events a run may hold depends on its scenario.

```python
import asyncio
from pathlib import Path

from glossogen.run_storage.event_log_reader import load_events
from glossogen.scenario_contract.catalog import built_in_scenario_sources, load_scenario_catalog

load_scenario_catalog(sources=built_in_scenario_sources())


async def main() -> None:
    events = await load_events(log_path=Path("runs/signal_game/1792075755/signal_game.jsonl"))
    print(len(events))


asyncio.run(main())
```

`glossogen` commands, the server and the testing helpers load a catalog for you.
Code that starts from `python script.py` does not, and a read before one is loaded
raises `ScenarioCatalogNotLoaded`.

## Which catalog to load

| You read | Load |
|---|---|
| Runs of the built-in scenarios | `load_scenario_catalog(sources=built_in_scenario_sources())` |
| Runs of your own scenarios, found as a command run from the same directory would find them | `load_configured_scenario_catalog(cli_sources=(), runs_dirs=())` from `glossogen.scenario_contract.scenario_sources`. It reads `GLOSSOGEN_SCENARIOS` from the process environment and `[tool.glossogen] scenarios` from the nearest `pyproject.toml`, and scans the project when neither is set. It does not read `.env`, which the CLI loads first, so call `load_env_from_working_directory()` (`glossogen.dotenv_loader`) yourself before it if `GLOSSOGEN_SCENARIOS` lives there |
| Runs of your own scenarios, named in the script | `load_configured_scenario_catalog(cli_sources=("my_scenarios",), runs_dirs=())`, which takes the same values as `--scenarios`: a module name, a `.py` file or a folder |

Load once per process. Loading again replaces the current catalog.

## What a read returns

`load_events` parses each line with the platform's events plus the events its
scenario returns from `event_types()`. The scenario is the one the log's first
line, `simulation_started`, names. A log whose first line is anything else raises
`ValueError`.

A line whose `event_type` neither the platform nor that scenario declares comes
back as an `UnrecognizedEvent` (`glossogen.models.event`). This happens when the
run's scenario is not in your catalog, in which case every scenario event is one,
and when the scenario has since dropped or renamed an event type. Each read that
meets any logs one warning with the counts by type.

| Attribute | Value |
|---|---|
| `event_type` | the line's `event_type` string |
| `payload` | the line's decoded JSON object, as a `dict` |
| `event_id`, `timestamp` | read from the line, like any event |
| `round_number` | the line's own, or the round backfilled for a legacy line that lacks one |

Serializing an `UnrecognizedEvent` gives back `payload`. A line the event logger
wrote comes back byte for byte; a line spelled another way (`1e0`, escaped
characters) comes back in orjson's spelling.

Code that iterates a run's events sees these among the typed ones. Dispatch with
`isinstance`, so a branch for a class passes over them, and handle them
explicitly when the question is about what the log holds:

```python
from glossogen.models.event import UnrecognizedEvent

for event in events:
    if isinstance(event, UnrecognizedEvent):
        print(event.event_type, event.round_number, event.payload)
```

Two cases differ. An undeclared line with no `event_id` or no `timestamp`,
which every line the event logger writes has, is skipped and counted in the same
warning. A malformed line of a type the parser does read still raises, so a
corrupt log does not read as a clean one.

The run detail API returns the kept lines as `unrecognized_events`, and the run
page shows them in its timeline ([Web UI](web-ui.md#inside-a-run)).

## Next

- [Exporting runs](exporting-runs.md) for tables over many runs.
- [Analysis and dashboards](analysis.md) for grouped queries without code.
- [Creating a scenario](creating-a-scenario.md) for declaring events in `event_types()`.
