"""`round_success_after_resume`: how the run went once an agent was replaced.

The headline number of the protocol-learnability experiments. Same accounting
as `round_success`, but scoped to the rounds after a swap and compared against
the same window before it, so the question it answers is whether the newcomer
kept the run going.
"""

from pathlib import Path

import pytest

from tests.metrics.conftest import FIRST_AGENT_ID, METRIC_RUN_GROUP, SWAP_ROUND
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "round_success_after_resume"


async def test_it_emits_one_measurement_per_swap_naming_round_and_agent(
    swapped_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multi-swap run reports each phase separately, so the name carries both.

    Analysis groups these by (round, agent) to compare swap points against each
    other. A single unnamed measurement would collapse a three-swap run into
    one number and lose which boundary it belonged to.
    """
    scored = await score_metrics(
        run=swapped_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    expected = f"{METRIC}_round_{SWAP_ROUND}_{FIRST_AGENT_ID}"
    assert scored.names() == [expected]
    assert scored.judge.calls == []


async def test_it_scores_only_the_rounds_after_the_swap(
    swapped_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Including pre-swap rounds would credit the newcomer with its predecessor's run.

    The smoke scenario fails every round here (no findings recorded), so the
    score is zero either way. What the window controls is which rounds appear
    in `per_round`, and that has to start at the swap.
    """
    scored = await score_metrics(
        run=swapped_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=f"{METRIC}_round_{SWAP_ROUND}_{FIRST_AGENT_ID}")
    assert measurement.per_round, "the post-swap window should contain rounds"
    assert min(o.round_number for o in measurement.per_round) >= SWAP_ROUND


async def test_a_run_with_no_swap_writes_no_measurement(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No boundary means no window, and zero would not say the same thing.

    Reporting zero here would be indistinguishable from a resumed run whose
    post-swap rounds all failed, and that number would be averaged into a
    comparison against runs where it means something.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.report.measurements == []
