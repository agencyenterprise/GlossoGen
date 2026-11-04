"""`round_success_after_resume`: how the run went once an agent was replaced.

The headline number of the protocol-learnability experiments. Same accounting
as `round_success`, but scoped to the rounds after a swap and compared against
the same window before it, so the question it answers is whether the newcomer
kept the run going.
"""

from pathlib import Path

import orjson
import pytest

from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, isolated_run, score_metrics
from tests.metrics.conftest import FIRST_AGENT_ID, METRIC_RUN_GROUP, SWAP_ROUND

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


async def test_a_swap_with_no_verdict_after_it_writes_no_measurement(
    swapped_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A swap the run never judged past is missing, not a window of failed rounds.

    The run keeps its pre-swap verdicts, so the metric applies; it has nothing
    to say about the successor. A zero would be averaged into the comparison
    as a newcomer that lost every round.
    """
    run = isolated_run(run=swapped_run, tmp_path=tmp_path)
    kept = [
        line
        for line in run.log_path.read_bytes().splitlines()
        if line
        and not (
            orjson.loads(line)["event_type"] == "round_result_recorded"
            and orjson.loads(line)["round_number"] >= SWAP_ROUND
        )
    ]
    run.log_path.write_bytes(b"\n".join(kept) + b"\n")

    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.report.measurements == []
