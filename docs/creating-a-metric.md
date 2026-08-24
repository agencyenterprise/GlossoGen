# Creating a metric

A metric scores a finished run. It reads the run's event log, optionally calls an
LLM judge, and returns one or more `Measurement` entries that land in
`<scenario>_report.json`.

Metrics are scenario-agnostic by default: one you write reads the event log and
asks the scenario for what it needs through hooks, so it works on scenarios you
did not write. It can live in this repo or ship in your own package without
touching this repo at all.

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
[metric_protocol.py](../src/glossogen/evaluation/metric_core/metric_protocol.py):

```python
class Metric(ABC):
    name: str

    @abstractmethod
    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]: ...
```

| Argument | Holds |
|---|---|
| `name` | What callers pass to `--metrics`, and the key the report is written under. Must be unique |
| `events` | The full ordered event log, already parsed |
| `scenario` | The built scenario: ask it which channels it scores (`get_primary_channels()`), how it renders a round (`build_communication_rounds`), anything on its contract |
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
    sidecar = await read_json_sidecar(path=run_dir / _SIDECAR_FILENAME)
    if sidecar is None:
        return []
    return [
        KeyedObservation(
            keys={"category_id": key_text(value=score.get("category_id"))},
            value=confidence,
        )
        for score in object_rows(value=sidecar.get("scores"))
        if (confidence := number_or_none(value=score.get("confidence"))) is not None
    ]
```

The keys are yours to name. They become groupable dimensions as `key.<name>`, and
nothing outside your metric interprets them. Without this method the numbers stay
readable only by whoever opens the file.

Two rules carry over from `compute`. A missing number is dropped rather than
returned as `0.0`. And a sidecar that cannot be read yields `[]` rather than raising: these are
read across whole cohorts, where one file written by an older version of your metric
must not fail the selection.

## Writing one

[mcr_metric.py](../src/glossogen/evaluation/metrics/mcr_metric.py) is the
smallest complete example: deterministic, reads `MessageSent` events on the
scenario's primary channels, emits one `RoundObservation` per round plus a mean.
Copy its shape.

```python
class ExternalWordCountMetric(Metric):
    """Mean words per message on the scenario's primary channels."""

    name = "external_word_count"

    async def compute(self, events, agent_configs, scenario, llm_provider, run_dir, options):
        _ = agent_configs, llm_provider, run_dir, options
        channel_ids = {channel.channel_id for channel in scenario.get_primary_channels()}
        counts = [
            len(event.message.text.split())
            for event in events
            if isinstance(event, MessageSent) and event.message.channel_id in channel_ids
        ]
        if not counts:
            return []
        mean = sum(counts) / len(counts)
        return [
            Measurement(
                metric_name=self.name,
                score=mean,
                score_unit="words/message",
                summary=f"{mean:.2f} words per message across {len(counts)} messages",
                per_round=[],
                per_agent=[],
            )
        ]
```

That one is real: it lives at
[tests/fakes/external_metric.py](../tests/fakes/external_metric.py), where the
tests use it as a stand-in for a metric shipped by another package.

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

The second list exists because `SimulationScenario.get_available_metric_names`
needs the names and cannot import the registry: a metric module imports the
scenario contract, so importing metric classes back into it would close a cycle.
A test asserts the two lists match, so forgetting either edit fails there. At
launch the symptom would have been a metric the CLI runs and the API rejects.

If the metric only makes sense for one scenario, put the class under that
scenario's `evaluation/` directory and have the scenario override
`get_available_metric_names`, calling `super()` and adding to what it returns.
Replacing it wholesale drops every generic and externally-installed metric for
that scenario. Prefer a generic metric that reads a scenario hook: every scoring
concept the platform has ended up expressible that way.

### In your own package

A metric does not have to live here. Depend on glossogen (see
[As a dependency](installation.md#as-a-dependency) for the install line, since
glossogen is not on PyPI) and declare an entry point:

```toml
[project]
name = "my-metrics"
dependencies = ["glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"]

[project.entry-points."glossogen.metrics"]
external_word_count = "my_metrics.word_count:ExternalWordCountMetric"
```

Then `pip install -e .` (or `uv pip install -e .`) in your package. One
distribution can declare both metrics and scenarios. The groups are independent,
so a metric package needs no scenario and vice versa.

The entry-point name **must equal the class's `name` attribute**. The report is
keyed by the class's own `name`, so a mismatch would write a measurement under a
name nobody asked for. The registry refuses that pairing and logs why.

With the package installed, the metric is runnable and every scenario advertises
it. No edit to either list above, and no fork.

What differs from an in-repo metric:

- **A name already used by a built-in stays with the built-in**, and the
  collision is logged. Reports are compared across runs by metric name, so
  letting an installed package redefine `round_success` would silently make two
  reports incomparable.
- **One broken metric does not fail the evaluation.** A metric that will not
  import, is not a `Metric` subclass, or disagrees with its declared name is
  logged and skipped. The others still run and still write a report. Check the
  evaluation log if your metric does not appear.
- **The group is unversioned**, unlike `glossogen.scenarios.v1`. The scenario
  contract carries a version because a scenario hook's required behaviour can
  change while its signature does not. `compute` is a single method, so a change
  to it fails loudly on the call.

## Running it

Same command either way. The metric name goes in the comma-separated `--metrics`
list:

```bash
glossogen evaluate veyru \
  --run-dir ./runs/veyru/<timestamp> \
  --metrics external_word_count,round_success,mean_chars_per_round \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  > ./runs/veyru/<timestamp>/eval_stdout.log 2>&1 &
```

From a checkout, spell each command
`VIRTUAL_ENV= uv run --no-sync python -m glossogen ...`.

**Only evaluate a run that has emitted `simulation_ended`.** Gating on a round
count instead scores a run whose last round is still in flight, and the missing
round is silent in the report:

```bash
grep -q '"simulation_ended"' ./runs/veyru/<timestamp>/veyru.jsonl && echo ready
```

`--model` / `--provider` select the judge. They are required even when every
metric you asked for is deterministic, because the provider is built before the
metrics run.

Results land in `<scenario>_report.json` under `measurements`, keyed by
`metric_name`. Re-running merges: a later invocation replaces the entries for the
metrics it produced and leaves the rest alone, and `evaluation_cost` accumulates
across invocations when the judge is unchanged.

Other ways to reach the same runner:

- **REST**: `POST /api/g/<slug>/runs/<scenario>/<run_dir_name>/evaluate` with a
  metric list. Validated against `get_available_metric_names()`, so an external
  metric works once installed. Gated by `ENABLE_EVALUATIONS`.
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
- A judge-driven metric's parsing, against a recorded judge response, using the
  stub provider in [tests/fakes/](../tests/fakes/) rather than a live call.

[tests/unit/test_metric_entry_points.py](../tests/unit/test_metric_entry_points.py)
covers the registration side: that an externally-declared metric becomes
runnable, that every scenario advertises it, that the advertised and runnable
lists agree, and each way a declaration can be refused.

## Checklist

- [ ] `name` is unique and matches the entry-point name, if you declared one.
- [ ] Returns `[]` rather than a zero-score sentinel when the metric does not
      apply, with one INFO skip line.
- [ ] In-repo: added to **both** `_GENERIC_METRICS` and `GENERIC_METRIC_NAMES`.
- [ ] Any prompt lives in a Jinja template, not a Python string.
- [ ] Sidecar files are written into `run_dir` and named after the metric, and
      `read_keyed_observations` reads them back if they hold numbers worth charting.
- [ ] `score_unit` says what `score` is, and `summary` reads as one sentence.
- [ ] `make lint` clean, and a test that calls `compute` on a hand-built event list.
