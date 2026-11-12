# Creating a metric

A metric scores a finished run. It reads the run's event log, optionally calls an
LLM judge, and returns one or more `Measurement` entries that land in
`<scenario>_report.json`.

A metric written against the [scenario hooks](#scenario-hooks), rather than
against one scenario's own events, works on scenarios you did not write, and is
added to this repo as a generic metric. A metric can also be scoped to a single
scenario, reading that scenario's own events and returned from its
`scenario_metrics()`; the [registration section](#registering-it) covers both
shapes, in this repo and in your own project.

## Before you write one

Check whether the platform already measures it. The generic metrics cover
round success, per-round and per-message character throughput, perplexity and
n-gram surprisal, compression ratio, message entropy, the language-emergence
judges, protocol probing and explanation, round-end triggers, and content-filter
refusals. [Evaluation](evaluation.md#metrics) lists them all with what each
`score` means.

Two questions decide the shape of what you write:

- **Does it need an LLM?** Deterministic metrics ignore the `llm_provider`
  argument and are bit-reproducible. Judge-driven metrics are not, so they
  usually average several replicas and pin the judge model.
- **Does it apply to every run?** A metric that only makes sense for some runs
  returns an empty list for the others. See "Not applying is not a zero" below.

## The contract

One method, defined in
[metric_protocol.py](../src/glossogen/scenario_contract/metric_protocol.py):

```python
class Metric(ABC):
    name: str

    @abstractmethod
    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]: ...
```

| Argument | Holds |
|---|---|
| `name` | What callers pass to `--metrics`, and the key the report is written under. Must be unique |
| `events` | The full ordered event log, already parsed |
| `scenario` | The built scenario: ask it which channels it scores (`get_primary_channels()`, widened by `scored_channel_ids`), how it renders a round (`build_communication_rounds`), anything on its contract. Typed `ScenarioBase` ([scenario_base.py](../src/glossogen/scenario_contract/scenario_base.py)), the part of the contract a metric reads; annotate your override the same way |
| `llm_provider` | The judge selected by `evaluate --model/--provider`; deterministic metrics ignore it |
| `run_dir` | The run directory, for writing a sidecar next to the report |
| `options` | Per-invocation flags the CLI passes through; most metrics ignore it |

A `Measurement` is `metric_name`, `score` (float), `score_unit` (free-form label),
`summary` (one line), `per_round` and `per_agent` (structured breakdowns).

Return more than one `Measurement` when your metric splits by partition. The
convention for teams is `PrimaryChannel.metric_name(base)`, which yields
`base` for a single-team run and `base_team_a` for a multi-team one, so a
single metric reports each team separately without inventing its own naming.

### Not applying is not a zero

If your metric cannot say anything about a run, return `[]` and log one
INFO-level skip line. Do not return a zero-score `Measurement` with a "does not
apply" summary: nothing downstream can tell that zero apart from a real zero, and
averaging across runs then quietly mixes the two.

Return a zero score only when zero is a genuine observation. `content_filter_refusal`
scoring `0` means the run had no refusals, which is a finding.

### Numbers that are neither per-round nor per-agent

A `Measurement` holds a run-level `score`, `per_round`, and `per_agent`. A metric
that measures along some other axis (one number per ontology category, per probe
question, per message) fits none of those, and the usual answer is a sidecar file
in `run_dir` beside the report.

Write the sidecar, then implement `read_keyed_observations` so those numbers can be
charted and aggregated across runs:

```python
async def read_keyed_observations(self, run_dir: Path) -> list[KeyedObservation]:
    """Return one confidence per category, keyed by category."""
    path = run_dir / _SIDECAR_FILENAME
    sidecar = await read_json_sidecar(path=path)
    if sidecar is None:
        return []
    observations: list[KeyedObservation] = []
    for raw in object_rows(value=sidecar.get("scores")):
        try:
            score = CategoryConfidence.model_validate(raw)
        except ValidationError:
            logger.exception("Skipping a malformed score in %s", path)
            continue
        observations.append(
            KeyedObservation(keys={"category_id": score.category_id}, value=score.confidence)
        )
    return observations
```

Read each row back with the model that wrote it. A row that does not validate costs
that row and is logged, so a field renamed in the writer shows up as a skip rather
than as a default value entering a mean.

Each key becomes a groupable dimension on the
[analysis surface](analysis.md#the-query-model), prefixed `key.`: the example
above charts as `key.category_id`.

## Scenario hooks

A metric stays scenario-agnostic by asking the scenario, rather than the event
log, for anything scenario-specific. The hooks live on `ScenarioBase`:
`judge_round_result` and `get_primary_channels` are abstract, so every scenario
has them. The rest are optional. A metric whose hook is absent returns nothing,
except `protocol_explanation`, which falls back to a generic prompt.

| Hook | Read by |
|---|---|
| `judge_round_result` (required) | `round_success`, `round_success_after_resume` |
| `get_primary_channels` (required) | `perplexity`, the language and throughput metrics, the communication-style judges |
| `build_communication_rounds` | `communication_open_coding`, `communication_feature_presence`, `protocol_learned_after_swap` |
| `detect_protocol_boundary_window` | `protocol_learned_after_swap`. Defaults to the first `AgentSwappedMidRun`; override it to also detect a boundary such as an intern takeover or a two-team observer swap |
| `get_protocol_probe_config` | the `protocol_probe*` metrics |
| `get_protocol_explanation_config` | per-role prompts for `protocol_explanation` |

Every generic metric is platform code reading scenario data through these hooks,
which is why a scenario in someone else's package gets the whole suite, and why
a metric you write the same way does too.

## Writing one

[mcr_metric.py](../src/glossogen/evaluation/metrics/mcr_metric.py) is the
smallest complete example: deterministic, reads `MessageSent` events on the
scenario's primary channels, emits one `RoundObservation` per round plus a mean.
Copy its shape. This one, saved as `word_count_metric.py` beside your scenario's
module, runs as written:

```python
"""A word-count metric for reactor_purge."""

import logging
from pathlib import Path

from glossogen.evaluation.metric_core.primary_channel_messages import (
    collect_primary_messages_by_round,
    transmitted_text,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.measurement import Measurement
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.metric_run_options import MetricRunOptions
from glossogen.scenario_contract.scenario_base import ScenarioBase
from glossogen.scenario_contract.scored_channels import scored_channel_ids

logger = logging.getLogger(__name__)


class ExternalWordCountMetric(Metric):
    """Mean words per message on each of the scenario's primary channels."""

    name = "external_word_count"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        _ = agent_configs, llm_provider, run_dir, options
        measurements: list[Measurement] = []
        for channel in scenario.get_primary_channels():
            channel_ids = scored_channel_ids(primary=channel, scenario=scenario, events=events)
            counts = [
                len(text.split())
                for round_messages in collect_primary_messages_by_round(
                    events=events, channel_ids=channel_ids, text_of=transmitted_text
                )
                for text in round_messages.texts
            ]
            if not counts:
                logger.info("%s: no messages on %s, skipping", self.name, channel.channel_id)
                continue
            mean = sum(counts) / len(counts)
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=mean,
                    score_unit="words/message",
                    summary=f"{mean:.2f} words per message across {len(counts)} messages",
                    per_round=[],
                    per_agent=[],
                )
            )
        return measurements
```

Build the channel set with `scored_channel_ids` from
[scored_channels.py](../src/glossogen/scenario_contract/scored_channels.py),
not from `channel_id` alone. A primary channel with `includes_direct_channels`
also owns the direct channels its members open during the run, and a metric that
reads only `channel_id` misses that traffic.
[primary_channel_messages.py](../src/glossogen/evaluation/metric_core/primary_channel_messages.py)
groups the messages on those channels by round.

If your metric writes a sidecar (per-message factors, probe responses, an
ontology), write it into `run_dir` next to the report and name it after the
metric, the way `language_repetition_messages.jsonl` and
`protocol_probe_responses.jsonl` do.

For a judge-driven metric: put the prompt in a Jinja template rather than a
Python string, average several replicas rather than trusting one call, and keep
the judge fixed across runs you intend to compare. This repo's convention is
`claude-haiku-4-5-20251001` on `anthropic`.

## Registering it

### In this repo

Two edits, both in
[metric_core](../src/glossogen/evaluation/metric_core/):

1. Add the class to `_GENERIC_METRICS` in
   [metric_registry.py](../src/glossogen/evaluation/metric_core/metric_registry.py).
   `GENERIC_METRIC_REGISTRY` is derived from that list by each class's `name`.
2. Add the name to `GENERIC_METRIC_NAMES` in
   [generic_metric_names.py](../src/glossogen/evaluation/metric_core/generic_metric_names.py).

The second list exists so that listing the metrics a scenario offers does not
import every metric class. A test asserts the two lists match, so forgetting
either edit fails there. At launch the symptom would have been a metric the CLI
runs and the API rejects.

If the metric only makes sense for one scenario, neither list is touched. The
scenario returns the class from `scenario_metrics()`, and the module defining it
can live anywhere, usually that scenario's `evaluation/` directory. Add these
imports to the scenario's module:

```python
from collections.abc import Sequence

from glossogen.scenario_contract.metric_protocol import Metric

from .word_count_metric import ExternalWordCountMetric
```

and this method inside the existing scenario class, keeping everything else in
it:

```python
    @classmethod
    def scenario_metrics(cls) -> Sequence[type[Metric]]:
        return (ExternalWordCountMetric,)
```

That makes it offered and runnable for that scenario's runs and for no other's:
`evaluate` on another scenario's run treats the name as unknown. Its name must not
repeat a generic metric's, which `validate` checks. Prefer a generic metric that
reads a scenario hook: every scoring concept the platform has ended up expressible
that way.

### In your own project

A metric outside glossogen belongs to a scenario outside glossogen. Define it in
your project and return it from your scenario's `scenario_metrics()`, exactly as
above. glossogen loads your scenario from its configured sources (see
[In this repo, or in your own package](creating-a-scenario.md#in-this-repo-or-in-your-own-package)),
and the metric comes with it: `evaluate` runs it on that scenario's runs, and
`glossogen serve` lists it among that scenario's metrics.

There is no way to add a metric to every scenario's runs from outside
glossogen. A metric that applies to every scenario is a generic one, added in
this repo.

## Running it

Same command either way. The metric name goes in the comma-separated `--metrics`
list:

```bash
glossogen evaluate <scenario> \
  --run-dir ./runs/<scenario>/<timestamp> \
  --metrics external_word_count,round_success,mean_chars_per_round \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  > ./runs/<scenario>/<timestamp>/eval_stdout.log 2>&1 &
```

`<scenario>` is the scenario that returns the metric from `scenario_metrics()`;
the metric is unknown to any other. From a checkout, spell each command
`VIRTUAL_ENV= uv run --no-sync python -m glossogen ...`.

**Only evaluate a run that has emitted `simulation_ended`.** Gating on a round
count instead scores a run whose last round is still in flight, and the missing
round is silent in the report:

```bash
grep -q '"simulation_ended"' ./runs/<scenario>/<timestamp>/<scenario>.jsonl && echo ready
```

`--model` / `--provider` select the judge. They are required even when every
metric you asked for is deterministic, because the provider is built before the
metrics run.

Results land in `<scenario>_report.json` under `measurements`, keyed by
`metric_name`. A later invocation drops every entry named after a metric it
ran or named in its new output, so a metric that now returns nothing or raises
loses its old entry. A suffixed entry such as `external_word_count_team_a` goes
only when the re-run emits that name again.
[What a report contains](evaluation.md#what-a-report-contains) covers the merge
and how `evaluation_cost` accumulates.

Other ways to reach the same runner:

- **REST**: `POST /api/g/<slug>/runs/<scenario>/<run_dir_name>/evaluate` with a
  metric list. Validated against `available_metric_names(scenario_cls)`, so a
  metric your scenario returns from `scenario_metrics()` works once the server
  loads that scenario. Gated by `ENABLE_EVALUATIONS`.
- **The frontend's "Run Eval" button**, which calls that endpoint.

A metric that raises is logged with its traceback and recorded as failed. The
remaining metrics still run and the report is still written.

## Testing it

A metric is a pure function of an event log, which makes it cheap to test
directly: build a list of events, call `compute`, assert on the `Measurement`.
No simulation and no LLM needed for a deterministic metric.

Worth covering:

- The empty-list case, on a run your metric does not apply to.
- The partition case, if you emit one `Measurement` per team.
- A judge-driven metric's parsing, against a recorded judge response, using
  `StubLLMProvider` from
  [stub_llm_provider.py](../src/glossogen/testing/stub_llm_provider.py) rather
  than a live call.

To score a whole run directory the way `glossogen evaluate` does, see
[Testing a metric](testing-a-scenario.md#testing-a-metric).

[tests/unit/test_available_metrics.py](../tests/unit/test_available_metrics.py)
covers the registration side: that a scenario's own metric is offered and
runnable for that scenario only, that the advertised and runnable lists agree,
and that a scenario metric cannot take a generic metric's name.

## Checklist

- [ ] `name` is unique, and does not repeat a generic metric's.
- [ ] Returns `[]` rather than a zero-score sentinel when the metric does not
      apply, with one INFO skip line.
- [ ] In-repo: added to **both** `_GENERIC_METRICS` and `GENERIC_METRIC_NAMES`.
- [ ] Any prompt lives in a Jinja template, not a Python string.
- [ ] Sidecar files are written into `run_dir` and named after the metric, and
      `read_keyed_observations` reads them back if they hold numbers worth charting.
- [ ] `score_unit` says what `score` is, and `summary` reads as one sentence.
- [ ] `make lint` clean, and a test that calls `compute` on a hand-built event list.

Next: [Evaluation](evaluation.md) for the other metrics and the report, and
[Analysis](analysis.md) to compare scores across runs.
