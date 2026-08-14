# Testing a scenario

`glossogen.testing` runs a scenario the way the platform runs it, with the LLM
replaced by a script. It ships in the package, so a scenario in your own
distribution is tested the same way the built-in ones are.

```bash
pip install "glossogen[testing] @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
```

The extra adds pytest and pytest-asyncio. pytest is in the API rather than only
in the tests: `run_simulation` takes a `pytest.MonkeyPatch`, because controlling
the clock is what makes a scenario test deterministic.

Async tests need this in your `pyproject.toml`, or every one of them errors with
"async def functions are not natively supported":

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## The contract comes first, and it is a command

Before any of this, run

```bash
glossogen check-scenario reactor_purge
```

It builds your scenario from every preset it ships and checks the parts
`SimulationScenario` being an ABC cannot: agents claiming channels that do not
exist, `get_agent_roles` disagreeing with the agents `get_agents` builds, presets
that no longer validate, templates that do not render. It reports every failure
rather than the first and exits non-zero, so it belongs in your CI whether or not
you write tests.

The one thing it cannot tell you is that the name found *your* class. A name
already taken by a built-in stays with the built-in, and the collision is only
logged, so `check-scenario` run by the author of a second `veyru` reports a
healthy scenario: the built-in one. That comparison needs the class in hand:

```python
from glossogen.testing import assert_scenario_is_registered

from my_scenarios.reactor_purge.scenario import ReactorPurgeScenario


def test_the_entry_point_resolves_to_this_class() -> None:
    assert_scenario_is_registered(scenario_cls=ReactorPurgeScenario)
```

It reads installed entry-point metadata, so run it against an installed package
rather than a source tree that was never installed.

## The round loop

`check-scenario` proves a scenario builds. It never starts the game clock, so
nothing there notices if the world's state machine, the postmortem phase or the
round verdict breaks. `run_rounds` closes that: MCP server, tool dispatch,
runtime, clock, event logger and your world are all real, and only the model is
scripted.

```python
from pathlib import Path

import pytest

from glossogen.testing import assert_no_agent_crashed, assert_round_loop_completed, run_rounds


async def test_the_round_loop_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = await run_rounds(
        scenario_name="reactor_purge",
        preset_name="knobs_default",
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert_round_loop_completed(result=result, round_count=2)
    assert_no_agent_crashed(result=result)
```

`run_rounds` builds your scenario from the preset you name, so a test exercises a
configuration you actually ship rather than one written for the test. The preset
is a required argument for the same reason `--config` is required on `run`:
nothing picks a configuration on your behalf, and a scenario that ships no
`knobs_default` would otherwise fail on a name it never chose.

It routes each agent to a primary channel it belongs to, read from the scenario
rather than named by the test, so a two-team scenario sends on both team channels
without the test knowing either.

For a script of your own, build the scenario and hand it to `run_scenario`:
`build_scenario`, `chat_script` and `ToolTurn` / `SayTurn` are the pieces. A
`ToolTurn` calls one of your scenario's MCP tools with arguments you choose,
which is how a test drives the world through a state the round verdict depends
on.

`SimulationResult` carries the event log: `of_type`, `messages_on` and
`failed_tool_calls` are what assertions read.

## Why it does not wait

A run waits `MIN_ROUND_DURATION_SECONDS` after the last message to guess whether
the agents have finished, and polls idle sessions on an interval. A test with
scripted agents does not have to guess, because it wrote the scripts, so the
harness answers that question directly rather than sleeping. It also replaces the
provider-backed token counter, which otherwise posts every message to a provider
for a number no test reads.

A test that races real time passes on a quiet machine and fails under load, and
the failure reads as a bug in the code under test. Monkeypatching a duration to a
small number narrows that race without removing it. See "Tests and time" in
[CLAUDE.md](../CLAUDE.md).

## Testing a metric

`metric_harness` scores a finished run through `run_scenario_evaluation`, the
same function `glossogen evaluate` calls, so a metric is exercised across the
JSONL reader, the transcript builder, the registry, the report merge and the cost
accounting rather than against a hand-built list of events.

Only the judge is replaced. Deterministic metrics never notice; LLM-judge metrics
get a `StubLLMProvider` whose answers the test chose, which is usually where the
interesting assertion lives: not what the judge said, but what it was shown.

`SmokeScenario` is a two-agent, one-channel scenario to score against when your
metric is not tied to a domain of your own.
