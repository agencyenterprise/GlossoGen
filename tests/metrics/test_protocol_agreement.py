"""`protocol_agreement`: how the agents came to share each convention, and which messages show it.

The judge's answer is the test's own, so these tests check what the metric does
around it: which entries it shows the judge, that only real references become
evidence, and that the sidecar the run page reads matches the measurement.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.metrics.protocol_agreement.judge_output import (
    JudgedConvention,
    JudgedStep,
    ProtocolAgreementJudgeOutput,
)
from glossogen.models.protocol_agreement import AgreementStage
from glossogen.run_storage.protocol_agreement_file import read_protocol_agreement
from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, isolated_run, score_metrics
from glossogen.testing.smoke_scenario import FIRST_AGENT_ID, SECOND_AGENT_ID
from tests.metrics.conftest import FIRST_TEXT, METRIC_RUN_GROUP, SECOND_TEXT

pytestmark = METRIC_RUN_GROUP

METRIC = "protocol_agreement"


def judge_answer(*, understood_references: list[str]) -> ProtocolAgreementJudgeOutput:
    """One convention proposed in round 1's first entry, and one that cites nothing real."""
    return ProtocolAgreementJudgeOutput(
        conventions=[
            JudgedConvention(
                name="Greek letters",
                meaning="Each agent names itself by a Greek letter.",
                steps=[
                    JudgedStep(
                        stage=AgreementStage.PROPOSED,
                        references=["R1.1"],
                        explanation="The first agent opens with a Greek letter.",
                    ),
                    JudgedStep(
                        stage=AgreementStage.UNDERSTOOD,
                        references=understood_references,
                        explanation="The second agent answers with another Greek letter.",
                    ),
                ],
                adopted_by_all=True,
                first_shared_round=1,
            ),
            JudgedConvention(
                name="Invented",
                meaning="A convention the judge cites no real entry for.",
                steps=[
                    JudgedStep(
                        stage=AgreementStage.PROPOSED,
                        references=["R9.99"],
                        explanation="Nothing in the run.",
                    )
                ],
                adopted_by_all=False,
                first_shared_round=None,
            ),
        ],
        summary="The agents shared one convention from round 1.",
    )


async def test_the_judge_reads_every_message_with_a_reference(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transcript must hold the run's messages, each labelled for citing."""
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[judge_answer(understood_references=["R1.2"])],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert len(scored.judge.calls) == 1, "one call for the whole run"
    prompt = scored.judge.calls[0].messages[0].content
    assert f"[R1.1] {FIRST_AGENT_ID}: #" in prompt or f"[R1.1] {SECOND_AGENT_ID}: #" in prompt
    assert FIRST_TEXT in prompt
    assert SECOND_TEXT in prompt
    assert "read_notifications" not in prompt, "platform calls carry no signal"
    assert scored.judge.calls[0].output_schema is ProtocolAgreementJudgeOutput


async def test_only_references_that_exist_become_evidence(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A made-up reference is dropped, and a step or convention left with none goes with it."""
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[judge_answer(understood_references=["R1.2", "R7.1"])],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    sidecar = await read_protocol_agreement(run_dir=run.run_dir)
    assert sidecar is not None
    assert [c.name for c in sidecar.conventions] == ["Greek letters"]
    proposed, understood = sidecar.conventions[0].steps
    assert [e.round_number for e in understood.evidence] == [1], "R7.1 is not in the run"
    assert proposed.evidence[0].text.endswith(FIRST_TEXT) or proposed.evidence[0].text.endswith(
        SECOND_TEXT
    ), "evidence text comes from the log, not from the judge"
    assert proposed.agent_id == proposed.evidence[0].agent_id

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(1.0)
    assert [o.round_number for o in measurement.per_round] == [1]
