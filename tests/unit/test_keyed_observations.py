"""Reading the numbers metrics wrote beside their reports, and grouping by them.

Some metrics measure a run along an axis that is neither a round nor an agent: an
ontology category, a probe question, a message. Those numbers were written to a
sidecar file because a Measurement has nowhere to hold them, which put them out of
reach of every cross-run question until now.

What is pinned here is the contract rather than any one metric's file format: a
metric declares how to read its own sidecar, the reader walks the registry so no
caller names a metric, and one unreadable file costs that run's numbers instead of
the sweep's.
"""

from pathlib import Path

import orjson
import pytest

from glossogen.evaluation.metric_core.keyed_observation import KeyedObservation
from glossogen.evaluation.metric_core.keyed_observation_reader import read_keyed_observations
from glossogen.evaluation.metric_core.sidecar_reading import (
    key_text,
    number_or_none,
    read_json_sidecar,
    read_jsonl_sidecar,
)
from glossogen.evaluation.metrics.communication.communication_feature_presence_metric import (
    CommunicationFeaturePresenceMetric,
)
from glossogen.evaluation.metrics.communication.communication_open_coding_metric import (
    CommunicationOpenCodingMetric,
)
from glossogen.evaluation.metrics.language_repetition_metric import LanguageRepetitionMetric
from glossogen.evaluation.metrics.protocol_probe.protocol_probe_replica_self_similarity_metric import (  # noqa: E501
    ProtocolProbeReplicaSelfSimilarityMetric,
)
from glossogen.run_analysis.aggregation import Aggregate
from glossogen.run_analysis.analysis_field_catalog import build_field_catalog
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_query_engine import run_analysis_query
from glossogen.run_analysis.analysis_query_models import (
    AnalysisQuerySpec,
    MeasureSpec,
    ResultSort,
)
from glossogen.run_analysis.analysis_run_record import (
    AnalysisRunRecord,
    MetricValues,
    load_analysis_records,
)
from glossogen.run_analysis.measure_resolution import MeasureSource
from tests.fakes.export_run_records import make_agent, make_record


def write(run_dir: Path, name: str, payload: object) -> None:
    """Write one sidecar file into a run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / name).write_bytes(orjson.dumps(payload))


# --- what each metric reads back ------------------------------------------------


async def test_feature_presence_reads_one_confidence_per_category(tmp_path: Path) -> None:
    write(
        run_dir=tmp_path,
        name="communication_feature_presence.json",
        payload={
            "scores": [
                {"category_id": "telegraphic_ellipsis", "confidence": 0.7, "justification": "x"},
                {"category_id": "first_letter_abbreviation", "confidence": 0.0},
            ]
        },
    )

    observations = await CommunicationFeaturePresenceMetric().read_keyed_observations(
        run_dir=tmp_path
    )

    assert [(o.keys["category_id"], o.value) for o in observations] == [
        ("telegraphic_ellipsis", 0.7),
        ("first_letter_abbreviation", 0.0),
    ]


async def test_a_category_with_no_confidence_is_dropped_rather_than_zeroed(
    tmp_path: Path,
) -> None:
    """The rule the whole analysis path rests on, applied one layer earlier."""
    write(
        run_dir=tmp_path,
        name="communication_feature_presence.json",
        payload={"scores": [{"category_id": "unscored", "confidence": None}]},
    )

    observations = await CommunicationFeaturePresenceMetric().read_keyed_observations(
        run_dir=tmp_path
    )

    assert observations == []


async def test_open_coding_reads_each_label_as_a_presence(tmp_path: Path) -> None:
    write(
        run_dir=tmp_path,
        name="communication_open_coding.json",
        payload={"labels": [{"text": "two-letter symptom code"}, {"text": "positional slots"}]},
    )

    observations = await CommunicationOpenCodingMetric().read_keyed_observations(run_dir=tmp_path)

    assert [o.value for o in observations] == [1.0, 1.0]
    assert observations[0].keys["label"] == "two-letter symptom code"


async def test_language_repetition_reads_one_factor_per_message(tmp_path: Path) -> None:
    rows = [
        {
            "message_id": "m1",
            "channel_id": "link",
            "sender_agent_id": "field_observer",
            "round_number": 1,
            "repetition_factor": 1.0,
        },
        {
            "message_id": "m2",
            "channel_id": "link_b",
            "sender_agent_id": "engineer",
            "round_number": 2,
            "repetition_factor": 1.4,
        },
    ]
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "language_repetition_messages.jsonl").write_bytes(
        b"\n".join(orjson.dumps(row) for row in rows) + b"\n"
    )

    observations = await LanguageRepetitionMetric().read_keyed_observations(run_dir=tmp_path)

    assert [o.value for o in observations] == [1.0, 1.4]
    assert observations[1].keys == {
        "message_id": "m2",
        "channel_id": "link_b",
        "sender_agent_id": "engineer",
        "round_number": "2",
    }


async def test_probe_similarity_carries_its_group_fields_as_keys(tmp_path: Path) -> None:
    """The evidence a similarity was computed from is not an axis, so it is left out."""
    write(
        run_dir=tmp_path,
        name="protocol_probe_replica_self_similarity.json",
        payload={
            "groups": [
                {
                    "agent_id": "field_observer",
                    "question_id": "obs_00",
                    "cutoff_round": 11,
                    "replica_indices": [0, 1, 2],
                    "response_texts": ["a", "b", "c"],
                    "cells": [{"a": 0, "b": 1, "similarity": 0.5}],
                    "mean_similarity": 0.69,
                }
            ]
        },
    )

    observations = await ProtocolProbeReplicaSelfSimilarityMetric().read_keyed_observations(
        run_dir=tmp_path
    )

    assert observations[0].value == pytest.approx(0.69)
    assert observations[0].keys["agent_id"] == "field_observer"
    assert observations[0].keys["cutoff_round"] == "11"
    assert "response_texts" not in observations[0].keys
    assert "cells" not in observations[0].keys


# --- the reader that walks the registry -----------------------------------------


async def test_the_reader_returns_only_the_metrics_this_run_has_files_for(
    tmp_path: Path,
) -> None:
    write(
        run_dir=tmp_path,
        name="communication_feature_presence.json",
        payload={"scores": [{"category_id": "a", "confidence": 0.5}]},
    )

    found = await read_keyed_observations(run_dir=tmp_path)

    assert list(found) == ["communication_feature_presence"]


async def test_a_run_with_no_sidecars_reads_as_nothing(tmp_path: Path) -> None:
    assert await read_keyed_observations(run_dir=tmp_path) == {}


async def test_an_unreadable_sidecar_costs_that_metric_and_not_the_run(
    tmp_path: Path,
) -> None:
    """A cohort spans months of metric versions; one bad file must not fail the sweep."""
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "communication_feature_presence.json").write_text("{ truncated")
    write(
        run_dir=tmp_path,
        name="communication_open_coding.json",
        payload={"labels": [{"text": "still readable"}]},
    )

    found = await read_keyed_observations(run_dir=tmp_path)

    assert list(found) == ["communication_open_coding"]


async def test_a_half_written_jsonl_keeps_the_rows_before_the_break(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "rows.jsonl"
    path.write_text('{"a": 1}\n{"a": 2}\n{"a": 3\n')

    rows = await read_jsonl_sidecar(path=path)

    assert rows == [{"a": 1}, {"a": 2}]


async def test_a_sidecar_that_is_not_an_object_is_skipped(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "list.json"
    path.write_bytes(orjson.dumps([1, 2, 3]))

    assert await read_json_sidecar(path=path) is None


def test_a_boolean_is_not_a_number() -> None:
    """``True`` would otherwise average as 1.0 and silently enter a mean."""
    assert number_or_none(value=True) is None
    assert number_or_none(value=1) == 1.0


def test_a_numeric_key_renders_as_text_for_its_dimension_cell() -> None:
    assert key_text(value=11) == "11"
    assert key_text(value=None) == ""


# --- the grain ------------------------------------------------------------------


def record_with(keyed: dict[str, list[KeyedObservation]]) -> AnalysisRunRecord:
    """A record carrying only what the keyed grain reads."""
    return AnalysisRunRecord(
        run_id="veyru/1",
        has_report=True,
        dimensions={"run_id": "veyru/1", "knob.budget": "800"},
        agents=[],
        run_columns={"total_cost_usd": 2.0},
        metrics={},
        keyed=keyed,
    )


def keyed_spec(measures: list[MeasureSpec], group_by: list[str]) -> AnalysisQuerySpec:
    """A query at the keyed grain."""
    return AnalysisQuerySpec(
        grain=AnalysisGrain.KEYED,
        filters=[],
        group_by=group_by,
        measures=measures,
        sort=ResultSort.GROUP,
        sort_measure_index=0,
        limit=100,
    )


def measure(key: str) -> MeasureSpec:
    """Mean of one metric."""
    return MeasureSpec(source=MeasureSource.METRIC, key=key, aggregate=Aggregate.MEAN)


def test_the_keys_a_metric_used_become_dimensions() -> None:
    record = record_with(
        keyed={
            "communication_feature_presence": [
                KeyedObservation(keys={"category_id": "ellipsis"}, value=0.7),
                KeyedObservation(keys={"category_id": "slots"}, value=0.3),
            ]
        }
    )

    result = run_analysis_query(
        records=[record],
        spec=keyed_spec(
            measures=[measure("communication_feature_presence")], group_by=["key.category_id"]
        ),
    )

    assert [row.group_values[0] for row in result.rows] == ["ellipsis", "slots"]
    assert result.rows[0].cells[0].value == pytest.approx(0.7)


def test_two_metrics_keyed_differently_do_not_share_a_row() -> None:
    """A blank here means the metric said nothing about that key, as everywhere else."""
    record = record_with(
        keyed={
            "communication_feature_presence": [
                KeyedObservation(keys={"category_id": "ellipsis"}, value=0.7)
            ],
            "communication_open_coding": [
                KeyedObservation(keys={"label": "coined codes"}, value=1.0)
            ],
        }
    )

    result = run_analysis_query(
        records=[record],
        spec=keyed_spec(
            measures=[
                measure("communication_feature_presence"),
                measure("communication_open_coding"),
            ],
            group_by=["key.category_id", "key.label"],
        ),
    )

    assert len(result.rows) == 2
    for row in result.rows:
        filled = [cell for cell in row.cells if cell.value is not None]
        assert len(filled) == 1


def test_a_metric_that_was_not_asked_for_contributes_no_rows() -> None:
    record = record_with(
        keyed={
            "communication_open_coding": [
                KeyedObservation(keys={"label": "coined codes"}, value=1.0)
            ]
        }
    )

    result = run_analysis_query(
        records=[record],
        spec=keyed_spec(
            measures=[measure("communication_feature_presence")], group_by=["key.category_id"]
        ),
    )

    assert result.rows == []


def test_the_keyed_grain_reports_no_unit_for_a_run_level_score() -> None:
    """`communication_feature_presence` counts categories; its keyed values are
    confidences. The run-level unit would name the wrong quantity on that axis."""
    record = record_with(
        keyed={
            "communication_feature_presence": [
                KeyedObservation(keys={"category_id": "ellipsis"}, value=0.7)
            ]
        }
    )

    result = run_analysis_query(
        records=[record],
        spec=keyed_spec(
            measures=[measure("communication_feature_presence")], group_by=["key.category_id"]
        ),
    )

    assert result.measures[0].score_unit == ""


async def test_sidecars_are_not_read_for_the_grains_that_cannot_use_them(
    tmp_path: Path,
) -> None:
    """Reading them costs a file open per metric per run, on every other grain for nothing."""
    write(
        run_dir=tmp_path,
        name="communication_feature_presence.json",
        payload={"scores": [{"category_id": "a", "confidence": 0.5}]},
    )
    record = make_record(
        run_id="veyru/1",
        scenario_name="veyru",
        scenario_config={},
        labels=[],
        agents=[make_agent(agent_id="field_observer", model="m", provider="anthropic")],
        measurements=None,
        total_cost_usd=1.0,
        current_round=1,
    )
    record = record._replace(summary=record.summary.model_copy(update={"run_dir": str(tmp_path)}))

    without = await load_analysis_records(runs=[record.summary], read_sidecars=False)
    with_sidecars = await load_analysis_records(runs=[record.summary], read_sidecars=True)

    assert without[0].keyed == {}
    assert list(with_sidecars[0].keyed) == ["communication_feature_presence"]


def test_a_per_team_metric_is_reachable_under_its_registry_name() -> None:
    """A metric that scores each channel separately reports one measurement per team
    (``language_repetition_team_a``) but writes one sidecar registered under
    ``language_repetition``. Offering the report's names at this grain would offer
    names no keyed row carries, and the metric would be unreachable."""
    record = record_with(
        keyed={
            "language_repetition": [
                KeyedObservation(keys={"channel_id": "link_a", "message_id": "m1"}, value=1.2),
                KeyedObservation(keys={"channel_id": "link_b", "message_id": "m2"}, value=1.4),
            ]
        }
    )._replace(
        metrics={
            "language_repetition_team_a": MetricValues(
                score=1.2, per_round={}, per_agent={}, score_unit="factor"
            )
        }
    )

    catalog = build_field_catalog(records=[record], grain=AnalysisGrain.KEYED)
    offered = {measure.key for measure in catalog.measures if measure.source == "metric"}

    assert offered == {"language_repetition"}
    assert catalog.observation_count == 2


def test_the_channel_a_metric_scored_stays_a_dimension() -> None:
    """Splitting by team is then a group-by, and not splitting keeps them together —
    which the name-splitting form cannot express."""
    record = record_with(
        keyed={
            "language_repetition": [
                KeyedObservation(keys={"channel_id": "link_a", "message_id": "m1"}, value=1.0),
                KeyedObservation(keys={"channel_id": "link_a", "message_id": "m2"}, value=1.5),
                KeyedObservation(keys={"channel_id": "link_b", "message_id": "m3"}, value=2.0),
            ]
        }
    )

    result = run_analysis_query(
        records=[record],
        spec=keyed_spec(measures=[measure("language_repetition")], group_by=["key.channel_id"]),
    )

    assert [row.group_values[0] for row in result.rows] == ["link_a", "link_b"]
    assert result.rows[0].cells[0].value == pytest.approx(1.25)
    assert result.rows[1].cells[0].observation_count == 1
