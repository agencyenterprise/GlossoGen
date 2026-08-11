"""`protocol_explanation`: each agent describing, in its own words, the protocol.

Free text rather than a fixed bank, and each agent is re-run under its own
model with its full end-of-run history. What it produces is the qualitative
counterpart to the probe similarity numbers: not how consistently an agent
answers, but what it thinks it agreed to.
"""

import json
from pathlib import Path

import pytest

from glossogen.evaluation.metrics.protocol_explanation_metric import ProtocolExplanationOutput
from tests.metrics.conftest import METRIC_RUN_GROUP, SUCCESSOR_MODEL
from tests.testbed.metric_harness import (
    NO_OPTIONS,
    MetricRun,
    ScoredRun,
    isolated_run,
    score_metrics,
    use_scripted_probe_model,
)
from tests.testbed.smoke_scenario import FIRST_AGENT_ID, SECOND_AGENT_ID

pytestmark = METRIC_RUN_GROUP

METRIC = "protocol_explanation"
ANSWER = "we sent one word per round and never acknowledged"


async def explain(
    *, metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[MetricRun, ScoredRun]:
    """Run the explanation probe over an isolated copy of the shared run."""
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    use_scripted_probe_model(
        answers=[ANSWER], output_type=ProtocolExplanationOutput, monkeypatch=monkeypatch
    )
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )
    return run, scored


async def test_every_agent_is_probed_and_its_answer_kept(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The score is the number of agents probed, and each answer is retrievable.

    An agent that was skipped costs half the run's evidence, and the score is
    the only place that would show it.
    """
    _, scored = await explain(metric_run=metric_run, tmp_path=tmp_path, monkeypatch=monkeypatch)

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(2.0)
    assert {observation.agent_id for observation in measurement.per_agent} == {
        FIRST_AGENT_ID,
        SECOND_AGENT_ID,
    }
    assert all(observation.note == ANSWER for observation in measurement.per_agent)


async def test_the_answers_and_their_cost_are_persisted(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sidecar is where the prose is read from; the report only counts it.

    Cost is recorded per model because each agent is probed under its own, so a
    mixed-model run cannot attribute the spend from the report alone.
    """
    run, _ = await explain(metric_run=metric_run, tmp_path=tmp_path, monkeypatch=monkeypatch)

    rows = [
        json.loads(line)
        for line in (run.run_dir / "protocol_explanation_responses.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert {row["agent_id"] for row in rows} == {FIRST_AGENT_ID, SECOND_AGENT_ID}
    assert all(row["description_text"] == ANSWER for row in rows)

    registered = {
        event["agent_id"]: event["model"]
        for event in metric_run.simulation.of_type(event_type="agent_registered")
    }
    for row in rows:
        assert row["model"] == registered[row["agent_id"]], "probed under its own model"

    assert (run.run_dir / "protocol_explanation_usage.json").exists()


async def test_a_swapped_agent_is_probed_under_the_model_it_finished_on(
    swapped_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An in-run swap writes no new `AgentRegistered`, only `AgentSwappedMidRun`.

    So configs rebuilt from registrations alone carry the *predecessor's*
    model, and the probe asks the successor's question of the agent it
    replaced. On a cross-model swap that means interrogating a gpt-5.4 agent as
    claude-sonnet, and the answer looks entirely plausible.

    This run swaps `first_agent` mid-way, so its recorded probe model has to be
    the successor's, not the one it started on.
    """
    run = isolated_run(run=swapped_run, tmp_path=tmp_path)
    use_scripted_probe_model(
        answers=[ANSWER], output_type=ProtocolExplanationOutput, monkeypatch=monkeypatch
    )
    await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    rows = {
        json.loads(line)["agent_id"]: json.loads(line)["model"]
        for line in (run.run_dir / "protocol_explanation_responses.jsonl").read_text().splitlines()
        if line.strip()
    }
    assert rows[FIRST_AGENT_ID] == SUCCESSOR_MODEL, (
        f"the swapped agent was probed as {rows[FIRST_AGENT_ID]!r}, "
        f"which is the model it was replaced from"
    )
    assert rows[SECOND_AGENT_ID] != SUCCESSOR_MODEL, "the unswapped agent should be unaffected"
