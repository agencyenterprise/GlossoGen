"""Grouping and aggregating runs, and what a missing number is allowed to do.

The rule under the most pressure is the one the export already settled: a metric
that reported nothing is not a zero. Here it has to survive one more step, because
an aggregate that quietly folded blanks in as zeros would report a mean that no
observation supports and nothing would fail.

The rest covers the shapes a chart depends on: rows exist at a grain only where an
observation does, a knob sweep orders numerically rather than lexicographically,
and the counts behind every aggregate are reported alongside it.
"""

import pytest
from pydantic import ValidationError

from glossogen.evaluation.metric_core.keyed_observation import KeyedObservation
from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.run_analysis.aggregation import Aggregate
from glossogen.run_analysis.analysis_field_catalog import build_field_catalog
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_limits import MAX_DIMENSION_VALUES
from glossogen.run_analysis.analysis_query_engine import run_analysis_query
from glossogen.run_analysis.analysis_query_models import (
    AnalysisQuerySpec,
    MeasureSpec,
    ResultSort,
)
from glossogen.run_analysis.analysis_result_models import AnalysisResult
from glossogen.run_analysis.analysis_run_record import (
    AnalysisRunRecord,
    MetricValues,
    project_run_record,
)
from glossogen.run_analysis.dimension_filter import DimensionFilter, FilterOperator
from glossogen.run_analysis.measure_resolution import (
    NUMERIC_RUN_COLUMNS,
    RUN_COLUMN_UNITS,
    MeasureSource,
    run_column_values,
)
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.server.runs.models import AgentModelSummary
from tests.fakes.export_run_records import make_agent, make_measurement, make_record

SONNET = make_agent(agent_id="field_observer", model="claude-sonnet-4-6", provider="anthropic")
ENGINEER = make_agent(
    agent_id="stabilization_engineer", model="claude-sonnet-4-6", provider="anthropic"
)
LLAMA = make_agent(
    agent_id="field_observer", model="meta-llama/Llama-3.3-70B-Instruct", provider="self-hosted"
)


def record(
    run_id: str,
    budget: int,
    measurements: list[Measurement] | None,
    agents: list[AgentModelSummary] | None,
) -> ExportRunRecord:
    """Build one veyru-shaped record at a given budget knob."""
    roster = [SONNET, ENGINEER]
    if agents is not None:
        roster = agents
    return make_record(
        run_id=run_id,
        scenario_name="veyru",
        scenario_config={"round_time_budget_seconds": budget, "round_count": 15},
        labels=["baseline"],
        agents=roster,
        measurements=measurements,
        total_cost_usd=2.0,
        current_round=15,
    )


def metric(name: str, score: float) -> Measurement:
    """Build a run-level-only measurement."""
    return make_measurement(metric_name=name, score=score, per_round=[], per_agent=[])


def query(
    group_by: list[str],
    measures: list[MeasureSpec],
    grain: AnalysisGrain,
    filters: list[DimensionFilter],
) -> AnalysisQuerySpec:
    """Build a query spec with the parts a test does not vary held fixed."""
    return AnalysisQuerySpec(
        grain=grain,
        filters=filters,
        group_by=group_by,
        measures=measures,
        sort=ResultSort.GROUP,
        sort_measure_index=0,
        limit=500,
    )


def mean_of(name: str) -> MeasureSpec:
    """Mean of one metric."""
    return MeasureSpec(source=MeasureSource.METRIC, key=name, aggregate=Aggregate.MEAN)


def projected(records: list[ExportRunRecord]) -> list[AnalysisRunRecord]:
    """Reduce export records the way the CLI and the endpoints do before querying.

    Sidecars are off: every grain but the keyed one ignores them, and the keyed grain
    is driven from records built directly in its own tests.
    """
    return [project_run_record(record=record, keyed={}) for record in records]


def answer(records: list[ExportRunRecord], spec: AnalysisQuerySpec) -> AnalysisResult:
    """Run one query."""
    return run_analysis_query(records=projected(records=records), spec=spec)


# --- a blank is not a zero ------------------------------------------------------


def test_a_run_with_no_report_is_excluded_from_the_mean_and_counted_as_missing() -> None:
    records = [
        record(
            run_id="veyru/1", budget=800, measurements=[metric("round_success", 0.8)], agents=None
        ),
        record(run_id="veyru/2", budget=800, measurements=None, agents=None),
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=["knob.round_time_budget_seconds"],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[],
        ),
    )

    cell = result.rows[0].cells[0]
    assert cell.value == pytest.approx(0.8)
    assert cell.observation_count == 1
    assert cell.missing_count == 1


def test_a_measured_zero_is_counted_where_a_missing_metric_is_not() -> None:
    records = [
        record(
            run_id="veyru/1", budget=800, measurements=[metric("round_success", 0.0)], agents=None
        ),
        record(
            run_id="veyru/2", budget=800, measurements=[metric("round_success", 1.0)], agents=None
        ),
        record(run_id="veyru/3", budget=800, measurements=[metric("neologism", 3.0)], agents=None),
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=[],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[],
        ),
    )

    cell = result.rows[0].cells[0]
    assert cell.value == pytest.approx(0.5)
    assert cell.observation_count == 2
    assert cell.missing_count == 1


def test_a_group_where_every_value_is_missing_aggregates_to_nothing() -> None:
    records = [record(run_id="veyru/1", budget=800, measurements=None, agents=None)]

    result = answer(
        records=records,
        spec=query(
            group_by=["scenario_name"],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[],
        ),
    )

    assert result.rows[0].cells[0].value is None
    assert result.rows[0].cells[0].observation_count == 0


# --- grains ---------------------------------------------------------------------


def test_the_run_grain_keeps_a_row_for_a_run_that_was_never_evaluated() -> None:
    records = [
        record(
            run_id="veyru/1", budget=800, measurements=[metric("round_success", 0.5)], agents=None
        ),
        record(run_id="veyru/2", budget=800, measurements=None, agents=None),
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=["run_id"],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[],
        ),
    )

    assert result.observation_count == 2
    assert [row.group_values[0] for row in result.rows] == ["veyru/1", "veyru/2"]


def test_the_round_grain_has_a_row_only_where_a_selected_metric_reported() -> None:
    per_round = make_measurement(
        metric_name="perplexity",
        score=4.0,
        per_round=[(1, 3.0), (3, 5.0)],
        per_agent=[],
    )
    records = [record(run_id="veyru/1", budget=800, measurements=[per_round], agents=None)]

    result = answer(
        records=records,
        spec=query(
            group_by=["round_number"],
            measures=[mean_of("perplexity")],
            grain=AnalysisGrain.ROUND,
            filters=[],
        ),
    )

    assert [row.group_values[0] for row in result.rows] == ["1", "3"]
    assert result.observation_count == 2


def test_a_round_one_metric_skipped_still_has_a_row_with_an_empty_cell() -> None:
    reported_every_round = make_measurement(
        metric_name="perplexity", score=4.0, per_round=[(1, 3.0), (2, 5.0)], per_agent=[]
    )
    reported_once = make_measurement(
        metric_name="neologism", score=1.0, per_round=[(2, 1.0)], per_agent=[]
    )
    records = [
        record(
            run_id="veyru/1",
            budget=800,
            measurements=[reported_every_round, reported_once],
            agents=None,
        )
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=["round_number"],
            measures=[mean_of("perplexity"), mean_of("neologism")],
            grain=AnalysisGrain.ROUND,
            filters=[],
        ),
    )

    first_round = result.rows[0]
    assert first_round.group_values == ["1"]
    assert first_round.cells[1].value is None
    assert first_round.cells[1].missing_count == 1


def test_the_agent_grain_is_keyed_on_the_roster_not_on_what_metrics_reported() -> None:
    scored_one_agent = make_measurement(
        metric_name="content_filter_refusal",
        score=2.0,
        per_round=[],
        per_agent=[("field_observer", 2.0)],
    )
    records = [record(run_id="veyru/1", budget=800, measurements=[scored_one_agent], agents=None)]

    result = answer(
        records=records,
        spec=query(
            group_by=["agent_id"],
            measures=[mean_of("content_filter_refusal")],
            grain=AnalysisGrain.AGENT,
            filters=[],
        ),
    )

    assert [row.group_values[0] for row in result.rows] == [
        "field_observer",
        "stabilization_engineer",
    ]
    assert result.rows[1].cells[0].value is None


def test_an_agent_only_a_metric_named_still_gets_a_row() -> None:
    scored_a_stranger = make_measurement(
        metric_name="content_filter_refusal",
        score=1.0,
        per_round=[],
        per_agent=[("observer_gen2", 1.0)],
    )
    records = [
        record(
            run_id="veyru/1",
            budget=800,
            measurements=[scored_a_stranger],
            agents=[SONNET],
        )
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=["agent_id"],
            measures=[mean_of("content_filter_refusal")],
            grain=AnalysisGrain.AGENT,
            filters=[],
        ),
    )

    assert sorted(row.group_values[0] for row in result.rows) == ["field_observer", "observer_gen2"]


# --- grouping, ordering, filtering ----------------------------------------------


def test_a_numeric_knob_sweep_orders_numerically_and_not_as_text() -> None:
    records = [
        record(
            run_id=f"veyru/{budget}",
            budget=budget,
            measurements=[metric("round_success", 0.5)],
            agents=None,
        )
        for budget in (2000, 800, 10000)
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=["knob.round_time_budget_seconds"],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[],
        ),
    )

    assert [row.group_values[0] for row in result.rows] == ["800", "2000", "10000"]


def test_two_group_by_keys_make_one_row_per_pair() -> None:
    records = [
        record(
            run_id="veyru/1",
            budget=800,
            measurements=[metric("round_success", 1.0)],
            agents=[SONNET],
        ),
        record(
            run_id="veyru/2",
            budget=800,
            measurements=[metric("round_success", 0.0)],
            agents=[LLAMA],
        ),
        record(
            run_id="veyru/3",
            budget=2000,
            measurements=[metric("round_success", 0.5)],
            agents=[LLAMA],
        ),
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=["knob.round_time_budget_seconds", "model_class"],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[],
        ),
    )

    assert [row.group_values for row in result.rows] == [
        ["800", "closed"],
        ["800", "open"],
        ["2000", "open"],
    ]


def test_a_numeric_filter_keeps_the_runs_above_the_bound_and_drops_unparsable_cells() -> None:
    records = [
        record(
            run_id="veyru/1", budget=800, measurements=[metric("round_success", 1.0)], agents=None
        ),
        record(
            run_id="veyru/2", budget=2000, measurements=[metric("round_success", 1.0)], agents=None
        ),
    ]
    records.append(
        make_record(
            run_id="veyru/3",
            scenario_name="veyru",
            scenario_config={"round_time_budget_seconds": "unlimited"},
            labels=[],
            agents=[SONNET],
            measurements=[metric("round_success", 1.0)],
            total_cost_usd=1.0,
            current_round=15,
        )
    )

    result = answer(
        records=records,
        spec=query(
            group_by=["run_id"],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[
                DimensionFilter(
                    key="knob.round_time_budget_seconds",
                    operator=FilterOperator.GREATER_OR_EQUAL,
                    values=["1000"],
                )
            ],
        ),
    )

    assert [row.group_values[0] for row in result.rows] == ["veyru/2"]


def test_an_in_filter_keeps_only_the_named_values() -> None:
    records = [
        record(
            run_id="veyru/1",
            budget=800,
            measurements=[metric("round_success", 1.0)],
            agents=[SONNET],
        ),
        record(
            run_id="veyru/2",
            budget=800,
            measurements=[metric("round_success", 0.0)],
            agents=[LLAMA],
        ),
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=["run_id"],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[
                DimensionFilter(key="model_class", operator=FilterOperator.IN, values=["open"])
            ],
        ),
    )

    assert [row.group_values[0] for row in result.rows] == ["veyru/2"]


def test_sorting_by_a_measure_puts_groups_that_computed_nothing_last() -> None:
    records = [
        record(
            run_id="veyru/1", budget=800, measurements=[metric("round_success", 0.2)], agents=None
        ),
        record(
            run_id="veyru/2", budget=2000, measurements=[metric("round_success", 0.9)], agents=None
        ),
        record(run_id="veyru/3", budget=10000, measurements=None, agents=None),
    ]
    spec = query(
        group_by=["knob.round_time_budget_seconds"],
        measures=[mean_of("round_success")],
        grain=AnalysisGrain.RUN,
        filters=[],
    ).model_copy(update={"sort": ResultSort.MEASURE_DESCENDING})

    result = answer(records=records, spec=spec)

    assert [row.group_values[0] for row in result.rows] == ["2000", "800", "10000"]
    assert result.rows[-1].cells[0].value is None


def test_the_row_limit_clips_the_answer_and_says_so() -> None:
    records = [
        record(
            run_id=f"veyru/{index}",
            budget=index,
            measurements=[metric("round_success", 0.5)],
            agents=None,
        )
        for index in range(10)
    ]
    spec = query(
        group_by=["run_id"],
        measures=[mean_of("round_success")],
        grain=AnalysisGrain.RUN,
        filters=[],
    ).model_copy(update={"limit": 3})

    result = answer(records=records, spec=spec)

    assert len(result.rows) == 3
    assert result.truncated is True


# --- aggregates -----------------------------------------------------------------


def test_spread_over_a_single_observation_is_nothing_rather_than_zero() -> None:
    records = [
        record(
            run_id="veyru/1", budget=800, measurements=[metric("round_success", 0.4)], agents=None
        )
    ]
    spec = query(
        group_by=[],
        measures=[
            MeasureSpec(
                source=MeasureSource.METRIC, key="round_success", aggregate=Aggregate.STDDEV
            ),
            MeasureSpec(source=MeasureSource.METRIC, key="round_success", aggregate=Aggregate.SEM),
            MeasureSpec(
                source=MeasureSource.METRIC, key="round_success", aggregate=Aggregate.COUNT
            ),
        ],
        grain=AnalysisGrain.RUN,
        filters=[],
    )

    result = answer(records=records, spec=spec)

    assert result.rows[0].cells[0].value is None
    assert result.rows[0].cells[1].value is None
    assert result.rows[0].cells[2].value == pytest.approx(1.0)


def test_a_run_column_measures_the_run_itself_and_needs_no_report() -> None:
    records = [
        make_record(
            run_id="veyru/1",
            scenario_name="veyru",
            scenario_config={},
            labels=[],
            agents=[SONNET],
            measurements=None,
            total_cost_usd=3.5,
            current_round=15,
        ),
        make_record(
            run_id="veyru/2",
            scenario_name="veyru",
            scenario_config={},
            labels=[],
            agents=[SONNET],
            measurements=None,
            total_cost_usd=1.5,
            current_round=15,
        ),
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=[],
            measures=[
                MeasureSpec(
                    source=MeasureSource.RUN_COLUMN,
                    key="total_cost_usd",
                    aggregate=Aggregate.SUM,
                )
            ],
            grain=AnalysisGrain.RUN,
            filters=[],
        ),
    )

    assert result.rows[0].cells[0].value == pytest.approx(5.0)
    assert result.measures[0].score_unit == "USD"


# --- the field catalog ----------------------------------------------------------


def test_the_catalog_offers_the_knobs_and_the_grain_key_as_dimensions() -> None:
    per_round = make_measurement(
        metric_name="perplexity", score=4.0, per_round=[(1, 3.0)], per_agent=[]
    )
    records = [record(run_id="veyru/1", budget=800, measurements=[per_round], agents=None)]

    catalog = build_field_catalog(records=projected(records=records), grain=AnalysisGrain.ROUND)

    keys = {dimension.key for dimension in catalog.dimensions}
    assert "knob.round_time_budget_seconds" in keys
    assert "round_number" in keys
    assert catalog.observation_count == 1


def test_the_catalog_reports_a_run_level_only_metric_as_empty_at_the_round_grain() -> None:
    records = [
        record(
            run_id="veyru/1", budget=800, measurements=[metric("round_success", 0.5)], agents=None
        )
    ]

    catalog = build_field_catalog(records=projected(records=records), grain=AnalysisGrain.ROUND)

    assert catalog.observation_count == 0
    scored = {measure.key: measure.rows_with_value for measure in catalog.measures}
    assert scored["round_success"] == 0


def test_the_catalog_caps_the_values_it_lists_but_not_the_count_it_reports() -> None:
    records = [
        record(
            run_id=f"veyru/{index}",
            budget=index,
            measurements=[metric("round_success", 0.5)],
            agents=None,
        )
        for index in range(MAX_DIMENSION_VALUES + 25)
    ]

    catalog = build_field_catalog(records=projected(records=records), grain=AnalysisGrain.RUN)

    budget = next(
        dimension
        for dimension in catalog.dimensions
        if dimension.key == "knob.round_time_budget_seconds"
    )
    assert budget.distinct_count == MAX_DIMENSION_VALUES + 25
    assert len(budget.values) == MAX_DIMENSION_VALUES


def test_the_catalog_names_the_runs_that_have_no_report() -> None:
    records = [
        record(
            run_id="veyru/1", budget=800, measurements=[metric("round_success", 0.5)], agents=None
        ),
        record(run_id="veyru/2", budget=800, measurements=None, agents=None),
    ]

    catalog = build_field_catalog(records=projected(records=records), grain=AnalysisGrain.RUN)

    assert catalog.runs_without_report == ["veyru/2"]


# --- queries that cannot be answered --------------------------------------------


def test_a_query_with_no_measure_is_refused() -> None:
    with pytest.raises(ValidationError):
        query(group_by=["run_id"], measures=[], grain=AnalysisGrain.RUN, filters=[])


def test_a_third_group_by_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        query(
            group_by=["run_id", "scenario_name", "model_class"],
            measures=[mean_of("round_success")],
            grain=AnalysisGrain.RUN,
            filters=[],
        )


def test_sorting_by_a_measure_that_was_not_requested_is_refused() -> None:
    with pytest.raises(ValidationError):
        AnalysisQuerySpec(
            grain=AnalysisGrain.RUN,
            filters=[],
            group_by=["run_id"],
            measures=[mean_of("round_success")],
            sort=ResultSort.MEASURE_DESCENDING,
            sort_measure_index=4,
            limit=100,
        )


# --- what the two clients must agree on -----------------------------------------


def units_agree(records: list[AnalysisRunRecord], spec: AnalysisQuerySpec) -> bool:
    """Whether the catalog labels each measure the way the answer to a query does."""
    catalog = build_field_catalog(records=records, grain=spec.grain)
    offered = {
        f"{measure.source}.{measure.key}": measure.score_unit for measure in catalog.measures
    }
    result = run_analysis_query(records=records, spec=spec)
    return all(
        measure.score_unit == offered[measure.column_key.split(":")[0]]
        for measure in result.measures
    )


def test_the_catalog_labels_a_run_grain_measure_the_way_the_answer_does() -> None:
    records = projected(
        records=[
            record(
                run_id="veyru/1",
                budget=800,
                measurements=[metric("round_success", 0.5)],
                agents=None,
            )
        ]
    )

    assert units_agree(
        records=records,
        spec=query(
            group_by=[],
            measures=[
                mean_of("round_success"),
                MeasureSpec(
                    source=MeasureSource.RUN_COLUMN, key="total_cost_usd", aggregate=Aggregate.MEAN
                ),
            ],
            grain=AnalysisGrain.RUN,
            filters=[],
        ),
    )


def test_the_catalog_claims_no_unit_where_the_answer_claims_none() -> None:
    """The grain the disagreement was at. A metric's unit describes its run-level
    score, and the keyed values are a different quantity, so both sides say nothing
    rather than one of them naming the wrong thing.

    At the run grain the two paths are identical, so a run-grain case pins nothing:
    removing the rule leaves it passing.
    """
    keyed_record = AnalysisRunRecord(
        run_id="veyru/1",
        has_report=True,
        dimensions={"run_id": "veyru/1"},
        agents=[],
        run_columns={"total_cost_usd": 2.0},
        metrics={
            "communication_feature_presence": MetricValues(
                score=3.0, per_round={}, per_agent={}, score_unit="categories over threshold"
            )
        },
        keyed={
            "communication_feature_presence": [
                KeyedObservation(keys={"category_id": "ellipsis"}, value=0.7)
            ]
        },
    )
    spec = query(
        group_by=["key.category_id"],
        measures=[mean_of("communication_feature_presence")],
        grain=AnalysisGrain.KEYED,
        filters=[],
    )

    assert units_agree(records=[keyed_record], spec=spec)
    assert run_analysis_query(records=[keyed_record], spec=spec).measures[0].score_unit == ""


def test_every_run_column_has_a_unit_and_a_reader() -> None:
    """Three parallel structures agreed by hand until they were one."""
    summary = record(run_id="veyru/1", budget=800, measurements=None, agents=None).summary
    values = run_column_values(summary=summary)

    assert set(NUMERIC_RUN_COLUMNS) == set(RUN_COLUMN_UNITS) == set(values)
    assert all(unit != "" for unit in RUN_COLUMN_UNITS.values())


# --- specs that cannot be answered ----------------------------------------------


def test_a_comparing_filter_with_no_values_is_refused() -> None:
    """`in` with no values matches nothing and `not_in` with none matches everything,
    so a half-built filter would silently blank every chart one way and silently do
    nothing the other. The CLI already refused it; the model refuses it for every
    caller."""
    for operator in (FilterOperator.IN, FilterOperator.NOT_IN, FilterOperator.CONTAINS):
        with pytest.raises(ValidationError):
            DimensionFilter(key="model_class", operator=operator, values=[])


def test_an_emptiness_filter_needs_no_values() -> None:
    kept = DimensionFilter(key="model_class", operator=FilterOperator.IS_EMPTY, values=[])

    assert kept.values == []


def test_a_round_query_measuring_only_a_run_column_is_refused() -> None:
    """A round row exists only where a metric reported one, so this matches no rows.
    The catalog offers run columns at every grain, which is what made it reachable."""
    with pytest.raises(ValidationError):
        query(
            group_by=["round_number"],
            measures=[
                MeasureSpec(
                    source=MeasureSource.RUN_COLUMN, key="total_cost_usd", aggregate=Aggregate.MEAN
                )
            ],
            grain=AnalysisGrain.ROUND,
            filters=[],
        )


def test_a_keyed_query_measuring_only_a_run_column_is_refused() -> None:
    with pytest.raises(ValidationError):
        query(
            group_by=["key.category_id"],
            measures=[
                MeasureSpec(
                    source=MeasureSource.RUN_COLUMN, key="total_cost_usd", aggregate=Aggregate.MEAN
                )
            ],
            grain=AnalysisGrain.KEYED,
            filters=[],
        )


def test_an_agent_query_measuring_only_a_run_column_is_answerable() -> None:
    """Agent rows come from the roster, not from what a metric reported, so this one
    has rows to put the run's number on."""
    records = [
        record(run_id="veyru/1", budget=800, measurements=None, agents=None),
    ]

    result = answer(
        records=records,
        spec=query(
            group_by=["agent_id"],
            measures=[
                MeasureSpec(
                    source=MeasureSource.RUN_COLUMN, key="total_cost_usd", aggregate=Aggregate.MEAN
                )
            ],
            grain=AnalysisGrain.AGENT,
            filters=[],
        ),
    )

    assert [row.group_values[0] for row in result.rows] == [
        "field_observer",
        "stabilization_engineer",
    ]
