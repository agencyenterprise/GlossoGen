"""Cell rendering, export ceilings, filter matching, and the tolerant report load.

The cell tests are about what survives a round trip into a spreadsheet. Model
output reaches these cells, and it carries control characters, newlines, and text
that a spreadsheet reads as a formula. Each of those loses data in a different
way, and only the formula case loses it silently.
"""

import io
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest

from glossogen.evaluation.reports.evaluation_report import load_report, load_report_tolerant
from glossogen.models.event import RunStatus
from glossogen.run_export import export_limits
from glossogen.run_export.agent_identity_columns import agent_identity_cells, agent_model_by_id
from glossogen.run_export.archive_member_filter import should_include_in_archive
from glossogen.run_export.csv_cell_text import (
    guard_spreadsheet_formula,
    render_cell,
    render_scalar,
    render_string_list,
    sanitize_cell_text,
)
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.csv_frame_writer import write_frame
from glossogen.run_export.export_limits import ExportTooLargeError, check_raw_bytes, check_run_count
from glossogen.run_export.export_request_models import ExplicitRunSelection, FilterRunSelection
from glossogen.run_export.knob_flattening import knob_cells_by_key
from glossogen.run_export.lineage_columns import lineage_cells
from glossogen.run_export.run_metadata_columns import run_metadata_cells
from glossogen.run_export.run_selection_resolution import resolve_selection
from glossogen.server.runs.models import (
    AgentModelSummary,
    ForkAtRoundSource,
    ForkSource,
    RunSummary,
)


def make_summary(
    run_id: str,
    scenario_name: str,
    labels: list[str],
    status: RunStatus,
) -> RunSummary:
    """Build a run summary carrying the fields selection and lineage read."""
    return RunSummary(
        run_id=run_id,
        scenario_name=scenario_name,
        scenario_description="",
        scenario_config={},
        timestamp=datetime(2026, 5, 4, tzinfo=UTC),
        total_messages=0,
        total_cost_usd=0.0,
        duration_seconds=0.0,
        status=status,
        has_evaluation=False,
        evaluation_in_progress=False,
        run_dir=f"/runs/{run_id}",
        fork_source=None,
        replace_agent_source=None,
        cross_run_replace_agent_source=None,
        fork_at_round_source=None,
        models=[],
        provider="anthropic",
        agent_models=[],
        labels=labels,
        has_note=False,
        current_round=0,
        evaluation_content_hash=None,
    )


# --- cells a spreadsheet would misread ------------------------------------------


def test_a_cell_beginning_with_at_is_guarded() -> None:
    """A real judge note begins ``@ notation established``, which Excel shows as #NAME?."""
    guarded = render_cell(text="@ notation established: '@B' means 'near/at face B'")
    assert guarded.startswith("'@ notation established")


def test_a_cell_beginning_with_equals_or_plus_is_guarded() -> None:
    """The same reading applies to the other formula leads."""
    assert render_cell(text="=SUM(A1:A9)").startswith("'=")
    assert render_cell(text="+1+1").startswith("'+")


def test_a_negative_number_is_left_alone() -> None:
    """Guarding a leading minus would put an apostrophe on every negative score."""
    assert render_scalar(value=-1.5) == "-1.5"
    assert render_cell(text="-1.5") == "-1.5"


def test_an_equals_sign_inside_a_cell_is_left_alone() -> None:
    """Only the first character decides how a spreadsheet reads the cell."""
    assert render_cell(text="20 messages, std=0.198") == "20 messages, std=0.198"


def test_the_guard_applies_once_per_cell_not_per_value() -> None:
    """A joined multi-value cell is one cell, so at most one apostrophe."""
    joined = render_string_list(values=["@first", "@second"])
    assert joined.startswith("'@first")
    assert joined.count("'") == 1


def test_control_characters_are_stripped() -> None:
    """A spreadsheet refuses a file containing them."""
    assert sanitize_cell_text(text="a\x00b\x07c\x1fd") == "abcd"


def test_a_tab_survives() -> None:
    """It is a legal cell character and the writer quotes it correctly."""
    assert sanitize_cell_text(text="a\tb") == "a\tb"


def test_newlines_become_spaces() -> None:
    """Legal inside a quoted field, and it breaks every line-oriented reader."""
    assert sanitize_cell_text(text="first\r\nsecond\rthird\nfourth") == "first second third fourth"


def test_a_container_renders_as_sorted_json() -> None:
    """A cell that cannot be a column stays machine-readable across processes."""
    assert render_scalar(value={"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert render_scalar(value=frozenset({3, 1, 2})) == "[1,2,3]"


def test_a_float_keeps_its_full_precision() -> None:
    """Rounding here would discard precision a metric computed."""
    assert render_scalar(value=2.434831780035891) == "2.434831780035891"


def test_the_guard_is_a_no_op_on_ordinary_text() -> None:
    """It only ever prepends, and only for the leads that matter."""
    assert guard_spreadsheet_formula(text="veyru/1777638061") == "veyru/1777638061"


# --- the writer -----------------------------------------------------------------


def test_the_writer_emits_no_byte_order_mark_and_unix_endings() -> None:
    """A BOM glues a stray character to the first column name for most readers."""
    frame = CsvFrame(name="t", header=["a", "b"], rows=iter([["1", "2"]]))
    buffer = io.BytesIO()
    write_frame(frame=frame, destination=buffer, check=None)
    raw = buffer.getvalue()

    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    assert raw == b"a,b\n1,2\n"


def test_the_writer_quotes_a_cell_containing_a_comma() -> None:
    """Multi-value cells use a semicolon, but a knob string can still hold a comma."""
    frame = CsvFrame(name="t", header=["a"], rows=iter([["x,y"]]))
    buffer = io.BytesIO()
    write_frame(frame=frame, destination=buffer, check=None)
    assert buffer.getvalue() == b'a\n"x,y"\n'


def test_the_writer_reports_its_row_and_byte_counts() -> None:
    """The byte count is what the export ceiling is enforced against."""
    frame = CsvFrame(name="t", header=["a"], rows=iter([["1"], ["2"], ["3"]]))
    buffer = io.BytesIO()
    row_count, written = write_frame(frame=frame, destination=buffer, check=None)
    assert row_count == 3
    assert written == len(buffer.getvalue())
    assert not buffer.closed


# --- ceilings -------------------------------------------------------------------


def test_a_selection_at_the_run_ceiling_is_allowed() -> None:
    """The limit is inclusive, so the number quoted to the user is reachable."""
    check_run_count(run_count=export_limits.MAX_EXPORT_RUN_COUNT)


def test_a_selection_over_the_run_ceiling_names_both_numbers() -> None:
    """The message has to say what was asked for and what is allowed."""
    with pytest.raises(ExportTooLargeError) as raised:
        check_run_count(run_count=export_limits.MAX_EXPORT_RUN_COUNT + 1)
    message = str(raised.value)
    assert str(export_limits.MAX_EXPORT_RUN_COUNT + 1) in message
    assert str(export_limits.MAX_EXPORT_RUN_COUNT) in message


def test_a_selection_over_the_byte_ceiling_is_refused() -> None:
    """Bounded by what a download can hand over, not by what a disk can hold."""
    with pytest.raises(ExportTooLargeError):
        check_raw_bytes(total_bytes=export_limits.MAX_RAW_EXPORT_BYTES + 1)


# --- the archive member filter --------------------------------------------------


def test_live_state_files_are_excluded_whatever_the_log_setting(tmp_path: Path) -> None:
    """They describe work in flight, so an imported run carrying them reads as busy."""
    for name in ("stream.json", "eval_in_progress.json"):
        path = tmp_path / name
        path.write_text("{}")
        assert not should_include_in_archive(path=path, run_dir=tmp_path, include_logs=False)
        assert not should_include_in_archive(path=path, run_dir=tmp_path, include_logs=True)


def test_a_file_inside_a_git_directory_is_excluded(tmp_path: Path) -> None:
    """Runs predating the JSONL rewrite carry one, and it is not run data."""
    nested = tmp_path / ".git" / "refs"
    nested.mkdir(parents=True)
    path = nested / "HEAD"
    path.write_text("x")
    assert not should_include_in_archive(path=path, run_dir=tmp_path, include_logs=True)


def test_the_log_suffixes_flip_with_the_setting(tmp_path: Path) -> None:
    """Excluded by size, not by meaning, so an export can ask for them back."""
    for name in ("veyru_debug.jsonl", "veyru_stdout.log", "x_start.log", "eval_stdout.log"):
        path = tmp_path / name
        path.write_text("x")
        assert not should_include_in_archive(path=path, run_dir=tmp_path, include_logs=False)
        assert should_include_in_archive(path=path, run_dir=tmp_path, include_logs=True)


# --- lineage --------------------------------------------------------------------


def test_a_run_derived_from_nothing_reports_an_empty_derivation_type() -> None:
    """Most runs are roots, and the column has to be able to say so."""
    cells = lineage_cells(
        summary=make_summary(
            run_id="veyru/1",
            scenario_name="veyru",
            labels=[],
            status=RunStatus.SCENARIO_COMPLETE,
        )
    )
    assert cells["derivation_type"] == ""
    assert not [key for key in cells if key.startswith("lineage.")]


def test_a_forked_run_flattens_its_provenance() -> None:
    """Walking a chain back to its root has to be possible from the CSV alone."""
    summary = make_summary(
        run_id="veyru/2",
        scenario_name="veyru",
        labels=[],
        status=RunStatus.SCENARIO_COMPLETE,
    )
    summary.fork_source = ForkSource(
        source_run_id="veyru/1",
        target_message_id="m-9",
        forked_at=datetime(2026, 5, 4, tzinfo=UTC),
    )
    cells = lineage_cells(summary=summary)

    assert cells["derivation_type"] == "fork"
    assert cells["lineage.source_run_id"] == "veyru/1"
    assert cells["lineage.target_message_id"] == "m-9"


def test_a_forked_at_round_run_is_named_as_such() -> None:
    """Four derivation kinds share one column family, so the type names which it is."""
    summary = make_summary(
        run_id="veyru/3",
        scenario_name="veyru",
        labels=[],
        status=RunStatus.SCENARIO_COMPLETE,
    )
    summary.fork_at_round_source = ForkAtRoundSource(
        source_run_id="veyru/1",
        after_round=15,
        rounds_after=11,
        target_event_id="e-4",
        forked_at=datetime(2026, 5, 4, tzinfo=UTC),
    )
    cells = lineage_cells(summary=summary)

    assert cells["derivation_type"] == "fork_at_round"
    assert cells["lineage.after_round"] == "15"


# --- the filter branch of selection ---------------------------------------------


def filter_selection(
    scenario: list[str],
    labels: list[str],
    run_id_contains: str | None,
    status: RunStatus | None,
) -> FilterRunSelection:
    """Build a filter selection with every field stated."""
    return FilterRunSelection(
        kind="filters",
        scenario=scenario,
        labels=labels,
        run_id_contains=run_id_contains,
        knob=[],
        status=status,
        contains_agent_id=None,
    )


CANDIDATES = [
    make_summary(
        run_id="veyru/1",
        scenario_name="veyru",
        labels=["baseline_oss", "budget=800"],
        status=RunStatus.SCENARIO_COMPLETE,
    ),
    make_summary(
        run_id="veyru/2",
        scenario_name="veyru",
        labels=["baseline_oss"],
        status=RunStatus.IN_PROGRESS,
    ),
    make_summary(
        run_id="spot_the_difference/3",
        scenario_name="spot_the_difference",
        labels=[],
        status=RunStatus.SCENARIO_COMPLETE,
    ),
]


def matched(selection: FilterRunSelection) -> list[str]:
    """Return the run ids a filter selection resolves to."""
    return [
        s.run_id for s in resolve_selection(candidates=CANDIDATES, selection=selection).summaries
    ]


def test_no_filters_matches_every_run() -> None:
    """Every filter empty means the whole group, which the wire has to allow."""
    assert matched(filter_selection([], [], None, None)) == [
        "spot_the_difference/3",
        "veyru/1",
        "veyru/2",
    ]


def test_scenarios_are_or_matched() -> None:
    """Naming two scenarios means either, which is how the runs list reads them."""
    assert matched(filter_selection(["veyru"], [], None, None)) == ["veyru/1", "veyru/2"]


def test_labels_are_and_matched() -> None:
    """Two labels mean both, so a pair of them addresses one cell of a sweep."""
    assert matched(filter_selection([], ["baseline_oss"], None, None)) == ["veyru/1", "veyru/2"]
    assert matched(filter_selection([], ["baseline_oss", "budget=800"], None, None)) == ["veyru/1"]


def test_the_id_substring_is_case_insensitive() -> None:
    """It is a search box, so the case someone typed cannot matter."""
    assert matched(filter_selection([], [], "SPOT", None)) == ["spot_the_difference/3"]


def test_status_narrows_to_one_state() -> None:
    """Exporting only what finished is the reason this filter exists."""
    assert matched(filter_selection([], [], None, RunStatus.IN_PROGRESS)) == ["veyru/2"]


def test_filters_compose_as_an_intersection() -> None:
    """Adding a filter narrows; it never grows the result."""
    assert matched(filter_selection(["veyru"], ["baseline_oss"], "1", None)) == ["veyru/1"]


def test_an_explicit_selection_ignores_runs_it_did_not_name() -> None:
    """The other form of selection, resolved against the same candidates."""
    resolved = resolve_selection(
        candidates=CANDIDATES,
        selection=ExplicitRunSelection(kind="explicit", run_ids=["veyru/2"]),
    )
    assert [s.run_id for s in resolved.summaries] == ["veyru/2"]


# --- the tolerant report load ---------------------------------------------------


REPORT_WITHOUT_COST: dict[str, object] = {
    "simulation_id": "veyru/1",
    "scenario_name": "veyru",
    "measurements": [],
}


async def test_a_report_predating_cost_tracking_still_loads(tmp_path: Path) -> None:
    """One old report must not fail a sweep across hundreds of runs."""
    path = tmp_path / "veyru_report.json"
    path.write_bytes(orjson.dumps(REPORT_WITHOUT_COST))

    report = await load_report_tolerant(report_path=path)

    assert report is not None
    assert report.evaluation_cost.estimated_cost_usd == 0.0
    assert report.evaluation_cost.model == "unknown"


async def test_the_strict_loader_still_rejects_it(tmp_path: Path) -> None:
    """The writer path legitimately demands a real cost before merging into one."""
    path = tmp_path / "veyru_report.json"
    path.write_bytes(orjson.dumps(REPORT_WITHOUT_COST))

    with pytest.raises(Exception):
        await load_report(report_path=path)


async def test_a_missing_report_is_absent_rather_than_an_error(tmp_path: Path) -> None:
    """Most runs in a wide selection were never evaluated."""
    assert await load_report_tolerant(report_path=tmp_path / "nope.json") is None


# --- the per-agent roster -------------------------------------------------------


def agent(agent_id: str, role_name: str, model: str) -> AgentModelSummary:
    """One registered agent."""
    return AgentModelSummary(
        agent_id=agent_id, role_name=role_name, model=model, provider="anthropic"
    )


def test_each_agent_gets_a_model_provider_and_role_column() -> None:
    """This is the generic form of the per-role model columns exporters spell out."""
    cells = agent_identity_cells(
        agent_models=[agent(agent_id="field_observer", role_name="Field Observer", model="opus")]
    )
    assert cells["agent_model.field_observer"] == "opus"
    assert cells["agent_provider.field_observer"] == "anthropic"
    assert cells["agent_role.field_observer"] == "Field Observer"


def test_a_second_agent_adds_its_own_columns() -> None:
    """Keying by agent id needs no table mapping ids to roles."""
    cells = agent_identity_cells(
        agent_models=[
            agent(agent_id="field_observer", role_name="Field Observer", model="opus"),
            agent(agent_id="stabilization_engineer", role_name="Engineer", model="sonnet"),
        ]
    )
    assert cells["agent_model.field_observer"] == "opus"
    assert cells["agent_model.stabilization_engineer"] == "sonnet"


def test_an_agent_swapped_mid_run_keeps_its_first_registration() -> None:
    """A swap registers the same id twice; one row has one cell for it.

    The first is kept so the column describes what the run started with, and the
    swap itself is recorded in the lineage columns and in the event log rather than
    by overwriting this.
    """
    cells = agent_identity_cells(
        agent_models=[
            agent(agent_id="field_observer", role_name="Field Observer", model="opus"),
            agent(agent_id="field_observer", role_name="Field Observer", model="sonnet"),
        ]
    )
    assert cells["agent_model.field_observer"] == "opus"


def test_a_run_with_no_agents_contributes_no_columns() -> None:
    """A run that failed before registering anything still has to render a row."""
    assert agent_identity_cells(agent_models=[]) == {}


def test_the_roster_index_keeps_the_first_of_a_repeated_id() -> None:
    """The long per-agent table resolves model and role through this."""
    indexed = agent_model_by_id(
        agent_models=[
            agent(agent_id="field_observer", role_name="Field Observer", model="opus"),
            agent(agent_id="field_observer", role_name="Field Observer", model="sonnet"),
        ]
    )
    assert list(indexed) == ["field_observer"]
    assert indexed["field_observer"].model == "opus"


def test_every_text_cell_goes_through_the_same_guard() -> None:
    """A model id or a role name can begin with @ as readily as a judge note can.

    These went through raw for a while, which meant one cell in a row was guarded
    and its neighbour was not, with nothing saying why.
    """
    cells = agent_identity_cells(
        agent_models=[agent(agent_id="obs", role_name="=SUM(A1)", model="@weird/model")]
    )
    assert cells["agent_role.obs"].startswith("'=")
    assert cells["agent_model.obs"].startswith("'@")


def test_run_metadata_cells_are_guarded_too() -> None:
    """The identity columns are text a scenario or a path can shape."""
    summary = make_summary(
        run_id="@odd/1",
        scenario_name="@odd",
        labels=[],
        status=RunStatus.SCENARIO_COMPLETE,
    )
    cells = run_metadata_cells(summary=summary)
    assert cells["run_id"].startswith("'@")
    assert cells["scenario_name"].startswith("'@")
    assert cells["run_dir_name"] == "1"


def test_an_empty_mapping_knob_still_gets_a_column() -> None:
    """Otherwise "recorded as empty" and "never recorded" render the same."""
    cells = knob_cells_by_key(scenario_config={"model_overrides": {}})
    assert cells["knob.model_overrides"] == "{}"


def test_a_populated_mapping_knob_explodes_instead() -> None:
    """The empty case is the exception, not a change to the rule."""
    cells = knob_cells_by_key(scenario_config={"model_overrides": {"obs": {"model": "opus"}}})
    assert "knob.model_overrides" not in cells
    assert cells["knob.model_overrides.obs.model"] == "opus"
