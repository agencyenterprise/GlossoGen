"""Score a finished simulation the way `glossogen evaluate` does.

A metric's contract is not "given this list of events, return this number". It
is "given a run directory on disk, produce a report". Between the two sit the
JSONL reader, the round-transcript builder, the metric registry, the report
merge and the cost accounting, and a metric can be correct while any of those
mis-serves it. So this drives `run_scenario_evaluation`, the same function the
CLI calls, against a run that a real simulation actually wrote.

Only the judge is replaced. Deterministic metrics never notice; LLM-judge
metrics get a `StubLLMProvider` whose answers the test chose, which is also
where the interesting assertion usually lives: not what the judge said, but
what it was shown.
"""

import shutil
from pathlib import Path
from typing import NamedTuple

import pytest
from pydantic import BaseModel

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.reports.evaluation_report import EvaluationReport
from glossogen.evaluation.scenario_evaluation_runner import run_scenario_evaluation
from glossogen.llm.provider import LLMProvider
from glossogen.scenario_protocol import SimulationScenario
from glossogen.testing.scripted_agent import ToolTurn, build_scripted_model
from glossogen.testing.simulation_harness import SimulationResult
from glossogen.testing.stub_llm_provider import StubLLMProvider

# What the CLI passes when no probe or ontology flags were given, which is every
# invocation except the probe metrics. Named so callers state it rather than
# inheriting it from a default.
NO_OPTIONS = MetricRunOptions(probe_round=None, probe_replicas=None, ontology_path=None)


def probe_options(*, replicas: int, probe_round: int | None) -> MetricRunOptions:
    """The options `--probe-replicas` and `--probe-round` produce."""
    return MetricRunOptions(probe_round=probe_round, probe_replicas=replicas, ontology_path=None)


def ontology_options(*, ontology_path: Path) -> MetricRunOptions:
    """The options `--ontology-path` produces."""
    return MetricRunOptions(probe_round=None, probe_replicas=None, ontology_path=ontology_path)


# The judge the report's cost is attributed to. Nothing is sent anywhere; the
# name only has to be one `token_pricing` knows, or the cost comes back zero and
# the report says the evaluation was free.
JUDGE_MODEL = "claude-haiku-4-5-20251001"
JUDGE_PROVIDER = "anthropic"


class MetricRun(NamedTuple):
    """A finished simulation on disk, ready to be scored."""

    scenario: SimulationScenario
    run_dir: Path
    log_path: Path
    simulation: SimulationResult


def isolated_run(*, run: MetricRun, tmp_path: Path) -> MetricRun:
    """Copy `run`'s directory so a metric can write sidecars without leaking.

    Several metrics persist files next to the log: `protocol_probe` appends
    `protocol_probe_responses.jsonl`, the similarity metrics and the
    communication pass each write their own JSON. The shared run is reused by
    every test in the package, so writing into it makes results depend on which
    test ran first, and an appending metric makes them depend on how many times.
    """
    copied_dir = tmp_path / "run"
    shutil.copytree(run.run_dir, copied_dir)
    return MetricRun(
        scenario=run.scenario,
        run_dir=copied_dir,
        log_path=copied_dir / run.log_path.name,
        simulation=run.simulation,
    )


class ScoredRun(NamedTuple):
    """The report a metric run produced, plus the judge it was given."""

    report: EvaluationReport
    judge: StubLLMProvider
    report_path: Path

    def names(self) -> list[str]:
        """Return the metric names the report carries, in order."""
        return [m.metric_name for m in self.report.measurements]

    def measurement(self, *, metric_name: str) -> Measurement:
        """Return one measurement by name, failing loudly if it is absent.

        A metric that decides it does not apply returns no measurement rather
        than a zero, so "missing" and "scored zero" are different outcomes and a
        test asking for the wrong one should say so.
        """
        for measurement in self.report.measurements:
            if measurement.metric_name == metric_name:
                return measurement
        raise AssertionError(
            f"no measurement named {metric_name!r} in the report; got {self.names()}"
        )

    def has(self, *, metric_name: str) -> bool:
        """Return whether the report carries a measurement under this name."""
        return any(m.metric_name == metric_name for m in self.report.measurements)


# pydantic-ai routes a structured `output_type` through a tool call rather than
# free text, under this name. A probe answer therefore has to arrive as a call
# to it, not as a `SayTurn`.
STRUCTURED_OUTPUT_TOOL = "final_result"


def use_scripted_probe_model(
    *,
    answers: list[str],
    output_type: type[BaseModel],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make the probe metrics answer from a script instead of a provider.

    `protocol_probe` and `protocol_explanation` do not go through the judge
    provider. They build their own pydantic-ai agent per probed agent, under
    that agent's original model, so `StubLLMProvider` never sees them and
    without this they would reach a real API on every run of the suite.

    `output_type` is the schema that metric asks for, and it differs between
    them: the probe wants a reasoning/message pair, the explanation wants a
    single description. The args are built from its fields, because a fixed
    payload validates for one and not the other, and a probe whose answer fails
    validation is swallowed by the metric's own error handling. That looks like
    an agent with no history rather than a broken fake.

    Each answer becomes one probe response, in order; the script repeats its
    last answer once spent, because the call count is the question bank times
    the replica count and a test should not have to restate that arithmetic.
    """
    fields = list(output_type.model_fields)
    turns = [
        ToolTurn(
            tool_name=STRUCTURED_OUTPUT_TOOL,
            # Every field is filled, and the last one carries the answer, so a
            # test can assert on the text whichever schema it asked for.
            args={name: (answer if name == fields[-1] else "scripted") for name in fields},
        )
        for answer in answers
    ]
    scripted = build_scripted_model(turns=turns, when_exhausted=[turns[-1]])

    def probe_model(model: str, provider: str) -> object:
        """Stand in for the per-agent model factory the probe agent builds."""
        _ = model, provider
        return scripted

    monkeypatch.setattr(
        "glossogen.evaluation.metrics.protocol_probe.probe_agent.build_pydantic_ai_model",
        probe_model,
    )


async def score_metrics(
    *,
    run: MetricRun,
    metric_names: list[str],
    judge_responses: list[BaseModel],
    options: MetricRunOptions,
    report_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ScoredRun:
    """Run `metric_names` over `run` and return the report.

    `judge_responses` are handed to the stub judge in order, one per
    `generate_structured` call. Pass an empty list for deterministic metrics: an
    unexpected call then fails with the schema it asked for, rather than a
    metric quietly scoring on an invented answer.

    `report_path` is explicit because evaluation merges into whatever is already
    there. Tests that want a clean report pass a path of their own; a test about
    merging passes the same path twice. Defaulting it to somewhere inside the
    run directory would silently couple every test sharing that run to the order
    they happen to execute in.
    """
    judge = StubLLMProvider()
    for response in judge_responses:
        judge.queue(response=response)

    def stub_provider(
        provider_name: str,
        model: str,
        inference_provider: str | None,
        reasoning_effort: str | None,
    ) -> LLMProvider:
        """Stand in for the real provider factory inside the evaluation runner."""
        _ = provider_name, model, inference_provider, reasoning_effort
        return judge

    monkeypatch.setattr(
        "glossogen.evaluation.scenario_evaluation_runner.create_provider",
        stub_provider,
    )

    report = await run_scenario_evaluation(
        scenario=run.scenario,
        log_path=run.log_path,
        metric_names=metric_names,
        report_path=report_path,
        model=JUDGE_MODEL,
        provider_name=JUDGE_PROVIDER,
        inference_provider=None,
        reasoning_effort=None,
        options=options,
    )
    return ScoredRun(report=report, judge=judge, report_path=report_path)
