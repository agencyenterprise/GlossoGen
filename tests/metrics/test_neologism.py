"""`neologism`: an LLM judge asked whether agents invented words.

Stands in here for the whole family of judge metrics, which share a shape:
render the round transcripts, ask once, turn the answer into a Measurement. The
score alone cannot tell you the judge was shown anything, so both sides are
checked.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import RoundNote
from glossogen.evaluation.metrics.neologism_metric import NeologismOutput
from tests.metrics.conftest import FIRST_TEXT, METRIC_RUN_GROUP, SECOND_TEXT
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "neologism"


def one_neologism_in_round_one() -> NeologismOutput:
    """A judge answer with a single flagged round."""
    return NeologismOutput(
        per_round_notes=[RoundNote(round_number=1, note="coined 'alpha' as a greeting")],
        semantically_stable=True,
        mutually_adopted=False,
        explanation="One invented term, used by one agent.",
    )


async def test_the_judge_is_shown_the_runs_actual_messages(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half the score cannot show.

    A metric that rendered an empty transcript would still return whatever the
    judge said, and the resulting number would look entirely reasonable.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[one_neologism_in_round_one()],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert len(scored.judge.calls) == 1, "the judge should be asked once for the whole run"
    call = scored.judge.calls[0]
    prompt = call.messages[0].content
    assert FIRST_TEXT in prompt
    assert SECOND_TEXT in prompt
    assert call.output_schema is NeologismOutput


async def test_the_judges_answer_becomes_the_measurement(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Score is the count of flagged rounds; the flags reach the summary."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[one_neologism_in_round_one()],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(1.0)
    assert [o.round_number for o in measurement.per_round] == [1]
    assert measurement.per_round[0].note == "coined 'alpha' as a greeting"
    assert "semantically stable" in measurement.summary


async def test_a_judge_that_found_nothing_scores_zero_rather_than_skipping(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "No neologisms" is an observation, not an inapplicable metric.

    The contrast with `round_success_after_resume` is the point: there, absence
    means the metric could not run. Here it means the judge looked and found
    none, which is a result worth recording.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[
            NeologismOutput(
                per_round_notes=[],
                semantically_stable=False,
                mutually_adopted=False,
                explanation="Plain English throughout.",
            )
        ],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(0.0)
    assert measurement.per_round == []
