"""`protocol_probe_cutoff_trajectory`: how far an agent's account moves over time.

Probing at several cutoffs turns a single end-of-run snapshot into a series.
The number is the mean similarity between adjacent snapshots, so a protocol
that settled early scores near 1.0 and one still being renegotiated does not.
"""

import json
from pathlib import Path

import pytest

from glossogen.evaluation.metrics.protocol_probe.response_models import ProtocolProbeOutput
from glossogen.testing.metric_harness import (
    NO_OPTIONS,
    MetricRun,
    isolated_run,
    probe_options,
    score_metrics,
    use_scripted_probe_model,
)
from tests.metrics.conftest import METRIC_RUN_GROUP

pytestmark = METRIC_RUN_GROUP

METRIC = "protocol_probe_cutoff_trajectory"
REPLICAS = 2


async def probe_at_cutoffs(
    *,
    metric_run: MetricRun,
    answer_by_cutoff: list[tuple[int | None, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MetricRun, float]:
    """Probe once per cutoff into one run dir, then score the trajectory.

    The rows accumulate in the same file, which is what gives the metric more
    than one snapshot to difference. Two passes is the minimum that produces a
    trajectory at all.
    """
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    for cutoff, answer in answer_by_cutoff:
        use_scripted_probe_model(
            answers=[answer], output_type=ProtocolProbeOutput, monkeypatch=monkeypatch
        )
        await score_metrics(
            run=run,
            metric_names=["protocol_probe"],
            judge_responses=[],
            options=probe_options(replicas=REPLICAS, probe_round=cutoff),
            report_path=tmp_path / "probe_report.json",
            monkeypatch=monkeypatch,
        )
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "trajectory_report.json",
        monkeypatch=monkeypatch,
    )
    return run, scored.measurement(metric_name=METRIC).score


async def test_an_unchanged_account_scores_one(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same answer at both cutoffs means the protocol did not move."""
    _, score = await probe_at_cutoffs(
        metric_run=metric_run,
        answer_by_cutoff=[(2, "one word per round"), (None, "one word per round")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert score == pytest.approx(1.0)


async def test_a_changed_account_scores_below_one(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drift has to move the number, or the metric measures nothing.

    Without this, a metric returning a constant 1.0 would pass the test above
    and every run would report a protocol that never changed.
    """
    _, score = await probe_at_cutoffs(
        metric_run=metric_run,
        answer_by_cutoff=[(2, "no convention yet"), (None, "we settled on numbered checkpoints")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert 0.0 <= score < 1.0


async def test_it_persists_the_adjacent_cutoff_series(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The series is the analysable output; the score is its macro mean."""
    run, _ = await probe_at_cutoffs(
        metric_run=metric_run,
        answer_by_cutoff=[(2, "early"), (None, "later and different")],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    written = json.loads((run.run_dir / "protocol_probe_cutoff_trajectory.json").read_text())
    assert written
