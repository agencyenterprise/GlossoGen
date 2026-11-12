# Testing a scenario

`glossogen.testing` runs a scenario the way the platform runs it, with the LLM
replaced by a script. It ships in the package, so a scenario in your own
project is tested the same way the built-in ones are.

```bash
pip install "glossogen[testing] @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
```

The extra installs `pytest-asyncio`. Mark each async test
`@pytest.mark.asyncio`, as the test `new-scenario` writes does, or set
`asyncio_mode = "auto"` in your pytest configuration. An unmarked async test
without that setting errors with "async def functions are not natively
supported".

## The contract check: `glossogen validate`

Run this before writing any test. It reports every failure rather than the
first and exits non-zero, so it belongs in your CI whether or not you write
tests.

```bash
glossogen validate ./reactor_purge    # a file or folder: loaded as one more source
glossogen validate reactor_purge      # a scenario your sources load, by name
```

A name resolves through the scenarios this process loaded from its configured
sources. A path is loaded as one more source on top of those, and every scenario
it registers is checked, which is what to use while editing. An argument that
holds a dot or a slash is always a path. A bare identifier is read as a loaded
scenario's name first, and as a path only when no loaded scenario has that name.
With the layout `new-scenario` writes, `reactor_purge` is both a scenario and a
folder, so `validate reactor_purge` checks the loaded scenario and prints a note;
write `./reactor_purge` to check the folder.

It builds the scenario from every preset it ships and checks what Python cannot.
Each check catches a failure that is silent at the time it happens:

| Check | The silent failure it catches |
|---|---|
| Agents claim only channels that exist; `get_agent_roles` agrees with the agents built | A roster the web UI and the metrics disagree on |
| Every preset validates; every round's injection renders | A misspelled template variable renders a briefing with a hole in it, and the run looks plausible for fifteen rounds |
| Every event declares a unique `event_type`, and the parser builds over platform events plus yours | A repeated name shadows one side of the parser: the run writes fine and reads back as the other thing |
| Every event class defined in the scenario's module or package is returned by `event_types()` | The event logger refuses an undeclared class mid-run, and a reader reads its lines as `UnrecognizedEvent` |
| A probe or explanation config points at files that exist | A missing question bank makes that metric family report nothing, exactly like a run with nothing to measure |
| `get_judge_models` is readable | The launch check asks it which credentials a run needs |
| Path form only, when the project's `pyproject.toml` has a `[build-system]`: setuptools `package-data` covers prompts and presets | The source tree works and the wheel you hand out renders nothing |

It needs no API key. Provider credentials are hidden while each preset builds, so
a scenario that reaches for one at construction fails here rather than in someone
else's environment.

It renders every round's injection rather than only the first, because scenarios swap
templates per round and a template first reached at round 12 would otherwise cost
eleven rounds to discover. What it cannot reach is the branch reading a previous
round's outcome: nothing has been played, so that branch belongs to `run_rounds`.
Two rounds are enough, because round two has a round one behind it.

### The registration check

A test that imports your scenario class registers it whether or not your
project's scenario sources would load it. These check the catalog those sources
load instead, from the directory pytest runs in. By name, which is what the test
`new-scenario` writes uses, so it imports nothing from the scenario's folder:

```python
from glossogen.testing import assert_scenario_is_loaded


def test_the_scenario_sources_load_this_scenario() -> None:
    assert_scenario_is_loaded(scenario_name="reactor_purge")
```

It fails with the message a command gives for a scenario that is not loaded,
listing the sources that were. `assert_scenario_is_registered(scenario_cls=...)`
checks a class you imported instead: that the name resolves to that class. The
same file imported under another module name counts as the same class, so a test
under `src/` may import `mypack.reactor_purge.reactor_purge` while the project
scan loaded it as `src.mypack.reactor_purge.reactor_purge`. It fails, saying to add the file or folder to `[tool.glossogen] scenarios`, when
the sources leave the class out.

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
closes that: tool dispatch, runtime, clock, event logger and your world are all
real, and only the model is scripted.

```python
from pathlib import Path

import pytest

from glossogen.testing import assert_no_agent_crashed, assert_round_loop_completed, run_rounds


@pytest.mark.asyncio
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
| `chat_script`, `ToolTurn`, `SayTurn` | The script: a `ToolTurn` calls one of your tools with arguments you choose, driving the world into a state the round verdict depends on |
| `assert_agents_chatted_every_round` | The paced contract as a check: one primary-channel message per agent per round |
| `SimulationResult` | The event log as typed events, your scenario's own included; `of_type(event_type=RoundResultRecorded)`, `messages_on` and `failed_tool_calls` are what assertions read |

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
