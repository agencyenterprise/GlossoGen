"""`communication_feature_presence`: a confidence per ontology category.

Pass three of the open-coding pipeline. Where pass one names patterns freely,
this re-reads the same per-round view against a fixed ontology and scores every
category, so runs become comparable to each other rather than only describable.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from glossogen.evaluation.metrics.communication.label_models import (
    CategoryConfidence,
    CommunicationFeaturePresenceOutput,
    CommunicationOntology,
    OntologyCategory,
)
from tests.metrics.conftest import FIRST_TEXT, METRIC_RUN_GROUP
from tests.testbed.metric_harness import (
    MetricRun,
    isolated_run,
    ontology_options,
    score_metrics,
)

pytestmark = METRIC_RUN_GROUP

METRIC = "communication_feature_presence"
PRESENT = "terse"
ABSENT = "codes"


def write_ontology(*, path: Path) -> Path:
    """Write a two-category ontology for the judge to score against."""
    ontology = CommunicationOntology(
        version="test-1",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_run_ids=["smoke"],
        categories=[
            OntologyCategory(
                id=PRESENT, name="Terse phrasing", description="Short messages.", synonyms=[]
            ),
            OntologyCategory(
                id=ABSENT, name="Shorthand codes", description="Symbol mappings.", synonyms=[]
            ),
        ],
    )
    path.write_text(ontology.model_dump_json())
    return path


def judged() -> CommunicationFeaturePresenceOutput:
    """One category clearly present, one clearly absent."""
    return CommunicationFeaturePresenceOutput(
        scores=[
            CategoryConfidence(category_id=PRESENT, confidence=0.9, justification="one word each"),
            CategoryConfidence(category_id=ABSENT, confidence=0.1, justification="no mappings"),
        ],
        notes="Terse but uncoded.",
    )


async def test_the_score_counts_categories_above_the_confidence_threshold(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One of the two categories clears 0.5, so the score is one.

    The threshold is what turns a confidence vector into a comparable count.
    A metric that summed or averaged the confidences would report 1.0 here too,
    so the categories are deliberately split either side of the line.
    """
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[judged()],
        options=ontology_options(ontology_path=write_ontology(path=tmp_path / "ontology.json")),
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.measurement(metric_name=METRIC).score == pytest.approx(1.0)


async def test_the_full_confidence_vector_is_persisted_with_its_provenance(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count is a rollup; the vector is what cross-run analysis reads.

    Provenance matters as much as the numbers: confidences scored against
    different ontology versions are not comparable, and the file is the only
    place that says which one was used.
    """
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[judged()],
        options=ontology_options(ontology_path=write_ontology(path=tmp_path / "ontology.json")),
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    written = json.loads((run.run_dir / "communication_feature_presence.json").read_text())
    scores = {entry["category_id"]: entry["confidence"] for entry in written["scores"]}
    assert scores == {PRESENT: pytest.approx(0.9), ABSENT: pytest.approx(0.1)}
    assert "test-1" in json.dumps(written), "the ontology version should be recorded"


async def test_the_judge_sees_the_same_rounds_as_the_open_coding_pass(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both passes read `build_communication_rounds`, which is what makes them
    commensurable. If this pass saw a different view, its confidences would not
    describe the labels the ontology was built from.
    """
    run = isolated_run(run=metric_run, tmp_path=tmp_path)
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[judged()],
        options=ontology_options(ontology_path=write_ontology(path=tmp_path / "ontology.json")),
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    prompt = scored.judge.calls[0].messages[0].content
    assert FIRST_TEXT in prompt
    assert "smoke round 1" in prompt
    assert PRESENT in prompt, "the ontology's categories should reach the judge"
