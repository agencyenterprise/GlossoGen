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
glossogen validate ./reactor-purge   # a directory: no install needed
glossogen validate reactor_purge     # an installed scenario, by name
```

It builds your scenario from every preset it ships and checks the parts
`SimulationScenario` being an ABC cannot: agents claiming channels that do not
exist, `get_agent_roles` disagreeing with the agents `get_agents` builds, presets
that no longer validate, templates that do not render. It reports every failure
rather than the first and exits non-zero, so it belongs in your CI whether or not
you write tests.

One command, two ways of saying which scenario. A name is resolved through
installed entry-point metadata, so the package has to be installed; a directory is
read straight from its own `pyproject.toml`, so it works on a tree you have only
just written. While you are editing, that second form is the difference between
reinstalling on every run and not. The two cannot be confused: a scenario name is a
bare lowercase identifier, so anything holding a dot or a slash is a path.

Given a directory, it also checks four things that stop meaning anything once the
package is installed, because installation is what hides them:

- **`package-data` covers your prompts and presets.** Without it only `.py` files
  are packaged. The editable install you are testing against works, and the wheel
  you hand to someone else renders nothing. Checked against the files actually in
  your tree, so `*.jinja` is reported when your prompts are in `prompts/`.
- **The entry-point group names this contract version.** The version lives in the
  group (`glossogen.scenarios.v1`), and a platform reads one of them. Declared
  under another and your scenario is not refused, it is absent.
- **The package `__init__.py` is empty.** Event discovery imports it while the
  event union is mid-import, so anything it pulls in closes that cycle.
- **The name is not already taken.** This is the one thing the name form cannot
  tell you. A name already held by a built-in stays with the built-in and the
  collision is only logged, so validating *by name* as the author of a second
  `veyru` reports a healthy scenario: the built-in one.

Either way it also checks your events and the hooks your metrics read, because
each of those fails silently at the time it happens:

- **Every event type declares its own `event_type`**, and one no platform event and
  no other event of yours already answers to. A repeat shadows one side of the
  parser, so the run writes fine and reads back afterwards as the other thing.
- **The parser builds** over the platform's event types plus yours, which is what
  your finished log will be read with.
- **`events.py` imports only `glossogen.models.event_base`.** Read from the source
  rather than by importing, because `models.event` builds its union by importing
  every scenario's `events` while it is itself mid-import, so by the time that
  import would fail the platform has failed to start.
- **A probe or explanation config points at files that are there.** A missing
  question bank makes every metric in that family report having nothing to measure,
  which is exactly what a run with nothing to measure reports.
- **`get_judge_models` is readable.** Whatever it reports is believed and never
  compared against your knobs: a scenario that scores its rounds without an LLM
  says so and is not asked for a credential it will never spend.

It needs no API key. Provider credentials are hidden while each preset is built, so
a scenario that reaches for one at construction fails here rather than in everyone
else's environment. It checks no model's reachability either: that is checked when
you launch, where the run's own model and provider are known.

### What renders, and what only the round loop can reach

It renders every round's injection, not just the first, because round one is not
representative: scenarios swap templates per round and bring an agent
in partway through, and a template first reached at round 12 otherwise costs the
eleven rounds before it to discover.

It cannot reach the branch that reads a previous round's outcome. Nothing has
been played, so every round renders with none and a template reading one renders
its empty case. That branch belongs to the round loop, which is what `run_rounds`
below is for: two rounds is enough, because round two has a round one behind it.

So `validate` owns templates that do not render and rounds that do not build, and
`run_rounds` owns anything that depends on what happened in an earlier round.

### The prompt linter

`make lint-server` runs `linter/check_prompt_templates.py` over every template in
the repository. It is not scenario-aware and needs nothing built, so it catches a
different set from the command above:

- a template that does not parse, which otherwise surfaces after the run
  directory is claimed and the agents have connected
- an `{% include %}` naming a partial that is not in the directory the renderer
  searches. Names resolve against that directory rather than against the
  including template, so a partial beside a template in `prompts/probe/` is still
  looked for in `prompts/`
- a template nothing renders or includes, which is a prompt somebody edits
  believing it is live
- a name in shipped code that no template answers to

It does not check undeclared variables. Scenarios assemble their template
variables in helpers, so the set a template renders with is not decidable from the
call site, and a rule that guessed would report the templates that are fine.
`StrictUndefined` already answers that exactly, at render.

Prompt-sized string literals in scenario Python are reported as advisory and do
not fail the build.

To compare the resolved class against yours, which is the check that needs the
class in hand rather than a name or a path:

```python
from glossogen.testing import assert_scenario_is_registered

from my_scenarios.reactor_purge.scenario import ReactorPurgeScenario


def test_the_entry_point_resolves_to_this_class() -> None:
    assert_scenario_is_registered(scenario_cls=ReactorPurgeScenario)
```

It reads installed entry-point metadata, so run it against an installed package
rather than a source tree that was never installed.

## The round loop

`validate` proves a scenario builds. It never starts the game clock, so
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
