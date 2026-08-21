"""How runs become CSV columns, and what an empty cell is allowed to mean.

The rule worth testing hardest is that a blank metric cell and a `0.0` metric
cell say different things. Blank means no number exists: the metric decided it did
not apply, or was never run, or the run has no report. `0.0` means the metric ran
and counted zero, which is a real observation for every metric that counts
occurrences. Filling blanks with zeros would merge the two and bias any average
taken over the column, and nothing would fail when it happened.

The rest covers the parts that a scenario nobody has written yet still has to
survive: knobs of any shape, a knob named after a metric, and a selection whose
runs come from different scenarios.
"""

from datetime import UTC, datetime

from glossogen.evaluation.metric_core.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.evaluation.reports.evaluation_cost import EvaluationCost, EvaluationTokenUsage
from glossogen.evaluation.reports.evaluation_report import EvaluationReport
from glossogen.models.event import RunStatus
from glossogen.run_export.agent_level_frame import build_agent_level_frame
from glossogen.run_export.csv_export_archive import build_export_frames
from glossogen.run_export.export_column_catalog import build_export_preview
from glossogen.run_export.export_request_models import (
    CsvExportRequest,
    ExportFrame,
    FilterRunSelection,
)
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.knob_flattening import knob_cells_by_key
from glossogen.run_export.label_value_columns import label_cells_by_key
from glossogen.run_export.metric_column_projection import measurements_by_name, metric_score_cell
from glossogen.run_export.round_level_frame import build_round_level_frame
from glossogen.run_export.run_level_frame import build_run_level_frame
from glossogen.run_export.run_selection_resolution import partition_explicit_run_ids
from glossogen.server.runs.models import AgentModelSummary, RunSummary

ZERO_COST = EvaluationCost(
    usage=EvaluationTokenUsage(
        input_tokens=0,
        output_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    ),
    estimated_cost_usd=0.0,
    model="test",
    provider_name="test",
)


def make_summary(
    run_id: str,
    scenario_name: str,
    scenario_config: dict[str, object],
    labels: list[str],
) -> RunSummary:
    """Build a run summary carrying only what the column projections read."""
    return RunSummary(
        run_id=run_id,
        scenario_name=scenario_name,
        scenario_description="",
        scenario_config=scenario_config,
        timestamp=datetime(2026, 5, 4, 18, 53, 43, tzinfo=UTC),
        total_messages=81,
        total_cost_usd=1.25,
        duration_seconds=600.0,
        status=RunStatus.SCENARIO_COMPLETE,
        has_evaluation=True,
        evaluation_in_progress=False,
        run_dir=f"/runs/{run_id}",
        fork_source=None,
        replace_agent_source=None,
        cross_run_replace_agent_source=None,
        resume_at_round_source=None,
        models=["claude-sonnet-4-6"],
        provider="anthropic",
        agent_models=[
            AgentModelSummary(
                agent_id="field_observer",
                role_name="Field Observer",
                model="claude-sonnet-4-6",
                provider="anthropic",
            )
        ],
        labels=labels,
        has_note=False,
        current_round=15,
        evaluation_content_hash=None,
    )


def make_measurement(metric_name: str, score: float) -> Measurement:
    """Build a measurement with one round and one agent observation."""
    return Measurement(
        metric_name=metric_name,
        score=score,
        score_unit="things",
        summary="a summary",
        per_round=[RoundObservation(round_number=1, value=score, note="")],
        per_agent=[AgentObservation(agent_id="field_observer", value=score, note="")],
    )


def make_record(
    run_id: str,
    scenario_name: str,
    scenario_config: dict[str, object],
    labels: list[str],
    measurements: list[Measurement] | None,
) -> ExportRunRecord:
    """Pair a synthetic summary with a report, or with no report at all."""
    summary = make_summary(
        run_id=run_id,
        scenario_name=scenario_name,
        scenario_config=scenario_config,
        labels=labels,
    )
    if measurements is None:
        return ExportRunRecord(summary=summary, report=None)
    return ExportRunRecord(
        summary=summary,
        report=EvaluationReport(
            simulation_id=run_id,
            scenario_name=scenario_name,
            measurements=measurements,
            evaluation_cost=ZERO_COST,
        ),
    )


def run_level_rows(
    records: list[ExportRunRecord],
    columns: list[str],
    metrics: list[str],
) -> tuple[list[str], list[list[str]]]:
    """Build the wide frame and return its header and materialized rows."""
    frame = build_run_level_frame(
        records=records,
        columns=columns,
        metrics=metrics,
        include_metric_summaries=False,
    )
    return (frame.header, list(frame.rows))


# --- the empty-versus-zero rule -------------------------------------------------


def test_a_metric_that_counted_zero_renders_zero() -> None:
    """Zero refusals is an observation, and the column has to be able to say so."""
    assert (
        metric_score_cell(
            measurement=make_measurement(metric_name="content_filter_refusal", score=0.0)
        )
        == "0.0"
    )


def test_a_metric_with_no_measurement_renders_empty() -> None:
    """No measurement means no number exists, which is not the same as zero."""
    assert metric_score_cell(measurement=None) == ""


def test_an_unevaluated_run_gets_empty_metric_cells_not_zeros() -> None:
    """Averaging a column of zeros for runs that were never scored would be wrong."""
    scored = make_record(
        run_id="veyru/1",
        scenario_name="veyru",
        scenario_config={},
        labels=[],
        measurements=[make_measurement(metric_name="round_success", score=0.6)],
    )
    unscored = make_record(
        run_id="veyru/2",
        scenario_name="veyru",
        scenario_config={},
        labels=[],
        measurements=None,
    )

    header, rows = run_level_rows(
        records=[scored, unscored],
        columns=[],
        metrics=["round_success"],
    )
    column = header.index("metric.round_success")

    assert rows[0][column] == "0.6"
    assert rows[1][column] == ""


def test_a_run_scored_by_a_different_metric_gets_an_empty_cell() -> None:
    """A partial evaluation leaves the metrics it did not run without a number."""
    record = make_record(
        run_id="veyru/1",
        scenario_name="veyru",
        scenario_config={},
        labels=[],
        measurements=[make_measurement(metric_name="round_success", score=0.6)],
    )
    header, rows = run_level_rows(
        records=[record],
        columns=[],
        metrics=["round_success", "perplexity"],
    )

    assert rows[0][header.index("metric.round_success")] == "0.6"
    assert rows[0][header.index("metric.perplexity")] == ""


# --- knob flattening ------------------------------------------------------------


def test_a_nested_knob_explodes_into_dotted_columns() -> None:
    """Per-agent overrides are a mapping, and each leaf is its own column."""
    cells = knob_cells_by_key(
        scenario_config={"model_overrides": {"field_observer": {"model": "gpt-5.4"}}}
    )
    assert cells["knob.model_overrides.field_observer.model"] == "gpt-5.4"


def test_a_list_knob_stays_one_json_cell() -> None:
    """Scheduled events vary in length per run, so an index-per-column would lie."""
    cells = knob_cells_by_key(
        scenario_config={"scheduled_events": [{"at_round": 16, "type": "swap_agent"}]}
    )
    assert cells["knob.scheduled_events"] == '[{"at_round":16,"type":"swap_agent"}]'


def test_a_null_knob_is_empty_rather_than_the_word_none() -> None:
    """``None`` in a cell has to read as absent, not as a Python repr."""
    cells = knob_cells_by_key(scenario_config={"intern_join_round": None})
    assert cells["knob.intern_join_round"] == ""


def test_a_boolean_knob_round_trips_as_a_capitalized_word() -> None:
    """The spelling data-frame libraries parse back into a boolean."""
    cells = knob_cells_by_key(scenario_config={"postmortem_enabled": False})
    assert cells["knob.postmortem_enabled"] == "False"


def test_a_knob_named_after_a_metric_does_not_collide_with_it() -> None:
    """The prefixes exist so a scenario is free to name a knob anything."""
    record = make_record(
        run_id="veyru/1",
        scenario_name="veyru",
        scenario_config={"perplexity": 3},
        labels=[],
        measurements=[make_measurement(metric_name="perplexity", score=2.5)],
    )
    header, rows = run_level_rows(
        records=[record],
        columns=["knob.perplexity"],
        metrics=["perplexity"],
    )

    assert rows[0][header.index("knob.perplexity")] == "3"
    assert rows[0][header.index("metric.perplexity")] == "2.5"


def test_a_knob_holding_control_characters_is_stripped() -> None:
    """Model output reaches these cells, and a spreadsheet refuses a file with them."""
    cells = knob_cells_by_key(scenario_config={"note": "a\x00b\x07c"})
    assert cells["knob.note"] == "abc"


def test_a_knob_holding_a_newline_becomes_one_line() -> None:
    """A newline inside a quoted field is legal CSV and breaks line-oriented tools."""
    cells = knob_cells_by_key(scenario_config={"note": "first\nsecond"})
    assert cells["knob.note"] == "first second"


# --- label columns --------------------------------------------------------------


def test_a_key_value_label_becomes_its_own_column() -> None:
    """Cohorts encode their conditions this way, and that is what gets regressed on."""
    assert label_cells_by_key(labels=["budget=800"]) == {"label.budget": "800"}


def test_a_plain_tag_becomes_a_flag_column() -> None:
    """A tag has no value to put in a cell, but whether a run carries it is the grouping."""
    assert label_cells_by_key(labels=["baseline_oss", "single_team"]) == {
        "label_flag.baseline_oss": "True",
        "label_flag.single_team": "True",
    }


def test_a_repeated_label_key_resolves_the_same_way_every_time() -> None:
    """The run was tagged inconsistently; picking deterministically beats arbitrarily."""
    first = label_cells_by_key(labels=["budget=800", "budget=250"])
    second = label_cells_by_key(labels=["budget=250", "budget=800"])
    assert first == second


# --- explicit id resolution -----------------------------------------------------


def test_a_requested_id_that_resolves_to_nothing_is_reported() -> None:
    """Reported, not skipped: the caller asked for it and has to hear that it is gone."""
    owned = {
        "veyru/1": make_summary(
            run_id="veyru/1", scenario_name="veyru", scenario_config={}, labels=[]
        )
    }
    resolved = partition_explicit_run_ids(run_ids=["veyru/1", "veyru/999"], owned_by_run_id=owned)

    assert [s.run_id for s in resolved.summaries] == ["veyru/1"]
    assert resolved.missing_run_ids == ["veyru/999"]


def test_a_duplicated_id_is_exported_once() -> None:
    """A checkbox list can repeat an id; the table must not repeat the run."""
    owned = {
        "veyru/1": make_summary(
            run_id="veyru/1", scenario_name="veyru", scenario_config={}, labels=[]
        )
    }
    resolved = partition_explicit_run_ids(run_ids=["veyru/1", "veyru/1"], owned_by_run_id=owned)

    assert [s.run_id for s in resolved.summaries] == ["veyru/1"]
    assert resolved.missing_run_ids == []


def test_an_id_with_no_separator_is_reported_rather_than_crashing() -> None:
    """Whatever a caller sends, the answer is a message and not a stack trace."""
    resolved = partition_explicit_run_ids(run_ids=["not-a-run-id"], owned_by_run_id={})
    assert resolved.missing_run_ids == ["not-a-run-id"]


def test_rows_come_out_in_run_id_order_whatever_order_was_asked_for() -> None:
    """Run ids are unique, so sorting on them makes the same selection export the same bytes."""
    owned = {
        "veyru/2": make_summary(
            run_id="veyru/2", scenario_name="veyru", scenario_config={}, labels=[]
        ),
        "veyru/1": make_summary(
            run_id="veyru/1", scenario_name="veyru", scenario_config={}, labels=[]
        ),
    }
    resolved = partition_explicit_run_ids(run_ids=["veyru/2", "veyru/1"], owned_by_run_id=owned)
    assert [s.run_id for s in resolved.summaries] == ["veyru/1", "veyru/2"]


# --- the preview ----------------------------------------------------------------


def test_the_preview_unions_knobs_across_scenarios_and_reports_coverage() -> None:
    """A knob one scenario defines is blank for the other, and the count says so."""
    records = [
        make_record(
            run_id="a/1",
            scenario_name="a",
            scenario_config={"grid_size": 4},
            labels=[],
            measurements=[],
        ),
        make_record(
            run_id="b/1",
            scenario_name="b",
            scenario_config={"container_count": 9},
            labels=[],
            measurements=[],
        ),
    ]
    preview = build_export_preview(records=records, missing_run_ids=[], raw_bytes_estimate=None)
    coverage = {c.key: c.runs_with_value for c in preview.columns}

    assert preview.scenario_names == ["a", "b"]
    assert coverage["knob.grid_size"] == 1
    assert coverage["knob.container_count"] == 1


def test_the_preview_names_metrics_the_reports_carry_not_a_registry() -> None:
    """Metrics emit names built at run time, so the data is the only complete list."""
    records = [
        make_record(
            "veyru/1",
            "veyru",
            {},
            [],
            [
                make_measurement(
                    metric_name="round_success_after_resume_round_16_field_observer", score=0.5
                )
            ],
        )
    ]
    preview = build_export_preview(records=records, missing_run_ids=[], raw_bytes_estimate=None)

    assert [m.metric_name for m in preview.metrics] == [
        "round_success_after_resume_round_16_field_observer"
    ]


def test_the_preview_counts_runs_with_no_report() -> None:
    """An empty metric cell is explained by this count rather than left to guess."""
    records = [
        make_record(
            run_id="veyru/1",
            scenario_name="veyru",
            scenario_config={},
            labels=[],
            measurements=[make_measurement(metric_name="round_success", score=1.0)],
        ),
        make_record(
            run_id="veyru/2",
            scenario_name="veyru",
            scenario_config={},
            labels=[],
            measurements=None,
        ),
    ]
    preview = build_export_preview(records=records, missing_run_ids=[], raw_bytes_estimate=None)

    assert preview.evaluated_run_count == 1
    assert preview.runs_without_report == ["veyru/2"]


def test_identity_columns_cannot_be_deselected() -> None:
    """Every other table joins back on the run id."""
    records = [
        make_record(
            run_id="veyru/1",
            scenario_name="veyru",
            scenario_config={},
            labels=[],
            measurements=[],
        )
    ]
    preview = build_export_preview(records=records, missing_run_ids=[], raw_bytes_estimate=None)
    always = {c.key for c in preview.columns if c.always_included}

    assert always == {"run_id", "scenario_name"}

    header, _ = run_level_rows(records=records, columns=[], metrics=[])
    assert header == ["run_id", "scenario_name"]


def test_a_request_naming_no_frames_builds_nothing() -> None:
    """The endpoint refuses this, and the builder agrees rather than guessing."""
    request = CsvExportRequest(
        selection=FilterRunSelection(
            kind="filters",
            scenario=[],
            labels=[],
            run_id_contains=None,
            knob=[],
            status=None,
            contains_agent_id=None,
        ),
        frames=[],
        columns=[],
        metrics=[],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    assert build_export_frames(records=[], request=request) == []


def test_the_round_table_carries_one_row_per_round_observed() -> None:
    """Rows follow what a metric reported, so absence stays absent."""
    records = [
        make_record(
            run_id="veyru/1",
            scenario_name="veyru",
            scenario_config={},
            labels=[],
            measurements=[make_measurement(metric_name="round_success", score=1.0)],
        ),
        make_record(
            run_id="veyru/2",
            scenario_name="veyru",
            scenario_config={},
            labels=[],
            measurements=None,
        ),
    ]
    frame = build_round_level_frame(
        records=records,
        columns=[],
        metrics=["round_success"],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    rows = list(frame.rows)

    assert len(rows) == 1
    columns = dict(zip(frame.header, rows[0]))
    assert columns["run_id"] == "veyru/1"
    assert columns["round_number"] == "1"
    assert columns["metric.round_success"] == "1.0"


def test_the_round_table_gives_each_metric_its_own_column() -> None:
    """A metric is a variable, so two of them share a round row rather than stacking."""
    frame = build_round_level_frame(
        records=[
            make_record(
                run_id="veyru/1",
                scenario_name="veyru",
                scenario_config={},
                labels=[],
                measurements=[
                    make_measurement(metric_name="round_success", score=1.0),
                    make_measurement(metric_name="perplexity", score=4.5),
                ],
            )
        ],
        columns=[],
        metrics=["round_success", "perplexity"],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    [row] = list(frame.rows)
    columns = dict(zip(frame.header, row))

    assert "metric_name" not in frame.header
    assert columns["metric.round_success"] == "1.0"
    assert columns["metric.perplexity"] == "4.5"


def test_a_round_a_metric_said_nothing_about_is_empty_not_zero() -> None:
    """The rule the wide shape has to keep: a gap in a row is still not a zero."""
    quiet = Measurement(
        metric_name="neologism",
        score=1.0,
        score_unit="rounds",
        summary="a summary",
        per_round=[RoundObservation(round_number=2, value=1.0, note="")],
        per_agent=[],
    )
    frame = build_round_level_frame(
        records=[
            make_record(
                run_id="veyru/1",
                scenario_name="veyru",
                scenario_config={},
                labels=[],
                measurements=[make_measurement(metric_name="round_success", score=1.0), quiet],
            )
        ],
        columns=[],
        metrics=["round_success", "neologism"],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    rows = [dict(zip(frame.header, row)) for row in frame.rows]

    assert [row["round_number"] for row in rows] == ["1", "2"]
    assert rows[0]["metric.neologism"] == ""
    assert rows[1]["metric.round_success"] == ""


def test_only_the_frames_requested_are_built() -> None:
    """One table in the request, one table out, and the CSV path returns it bare."""
    request = CsvExportRequest(
        selection=FilterRunSelection(
            kind="filters",
            scenario=[],
            labels=[],
            run_id_contains=None,
            knob=[],
            status=None,
            contains_agent_id=None,
        ),
        frames=[ExportFrame.RUN_LEVEL],
        columns=[],
        metrics=[],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    frames = build_export_frames(
        records=[
            make_record(
                run_id="veyru/1",
                scenario_name="veyru",
                scenario_config={},
                labels=[],
                measurements=[],
            )
        ],
        request=request,
    )
    assert [frame.name for frame in frames] == ["run_level"]


def test_measurements_index_keeps_the_first_of_a_repeated_name() -> None:
    """A report merged across invocations can carry a duplicate; the cell needs one."""
    indexed = measurements_by_name(
        measurements=[
            make_measurement(metric_name="round_success", score=1.0),
            make_measurement(metric_name="round_success", score=0.0),
        ]
    )
    assert indexed["round_success"].score == 1.0


# --- the per-agent table --------------------------------------------------------


def test_the_agent_table_carries_one_row_per_registered_agent() -> None:
    """Rows follow the roster, so the table is the roster even before any metric fills it."""
    frame = build_agent_level_frame(
        records=[
            make_record(
                run_id="veyru/1",
                scenario_name="veyru",
                scenario_config={},
                labels=[],
                measurements=[make_measurement(metric_name="protocol_explanation", score=1.0)],
            )
        ],
        columns=[],
        metrics=["protocol_explanation"],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    rows = list(frame.rows)

    assert len(rows) == 1
    columns = dict(zip(frame.header, rows[0]))
    assert columns["agent_id"] == "field_observer"
    assert columns["metric.protocol_explanation"] == "1.0"


def test_the_agent_table_resolves_model_and_role_from_the_roster() -> None:
    """Grouping by model is the point, and the observation itself carries neither."""
    frame = build_agent_level_frame(
        records=[
            make_record(
                run_id="veyru/1",
                scenario_name="veyru",
                scenario_config={},
                labels=[],
                measurements=[make_measurement(metric_name="protocol_explanation", score=1.0)],
            )
        ],
        columns=[],
        metrics=["protocol_explanation"],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    columns = dict(zip(frame.header, list(frame.rows)[0]))

    assert columns["agent_model"] == "claude-sonnet-4-6"
    assert columns["agent_role"] == "Field Observer"
    assert columns["agent_provider"] == "anthropic"


def test_the_agent_table_still_lists_agents_when_no_metric_reports_per_agent() -> None:
    """The common case, and the reason the table is keyed on the roster rather than on metrics."""
    frame = build_agent_level_frame(
        records=[
            make_record(
                run_id="veyru/1",
                scenario_name="veyru",
                scenario_config={},
                labels=[],
                measurements=None,
            )
        ],
        columns=[],
        metrics=["protocol_explanation"],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    [row] = list(frame.rows)
    columns = dict(zip(frame.header, row))

    assert columns["agent_id"] == "field_observer"
    assert columns["agent_model"] == "claude-sonnet-4-6"
    assert columns["metric.protocol_explanation"] == ""


def test_repeating_run_columns_widens_the_per_round_table() -> None:
    """Excel users will not join back on run_id, so the option exists and defaults on."""
    record = make_record(
        run_id="veyru/1",
        scenario_name="veyru",
        scenario_config={"round_count": 15},
        labels=[],
        measurements=[make_measurement(metric_name="round_success", score=1.0)],
    )
    narrow = build_round_level_frame(
        records=[record],
        columns=["knob.round_count"],
        metrics=["round_success"],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    wide = build_round_level_frame(
        records=[record],
        columns=["knob.round_count"],
        metrics=["round_success"],
        repeat_run_columns=True,
        include_metric_summaries=False,
    )

    assert "knob.round_count" not in narrow.header
    assert "knob.round_count" in wide.header


def test_a_repeated_column_key_emits_the_column_once() -> None:
    """A scripted caller can send a key twice; no reader expects it twice.

    The modal cannot produce this, because it sends a Set. The REST body can.
    """
    request = CsvExportRequest(
        selection=FilterRunSelection(
            kind="filters",
            scenario=[],
            labels=[],
            run_id_contains=None,
            knob=[],
            status=None,
            contains_agent_id=None,
        ),
        frames=[ExportFrame.RUN_LEVEL],
        columns=["status", "status"],
        metrics=["round_success", "round_success"],
        repeat_run_columns=False,
        include_metric_summaries=False,
    )
    [frame] = build_export_frames(
        records=[
            make_record(
                run_id="veyru/1",
                scenario_name="veyru",
                scenario_config={},
                labels=[],
                measurements=[make_measurement(metric_name="round_success", score=1.0)],
            )
        ],
        request=request,
    )

    assert frame.header == [
        "run_id",
        "scenario_name",
        "status",
        "metric.round_success",
        "metric_rounds.round_success",
    ]
    assert len(frame.header) == len(set(frame.header))
