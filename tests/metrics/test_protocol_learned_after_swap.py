"""`protocol_learned_after_swap`: did the newcomer pick up what it inherited?

The learnability question itself. It splits the run at a personnel change,
renders the transcript either side through `build_communication_rounds`, and
asks a judge whether the agent that arrived after the boundary shows evidence
of the protocol negotiated before it.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import RoundNote
from glossogen.evaluation.metrics.protocol_learned_after_swap_metric import ProtocolLearnedOutput
from tests.metrics.conftest import (
    FIRST_AGENT_ID,
    FIRST_TEXT,
    METRIC_RUN_GROUP,
    SUCCESSOR_TEXT,
    SWAP_ROUND,
)
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "protocol_learned_after_swap"


def judged(*, rounds: list[int]) -> ProtocolLearnedOutput:
    """A judge answer flagging the given post-boundary rounds."""
    return ProtocolLearnedOutput(
        per_round_notes=[
            RoundNote(round_number=number, note="successor reused the incumbent's format")
            for number in rounds
        ],
        protocol_elements=["one word per round"],
        newcomer_agent_ids=[FIRST_AGENT_ID],
        protocol_established=True,
        explanation="The successor matched the prior convention.",
    )


async def test_the_score_counts_post_boundary_rounds_with_evidence(
    swapped_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One flagged round means one round where the newcomer showed the protocol."""
    scored = await score_metrics(
        run=swapped_run,
        metric_names=[METRIC],
        judge_responses=[judged(rounds=[SWAP_ROUND])],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(1.0)
    assert [o.round_number for o in measurement.per_round] == [SWAP_ROUND]


async def test_the_judge_is_shown_both_sides_of_the_boundary(
    swapped_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A judge shown only the post-swap rounds cannot tell learned from invented.

    The question is whether the newcomer picked up something that already
    existed, so it needs the predecessor's messages as well as the successor's.
    Both texts are distinct on purpose, so their presence in the prompt is
    checkable.
    """
    scored = await score_metrics(
        run=swapped_run,
        metric_names=[METRIC],
        judge_responses=[judged(rounds=[SWAP_ROUND])],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert len(scored.judge.calls) == 1
    prompt = scored.judge.calls[0].messages[0].content
    assert FIRST_TEXT in prompt, "the predecessor's messages should reach the judge"
    assert SUCCESSOR_TEXT in prompt, "the successor's messages should reach the judge"


async def test_a_judge_that_saw_no_evidence_scores_zero(
    swapped_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A newcomer that learned nothing is the negative result, and it is a result.

    This is the finding the experiments are looking for, so it has to be
    distinguishable from a run the metric could not score at all.
    """
    scored = await score_metrics(
        run=swapped_run,
        metric_names=[METRIC],
        judge_responses=[
            ProtocolLearnedOutput(
                per_round_notes=[],
                protocol_elements=[],
                newcomer_agent_ids=[FIRST_AGENT_ID],
                protocol_established=False,
                explanation="No convention survived the swap.",
            )
        ],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(0.0)
    assert measurement.per_round == []


async def test_a_run_with_no_swap_writes_no_measurement(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No boundary means there is no before and after to compare."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.report.measurements == []
    assert scored.judge.calls == []
