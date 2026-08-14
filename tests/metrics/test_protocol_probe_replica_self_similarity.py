"""`protocol_probe_replica_self_similarity`: does an agent answer the same way twice?

Computed within one (agent, question, cutoff) group as the upper-triangle mean
of the replica x replica normalized-Levenshtein matrix. Saturation at 1.0 is
the expected signal for a settled protocol: the agent's account of it does not
move between samples.
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

METRIC = "protocol_probe_replica_self_similarity"
PROBE = "protocol_probe"


async def probe_then_score(
    *,
    metric_run: MetricRun,
    answers: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MetricRun, float]:
    """Probe with the given answers, then score the similarity over those rows."""
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    use_scripted_probe_model(
        answers=answers, output_type=ProtocolProbeOutput, monkeypatch=monkeypatch
    )
    await score_metrics(
        run=run,
        metric_names=[PROBE],
        judge_responses=[],
        options=probe_options(replicas=len(answers), probe_round=None),
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


async def test_identical_replicas_score_one(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent that says exactly the same thing twice is perfectly self-similar.

    This is the saturation the real runs report, so it has to be reachable:
    a metric that could never return 1.0 would make every converged protocol
    look slightly unstable.
    """
    _, score = await probe_then_score(
        metric_run=metric_run,
        answers=["we numbered the checkpoints", "we numbered the checkpoints"],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert score == pytest.approx(1.0)


async def test_replicas_that_disagree_score_below_one(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different answers have to move the number, or it measures nothing.

    Without this, a metric hardcoded to 1.0 would pass the test above and
    every real run would report a perfectly stable protocol.
    """
    _, score = await probe_then_score(
        metric_run=metric_run,
        answers=["we numbered the checkpoints", "no convention emerged at all"],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert 0.0 <= score < 1.0


async def test_it_persists_the_matrix_it_computed(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-group matrices are the analysable output; the score is a rollup."""
    run, _ = await probe_then_score(
        metric_run=metric_run,
        answers=["stable answer", "stable answer"],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    written = json.loads((run.run_dir / "protocol_probe_replica_self_similarity.json").read_text())
    assert written
