"""The report itself, rather than any one metric.

`run_scenario_evaluation` is shared by every metric, so a fault here breaks all
of them at once and none of the per-metric files would say why. It lives in this
package because it needs the same scored run they do.
"""

from pathlib import Path

import orjson
import pytest

from tests.metrics.conftest import METRIC_RUN_GROUP
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP


async def test_the_report_reaches_disk_in_the_shape_evaluate_writes(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everything downstream reads the file, not the return value.

    The runs API, the frontend and the analysis exporters all load
    `<scenario>_report.json`. A report that is right in memory and wrong on disk
    fails only there, long after the run that produced it.
    """
    report_path = tmp_path / "report.json"
    await score_metrics(
        run=metric_run,
        metric_names=["mean_chars_per_round", "round_success"],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=report_path,
        monkeypatch=monkeypatch,
    )

    written = orjson.loads(report_path.read_bytes())
    assert written["scenario_name"] == metric_run.scenario.name()
    assert written["simulation_id"]
    assert {m["metric_name"] for m in written["measurements"]} == {
        "mean_chars_per_round",
        "round_success",
    }


async def test_a_second_evaluation_keeps_the_metrics_it_did_not_rerun(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evaluating one metric must not drop the rest of the report.

    Metrics are routinely run in separate passes, the expensive ones long after
    the cheap ones. If the second pass replaced the report instead of merging
    into it, the first pass's results would vanish with nothing to say so.
    """
    report_path = tmp_path / "report.json"
    first = await score_metrics(
        run=metric_run,
        metric_names=["mean_chars_per_round"],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=report_path,
        monkeypatch=monkeypatch,
    )
    assert first.has(metric_name="mean_chars_per_round")

    second = await score_metrics(
        run=metric_run,
        metric_names=["round_success"],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=report_path,
        monkeypatch=monkeypatch,
    )

    assert second.has(metric_name="round_success")
    assert second.has(metric_name="mean_chars_per_round"), "the earlier metric was dropped"


async def test_an_unknown_metric_name_is_rejected_before_anything_runs(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo in `--metrics` has to fail, not silently score less than asked.

    The error carries the available names, because that is what the caller
    needs and the list is long enough to be worth printing.
    """
    with pytest.raises(ValueError) as raised:
        await score_metrics(
            run=metric_run,
            metric_names=["mean_chars_per_round", "round_sucess"],
            judge_responses=[],
            options=NO_OPTIONS,
            report_path=tmp_path / "report.json",
            monkeypatch=monkeypatch,
        )
    assert "round_success" in str(raised.value)


async def test_a_failing_metric_does_not_lose_the_ones_that_worked(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A judge metric with no queued answer raises; the report still lands.

    Evaluation writes what succeeded and then exits non-zero, so a run whose
    expensive metric failed keeps the cheap ones instead of having to redo
    everything.
    """
    report_path = tmp_path / "report.json"
    with pytest.raises(Exception) as raised:
        await score_metrics(
            run=metric_run,
            metric_names=["mean_chars_per_round", "neologism"],
            judge_responses=[],
            options=NO_OPTIONS,
            report_path=report_path,
            monkeypatch=monkeypatch,
        )
    assert "neologism" in str(raised.value)

    written = orjson.loads(report_path.read_bytes())
    names = {m["metric_name"] for m in written["measurements"]}
    assert names == {"mean_chars_per_round"}
