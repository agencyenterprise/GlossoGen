"""Test a scenario or metric that ships in its own package.

A scenario is only exercised by running one, and running one means an MCP
server, agent sessions, a game clock and an event log. This package supplies all
of that with the LLM replaced by a script, so a test states what each agent does
and asserts on what the platform did with it.

Time is the reason this exists rather than being written per package. A run
waits out `MIN_ROUND_DURATION_SECONDS` after the last message to guess whether
the agents have finished, and counts idle sessions on an interval. A test with
scripted agents knows when they have finished, because it wrote the scripts, so
the harness answers that question directly instead of waiting. It also replaces
the provider-backed token counter, which otherwise posts every message to a
provider for a number no test reads. See "Tests and time" in CLAUDE.md.

Install the extra to get pytest, which `run_simulation` takes a `MonkeyPatch`
from:

    pip install "glossogen[testing] @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"

What a scenario author needs, in order:

- `glossogen validate <name-or-directory>` covers the static contract: channels that
  exist, roles that match the agents, presets that still validate, templates that
  render. It is a command rather than part of this package, so it needs no test
  suite to run. `assert_scenario_is_registered` covers the one thing it cannot,
  that the name resolves to your class and not to somebody else's.
- `run_scenario` / `run_rounds` drive the real round loop with scripted agents,
  and the `assert_*` helpers state what a finished run must contain.

`metric_harness` is the equivalent for a metric: it scores a finished run
through `run_scenario_evaluation`, the same function `glossogen evaluate` calls,
with a stub judge whose answers the test chose.
"""

from glossogen.testing.metric_harness import (
    NO_OPTIONS,
    MetricRun,
    ScoredRun,
    isolated_run,
    ontology_options,
    probe_options,
    score_metrics,
    use_scripted_probe_model,
)
from glossogen.testing.scenario_registration import assert_scenario_is_registered
from glossogen.testing.scenario_runtime import (
    assert_no_agent_crashed,
    assert_postmortem_never_ran,
    assert_postmortem_ran,
    assert_round_loop_completed,
    build_scenario,
    chat_script,
    fast_round_overrides,
    messages_on_primary,
    primary_channel_ids_of,
    run_rounds,
    run_scenario,
)
from glossogen.testing.scripted_agent import (
    SayTurn,
    ScriptedTurn,
    ScriptExhausted,
    ToolTurn,
    build_scripted_model,
)
from glossogen.testing.simulation_harness import (
    SimulationResult,
    always_timed_out,
    free_port,
    never_times_out,
    run_simulation,
)
from glossogen.testing.smoke_scenario import SmokeScenario
from glossogen.testing.stub_llm_provider import RecordedCall, StubLLMProvider

__all__ = [
    "NO_OPTIONS",
    "MetricRun",
    "RecordedCall",
    "SayTurn",
    "ScoredRun",
    "ScriptExhausted",
    "ScriptedTurn",
    "SimulationResult",
    "SmokeScenario",
    "StubLLMProvider",
    "ToolTurn",
    "always_timed_out",
    "assert_no_agent_crashed",
    "assert_postmortem_never_ran",
    "assert_postmortem_ran",
    "assert_round_loop_completed",
    "assert_scenario_is_registered",
    "build_scenario",
    "build_scripted_model",
    "chat_script",
    "fast_round_overrides",
    "free_port",
    "isolated_run",
    "messages_on_primary",
    "never_times_out",
    "ontology_options",
    "primary_channel_ids_of",
    "probe_options",
    "run_rounds",
    "run_scenario",
    "run_simulation",
    "score_metrics",
    "use_scripted_probe_model",
]
