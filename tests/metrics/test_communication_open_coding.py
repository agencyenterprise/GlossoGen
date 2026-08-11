"""`communication_open_coding`: free-form labels for the patterns a judge sees.

Pass one of the open-coding pipeline: no fixed vocabulary, the judge names
whatever it notices. The labels become the raw material a later pass
consolidates into an ontology, so what this writes to disk matters as much as
the score.
"""

import json
from pathlib import Path

import pytest

from glossogen.evaluation.metrics.communication.label_models import (
    CommunicationLabel,
    CommunicationOpenCodingOutput,
    EvidenceCitation,
)
from tests.metrics.conftest import FIRST_TEXT, METRIC_RUN_GROUP
from tests.testbed.metric_harness import (
    NO_OPTIONS,
    MetricRun,
    isolated_run,
    score_metrics,
)

pytestmark = METRIC_RUN_GROUP

METRIC = "communication_open_coding"


def two_labels() -> CommunicationOpenCodingOutput:
    """A judge answer naming two patterns, each with evidence."""
    return CommunicationOpenCodingOutput(
        labels=[
            CommunicationLabel(
                text="terse acknowledgement",
                evidence=[EvidenceCitation(round_number=1, quote=FIRST_TEXT)],
            ),
            CommunicationLabel(
                text="no addressing convention",
                evidence=[EvidenceCitation(round_number=1, quote=FIRST_TEXT)],
            ),
        ],
        explanation="Two patterns across the run.",
    )


async def test_the_score_is_the_number_of_labels_the_judge_returned(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open coding has no vocabulary, so the count is the whole measurement."""
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[two_labels()],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.measurement(metric_name=METRIC).score == pytest.approx(2.0)


async def test_the_labels_and_their_evidence_are_persisted(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sidecar is the pipeline's input, so the score alone is not enough.

    Pass two consolidates these files across runs into an ontology. A label
    that reached the report but not the file is a pattern the ontology will
    never contain.
    """
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[two_labels()],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    written = json.loads((run.run_dir / "communication_open_coding.json").read_text())
    labels = {label["text"] for label in written["labels"]}
    assert labels == {"terse acknowledgement", "no addressing convention"}
    assert written["labels"][0]["evidence"][0]["quote"] == FIRST_TEXT


async def test_the_judge_is_shown_the_scenario_rendered_rounds(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scenario's ground-truth block is what makes labels comparable.

    Without it the judge is coding a transcript with no idea what the round
    was trying to do, and the labels drift toward describing the task rather
    than the communication.
    """
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[two_labels()],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    prompt = scored.judge.calls[0].messages[0].content
    assert FIRST_TEXT in prompt
    assert "smoke round 1" in prompt, "the scenario's round header should reach the judge"
    assert "Findings recorded" in prompt, "the ground-truth block should reach the judge"
