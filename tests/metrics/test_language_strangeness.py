"""`language_strangeness`: unusual grammar, structure or formatting.

Deliberately not about codes, slang or invented words: those have their own
metrics, and a judge that conflates them makes all four move together and
none of them mean anything on their own.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import RoundNote
from glossogen.evaluation.metrics.language_strangeness_metric import LanguageStrangenessOutput
from tests.metrics.conftest import FIRST_TEXT, METRIC_RUN_GROUP, SECOND_TEXT
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "language_strangeness"


def judge_found_one() -> LanguageStrangenessOutput:
    """A judge answer flagging exactly one round."""
    return LanguageStrangenessOutput(
        per_round_notes=[RoundNote(round_number=1, note="telegraphic phrasing, articles dropped")],
        anomaly_categories=["telegraphic"],
        mutually_adopted=False,
        explanation="One round showed clipped syntax.",
    )


async def test_the_judge_is_shown_this_runs_messages(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A metric that rendered an empty transcript would still return a number.

    The judge's answer is the test's own, so the score proves nothing about
    what was read. Checking the prompt is what does.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[judge_found_one()],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert len(scored.judge.calls) == 1, "one call for the whole run"
    call = scored.judge.calls[0]
    assert FIRST_TEXT in call.messages[0].content
    assert SECOND_TEXT in call.messages[0].content
    assert call.output_schema is LanguageStrangenessOutput


async def test_the_answer_becomes_the_measurement(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Score counts flagged rounds; each note reaches its round observation."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[judge_found_one()],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(1.0)
    assert [o.round_number for o in measurement.per_round] == [1]
    assert measurement.per_round[0].note == "telegraphic phrasing, articles dropped"


async def test_a_judge_that_found_nothing_scores_zero_rather_than_skipping(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Looking and finding none is a result; not applying is not.

    The contrast with `round_success_after_resume` is the point: there, no
    measurement means the metric could not run at all.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[
            LanguageStrangenessOutput(
                per_round_notes=[],
                anomaly_categories=[],
                mutually_adopted=False,
                explanation="Nothing of the kind appeared.",
            )
        ],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(0.0)
    assert measurement.per_round == []
