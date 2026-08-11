"""`protocol_probe`: every agent answering a fixed question bank afterwards.

The producer of the probe family: it re-runs each agent under its own model
with its end-of-run history, asks the scenario's questions, and writes one row
per (agent, question, replica). The three similarity metrics read those rows,
so if this writes the wrong thing they all agree on the wrong answer.
"""

import json
from pathlib import Path

import pytest

from glossogen.evaluation.metrics.protocol_probe.response_models import ProtocolProbeOutput
from tests.metrics.conftest import METRIC_RUN_GROUP
from tests.testbed.metric_harness import (
    NO_OPTIONS,
    MetricRun,
    isolated_run,
    probe_options,
    score_metrics,
    use_scripted_probe_model,
)
from tests.testbed.smoke_scenario import FIRST_AGENT_ID, SECOND_AGENT_ID

pytestmark = METRIC_RUN_GROUP

METRIC = "protocol_probe"
# The bank in tests/testbed/probe_questions.json asks each agent one question of
# its own and one they both answer, so a replica costs three questions but four
# probes. The row count follows the agent-question pairs, not the questions:
# a question matching two agents produces two rows.
PROBES_PER_REPLICA = 4
QUESTION_IDS = {"q_first_agent_recall", "q_second_agent_recall", "q_shared_protocol"}
REPLICAS = 2


async def test_it_writes_a_row_per_agent_question_and_replica(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row count is the contract the similarity metrics are built on.

    Each row carries one answer. Dropping a replica silently narrows every
    downstream matrix, and the similarity numbers stay plausible while being
    computed over fewer samples than the run paid for.
    """
    use_scripted_probe_model(
        answers=["we used two-letter codes"],
        output_type=ProtocolProbeOutput,
        monkeypatch=monkeypatch,
    )
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[],
        options=probe_options(replicas=REPLICAS, probe_round=None),
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(float(PROBES_PER_REPLICA * REPLICAS))

    rows = [
        json.loads(line)
        for line in (run.run_dir / "protocol_probe_responses.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == PROBES_PER_REPLICA * REPLICAS
    assert {row["agent_id"] for row in rows} == {FIRST_AGENT_ID, SECOND_AGENT_ID}
    assert {row["question_id"] for row in rows} == QUESTION_IDS
    assert {row["replica_index"] for row in rows} == set(range(1, REPLICAS + 1))
    assert all(row["response_text"] == "we used two-letter codes" for row in rows)


async def test_each_agent_is_probed_under_its_own_model(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not the evaluation `--model`.

    A probe answers "what does this agent remember", so running it on a
    different model than the agent used answers a question nobody asked. The
    row records the model, and it has to be the one from `agent_registered`.
    """
    use_scripted_probe_model(
        answers=["recalled"], output_type=ProtocolProbeOutput, monkeypatch=monkeypatch
    )
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[],
        options=probe_options(replicas=1, probe_round=None),
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    rows = [
        json.loads(line)
        for line in (run.run_dir / "protocol_probe_responses.jsonl").read_text().splitlines()
        if line.strip()
    ]
    registered = {
        event["agent_id"]: event["model"]
        for event in metric_run.simulation.of_type(event_type="agent_registered")
    }
    for row in rows:
        assert row["model"] == registered[row["agent_id"]]


async def test_it_refuses_to_run_without_a_replica_count(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe with no replica count has no defined amount of work to do.

    Defaulting to one would silently produce a run whose self-similarity
    cannot be computed, which is the whole point of probing more than once.
    """
    use_scripted_probe_model(
        answers=["recalled"], output_type=ProtocolProbeOutput, monkeypatch=monkeypatch
    )
    with pytest.raises(Exception) as raised:
        await score_metrics(
            run=metric_run,
            metric_names=[METRIC],
            judge_responses=[],
            options=NO_OPTIONS,
            report_path=tmp_path / "report.json",
            monkeypatch=monkeypatch,
        )
    assert METRIC in str(raised.value)
