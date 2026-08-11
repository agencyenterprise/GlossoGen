"""`protocol_probe_agent_pair_similarity`: do two agents describe the same protocol?

Where replica self-similarity asks whether one agent is consistent with itself,
this asks whether two agents converged on the same account. A pair that answers
a shared question the same way agreed on something; a pair that does not was
running two protocols that happened to interoperate.

It groups probe rows by (question, cutoff, role filter) and needs a group
holding more than one agent, which is why the test bank carries a question both
agents answer.
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
from tests.testbed.smoke_scenario import FIRST_AGENT_ID, SECOND_AGENT_ID, SHARED_QUESTION_ID

pytestmark = METRIC_RUN_GROUP

METRIC = "protocol_probe_agent_pair_similarity"


def shared_pair(*, first: str, second: str) -> list[str]:
    """Answers positioned so `first` and `second` land on the shared question.

    The two leading entries are consumed by the per-agent questions, which this
    metric does not pair. Naming them keeps the arithmetic out of each test.
    """
    return ["per-agent answer", "per-agent answer", first, second]


async def probe_then_score(
    *,
    metric_run: MetricRun,
    answers: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MetricRun, float]:
    """Probe both agents, then score how much their answers agree.

    `answers` is consumed in probe order, and the bank asks the two per-agent
    questions before the shared one. So the first two answers go to questions
    this metric ignores, and only the last two form the pair it compares.
    `shared_pair` builds that list rather than leaving a caller to count.
    """
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    use_scripted_probe_model(
        answers=answers, output_type=ProtocolProbeOutput, monkeypatch=monkeypatch
    )
    await score_metrics(
        run=run,
        metric_names=["protocol_probe"],
        judge_responses=[],
        options=probe_options(replicas=1, probe_round=None),
        report_path=tmp_path / "probe_report.json",
        monkeypatch=monkeypatch,
    )
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "similarity_report.json",
        monkeypatch=monkeypatch,
    )
    return run, scored.measurement(metric_name=METRIC).score


async def test_agents_that_answer_alike_score_one(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two agents giving the same account of the protocol agree completely.

    This is the convergence the experiments look for, so it has to be
    reachable: a metric that could never return 1.0 would make every agreed
    protocol look partly disputed.
    """
    _, score = await probe_then_score(
        metric_run=metric_run,
        answers=shared_pair(
            first="we numbered the checkpoints", second="we numbered the checkpoints"
        ),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert score == pytest.approx(1.0)


async def test_agents_that_disagree_score_below_one(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different accounts have to move the number, or it measures nothing.

    Without this a metric hardcoded to 1.0 passes the test above, and every
    run reports two agents in perfect agreement.
    """
    _, score = await probe_then_score(
        metric_run=metric_run,
        answers=shared_pair(
            first="we numbered the checkpoints", second="there was no convention at all"
        ),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert 0.0 <= score < 1.0


async def test_it_compares_the_question_both_agents_answered(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pair comes from the shared question, not from the per-agent ones.

    Each agent also answers a question only it is asked. Those groups hold one
    agent and cannot form a pair, so a metric pairing across questions would be
    comparing answers to different prompts.
    """
    run, _ = await probe_then_score(
        metric_run=metric_run,
        answers=shared_pair(first="a stable account", second="a stable account"),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    rows = [
        json.loads(line)
        for line in (run.run_dir / "protocol_probe_responses.jsonl").read_text().splitlines()
        if line.strip()
    ]
    shared = [row for row in rows if row["question_id"] == SHARED_QUESTION_ID]
    assert {row["agent_id"] for row in shared} == {FIRST_AGENT_ID, SECOND_AGENT_ID}

    written = json.loads((run.run_dir / "protocol_probe_agent_pair_similarity.json").read_text())
    assert SHARED_QUESTION_ID in json.dumps(written)
