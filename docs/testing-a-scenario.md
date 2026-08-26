# Testing a scenario

`glossogen.testing` runs a scenario the way the platform runs it, with the LLM
replaced by a script. It ships in the package, so a scenario in your own
distribution is tested the same way the built-in ones are.

```bash
pip install "glossogen[testing] @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
```

Async tests need this in your `pyproject.toml`, or every one of them errors with
"async def functions are not natively supported":

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## The contract check: `glossogen validate`

Run this before writing any test. It reports every failure rather than the
first and exits non-zero, so it belongs in your CI whether or not you write
tests.

```bash
glossogen validate ./reactor-purge   # a directory: no install needed
glossogen validate reactor_purge     # an installed scenario, by name
```

A name resolves through installed entry-point metadata, so the package has to be
installed. A directory is read straight from its own `pyproject.toml`, which is
what to use while editing. The two cannot be confused: a scenario name is a bare
lowercase identifier, so anything holding a dot or a slash is a path.

It builds the scenario from every preset it ships and checks what Python cannot.
Each check catches a failure that is silent at the time it happens:

| Check | The silent failure it catches |
|---|---|
| Agents claim only channels that exist; `get_agent_roles` agrees with the agents built | A roster the web UI and the metrics disagree on |
| Every preset validates; every round's injection renders | A misspelled template variable renders a briefing with a hole in it, and the run looks plausible for fifteen rounds |
| Every event declares a unique `event_type`, and the parser builds over platform events plus yours | A repeated name shadows one side of the parser: the run writes fine and reads back as the other thing |
| `events.py` imports only `glossogen.models.event_base` (checked in source, not by importing) | The event union imports your `events.py` while mid-import, so a wider import fails the whole platform at startup |
| A probe or explanation config points at files that exist | A missing question bank makes that metric family report nothing, exactly like a run with nothing to measure |
| `get_judge_models` is readable | The launch check asks it which credentials a run needs |
| Directory form only: `package-data` covers prompts and presets | Your editable install works and the wheel you hand out renders nothing |
| Directory form only: the entry-point group is `glossogen.scenarios.v1` | Declared under another version, the scenario is not refused, it is absent |
| Directory form only: the package `__init__.py` is empty | Event discovery imports it mid-cycle |
| Directory form only: the name is not already taken | A name held by a built-in stays with the built-in, so validating a second `veyru` *by name* reports the healthy built-in |

It needs no API key. Provider credentials are hidden while each preset builds, so
a scenario that reaches for one at construction fails here rather than in someone
else's environment.

It renders every round's injection rather than only the first, because scenarios swap
templates per round and a template first reached at round 12 would otherwise cost
eleven rounds to discover. What it cannot reach is the branch reading a previous
round's outcome: nothing has been played, so that branch belongs to `run_rounds`.
Two rounds are enough, because round two has a round one behind it.

### The registration check

To compare the class the entry point resolves against your own, which needs the
class in hand rather than a name:

```python
from glossogen.testing import assert_scenario_is_registered

from my_scenarios.reactor_purge.scenario import ReactorPurgeScenario


def test_the_entry_point_resolves_to_this_class() -> None:
    assert_scenario_is_registered(scenario_cls=ReactorPurgeScenario)
```

It reads installed entry-point metadata, so run it against an installed package.

## The prompt linter

`make lint-server` runs `linter/check_prompt_templates.py` over every template in
the repository. It applies to a repository clone only, for scenarios developed
in-tree; a scenario in its own package has no equivalent. It is not
scenario-aware and needs nothing built, so it catches a different set:

| Catch | Otherwise surfaces |
|---|---|
| A template that does not parse | After the run directory is claimed and the agents connected |
| An `{% include %}` naming a partial outside the search directory | Names resolve against that directory, not the including template |
| A template nothing renders or includes | Somebody edits a prompt believing it is live |
| A name in shipped code that no template answers to | At render, in someone else's run |

It does not check undeclared variables: scenarios assemble template variables in
helpers, so the set a template renders with is not decidable from the call site.
`StrictUndefined` answers that exactly, at render. Prompt-sized string literals in
scenario Python are reported as advisory and do not fail the build.

## The round loop

`validate` proves a scenario builds. It never starts the game clock. `run_rounds`
closes that: MCP server, tool dispatch, runtime, clock, event logger and your
world are all real, and only the model is scripted.

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

The preset is required for the same reason `--config` is required on `run`: the
test exercises a configuration you actually ship. Each agent is routed to a primary channel it
belongs to, read from the scenario, so a two-team scenario sends on both team
channels without the test naming either.

Each agent chats exactly once per round. That is paced, not merely budgeted:
every send sits behind a round gate that reads the simulation's own round
counter, so which round a message lands in does not depend on how the machine
schedules the agents' cycles, and two runs place every message identically.

| Piece | For |
|---|---|
| `run_rounds` | The whole loop from a preset name, N rounds of scripted chatter |
| `build_scenario` + `run_scenario` | The same paced chatter against a scenario you built yourself |
| `chat_script`, `ToolTurn`, `SayTurn` | The script: a `ToolTurn` calls one of your MCP tools with arguments you choose, driving the world into a state the round verdict depends on |
| `assert_agents_chatted_every_round` | The paced contract as a check: one primary-channel message per agent per round |
| `SimulationResult` | The event log; `of_type`, `messages_on` and `failed_tool_calls` are what assertions read |

## Why it does not wait

A live run waits `MIN_ROUND_DURATION_SECONDS` after the last message to guess
whether the agents have finished. A test wrote the scripts, so the harness
answers that question directly instead of sleeping, and it replaces the
provider-backed token counter that would otherwise post every message to a
provider. A test that races real time passes on a quiet machine and fails under
load, and the failure reads as a bug in the code under test. See "Tests and time"
in [CLAUDE.md](../CLAUDE.md).

## Testing a metric

`metric_harness` scores a finished run through `run_scenario_evaluation`, the
same function `glossogen evaluate` calls. A metric is exercised across the JSONL
reader, the transcript builder, the registry, the report merge and the cost
accounting rather than against a hand-built list of events.

Only the judge is replaced. Deterministic metrics never notice. LLM-judge metrics
get a `StubLLMProvider` whose answers the test chose. The interesting assertion
is usually about what the judge was shown, since the answers were chosen.
`SmokeScenario` is a two-agent, one-channel scenario to score against when your
metric is not tied to a domain of your own.
