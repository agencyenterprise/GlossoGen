"""The ``analyze`` subcommand: group and aggregate many runs' metrics."""

import argparse

from pydantic import ValidationError

from glossogen.cli.local_run_selection import add_run_selection_flags, resolved_local_runs
from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.run_analysis.analysis_field_catalog import build_field_catalog
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_key_validation import UnknownAnalysisKeysError
from glossogen.run_analysis.analysis_limits import MAX_RESULT_ROWS as MAX_ANALYSIS_RESULT_ROWS
from glossogen.run_analysis.analysis_query_engine import run_analysis_query
from glossogen.run_analysis.analysis_query_models import AnalysisQuerySpec, ResultSort
from glossogen.run_analysis.analysis_run_record import load_analysis_records
from glossogen.run_analysis.analysis_spec_parsing import (
    AnalysisSpecError,
    parse_filter,
    parse_measure,
)
from glossogen.run_analysis.analysis_text_table import render_field_catalog, render_text_table
from glossogen.run_export.export_limits import MAX_EXPORT_RUN_COUNT


def add_analyze_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``analyze`` subcommand and its flags."""
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Group and aggregate many runs' metrics into one table",
    )
    analyze_parser.add_argument(
        "--runs-dir",
        type=str,
        default="./runs",
        help="Directory holding the run data (default: ./runs)",
    )
    add_run_selection_flags(parser=analyze_parser, verb="Analyze")
    analyze_parser.add_argument(
        "--grain",
        type=str,
        default=AnalysisGrain.RUN.value,
        choices=[grain.value for grain in AnalysisGrain],
        help="What one observation is (default: run)",
    )
    analyze_parser.add_argument(
        "--group-by",
        action="append",
        default=[],
        metavar="DIMENSION",
        help=(
            "Group on this dimension (repeatable, at most two: the x axis then the "
            "series). Omit to aggregate the whole selection into one row."
        ),
    )
    analyze_parser.add_argument(
        "--measure",
        action="append",
        default=[],
        metavar="SPEC",
        help=(
            "What to aggregate, as key:aggregate (a metric) or source:key:aggregate "
            "(e.g. run_column:total_cost_usd:sum). Repeatable."
        ),
    )
    analyze_parser.add_argument(
        "--filter",
        action="append",
        default=[],
        dest="dimension_filter",
        metavar="SPEC",
        help=(
            "Narrow the observations, as key:operator[:values] "
            "(e.g. knob.round_time_budget_seconds:gte:1000). Repeatable."
        ),
    )
    analyze_parser.add_argument(
        "--sort",
        type=str,
        default=ResultSort.GROUP.value,
        choices=[sort.value for sort in ResultSort],
        help="Row order (default: by the group values, numerically where they are numbers)",
    )
    analyze_parser.add_argument(
        "--sort-measure",
        type=int,
        default=0,
        metavar="INDEX",
        help="Which --measure a measure sort orders by, counting from 0 (default: 0)",
    )
    analyze_parser.add_argument(
        "--limit",
        type=int,
        default=MAX_ANALYSIS_RESULT_ROWS,
        help=f"Keep at most this many groups (default: {MAX_ANALYSIS_RESULT_ROWS})",
    )
    analyze_parser.add_argument(
        "--list-fields",
        action="store_true",
        help="Print the dimensions and measures this selection carries, and stop",
    )
    analyze_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Print the result as JSON instead of an aligned table",
    )
    analyze_parser.add_argument(
        "--max-runs",
        type=int,
        default=MAX_EXPORT_RUN_COUNT,
        help=f"Refuse a selection larger than this (default: {MAX_EXPORT_RUN_COUNT})",
    )


def _analysis_spec_from_args(args: argparse.Namespace) -> AnalysisQuerySpec:
    """Build the query spec the flags describe, naming what could not be read."""
    if not args.measure:
        raise SystemExit(
            "Pass at least one --measure (e.g. --measure round_success:mean). "
            "Run with --list-fields to see what this selection carries."
        )
    try:
        measures = [parse_measure(text=text) for text in args.measure]
        filters = [parse_filter(text=text) for text in args.dimension_filter]
    except (AnalysisSpecError, ValidationError) as exc:
        raise SystemExit(str(exc)) from exc

    try:
        return AnalysisQuerySpec(
            grain=AnalysisGrain(args.grain),
            filters=filters,
            group_by=list(args.group_by),
            measures=measures,
            sort=ResultSort(args.sort),
            sort_measure_index=args.sort_measure,
            limit=args.limit,
        )
    except ValidationError as exc:
        raise SystemExit(str(exc)) from exc


async def handle_analyze(args: argparse.Namespace) -> None:
    """Group and aggregate the selected runs into one table.

    Reads the runs directory directly, so it needs no server and no database, and runs
    the same engine the web UI's charts do.
    """
    summaries = (await resolved_local_runs(args=args)).summaries
    grain = AnalysisGrain(args.grain)
    records = await load_analysis_records(
        runs=summaries, read_sidecars=grain is AnalysisGrain.KEYED
    )

    if args.list_fields:
        catalog = build_field_catalog(records=records, grain=grain)
        if args.as_json:
            print(catalog.model_dump_json(indent=2))
            return
        print(render_field_catalog(catalog=catalog))
        return

    try:
        result = run_analysis_query(records=records, spec=_analysis_spec_from_args(args=args))
    except UnknownAnalysisKeysError as exc:
        raise SystemExit(str(exc)) from exc
    if args.as_json:
        print(result.model_dump_json(indent=2))
        return
    print(render_text_table(result=result))
