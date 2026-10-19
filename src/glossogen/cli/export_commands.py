"""The ``export``, ``export-thread`` and ``export-atif`` subcommands."""

import argparse
import asyncio
import logging
from pathlib import Path

from glossogen.atif_export.atif_run_context import load_atif_run_context
from glossogen.atif_export.atif_trajectory_builder import (
    build_agent_trajectories,
    build_run_trajectories,
    serialize_trajectory,
    trajectory_file_name,
)
from glossogen.cli.local_run_selection import add_run_selection_flags, resolved_local_runs
from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.run_export.csv_export_archive import (
    build_export_frames,
    build_legend_frame,
    write_frames_to_directory,
)
from glossogen.run_export.export_column_catalog import build_export_preview
from glossogen.run_export.export_limits import MAX_EXPORT_RUN_COUNT, ExportTooLargeError
from glossogen.run_export.export_request_models import (
    CsvExportRequest,
    ExportFrame,
)
from glossogen.run_export.export_run_record import load_export_run_records
from glossogen.run_export.runs_zip_archive import write_runs_zip
from glossogen.thread_export.export_agent_thread import (
    ThreadExportFormat,
    export_agent_thread_from_run_dir,
)

logger = logging.getLogger(__name__)


def add_export_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``export`` subcommand and its flags."""
    export_parser = subparsers.add_parser(
        "export",
        help="Export many runs as CSV tables or as a zip of their run folders",
    )
    export_parser.add_argument(
        "--runs-dir",
        type=str,
        default="./runs",
        help="Directory holding the run data (default: ./runs)",
    )
    export_parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Directory to write the export into (created if absent)",
    )
    add_run_selection_flags(parser=export_parser, verb="Export")
    export_parser.add_argument(
        "--frames",
        type=str,
        default="run_level,round_level,agent_level",
        help=(
            "Comma-separated tables to emit: run_level, round_level, agent_level, "
            "message_level, round_context (default: the first three; the last two "
            "read every run's event log)"
        ),
    )
    export_parser.add_argument(
        "--include-metric-summaries",
        action="store_true",
        help=(
            "Add each metric's unit and one-line summary at run level, and its "
            "per-observation note on the round and agent tables"
        ),
    )
    export_parser.add_argument(
        "--no-repeat-run-columns",
        dest="repeat_run_columns",
        action="store_false",
        help="Keep the long tables narrow, joining back on run_id instead",
    )
    export_parser.add_argument(
        "--raw",
        action="store_true",
        help="Also write a zip of the selected runs' folders",
    )
    export_parser.add_argument(
        "--include-logs",
        action="store_true",
        help="Keep debug and stdout logs in the raw zip (they are dropped by default)",
    )
    export_parser.add_argument(
        "--include-atif",
        action="store_true",
        help="Add each agent's ATIF trajectory under atif/ in every run of the raw zip",
    )
    export_parser.add_argument(
        "--max-runs",
        type=int,
        default=MAX_EXPORT_RUN_COUNT,
        help=f"Refuse a selection larger than this (default: {MAX_EXPORT_RUN_COUNT})",
    )


def add_export_thread_parser(subparsers: SubcommandParsers, scenario_names: list[str]) -> None:
    """Add the ``export-thread`` subcommand and its flags."""
    export_thread_parser = subparsers.add_parser(
        "export-thread",
        help="Export one agent's reconstructed thread as a provider-native API request body",
    )
    export_thread_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario the run belongs to",
    )
    export_thread_parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Path to the run directory (e.g. runs/veyru/1742234567)",
    )
    export_thread_parser.add_argument(
        "--agent-id",
        type=str,
        required=True,
        help="Agent whose thread to export (e.g. field_observer)",
    )
    export_thread_parser.add_argument(
        "--round",
        dest="round",
        type=int,
        default=None,
        help=(
            "Exclusive round cutoff: drops every tool call whose round_number >= R, "
            "so the exported history covers rounds 1..R-1. Pass --round=R+1 to capture "
            "the agent's state at the END of round R. Omit for the full end-of-run thread."
        ),
    )
    export_thread_parser.add_argument(
        "--format",
        dest="format",
        type=str,
        choices=["anthropic", "openai"],
        default=None,
        help=(
            "Target provider format for the request body. Defaults to the format "
            "matching the agent's own provider (anthropic->anthropic, "
            "openai/self-hosted->openai)."
        ),
    )
    export_thread_parser.add_argument(
        "--include-thinking",
        dest="include_thinking",
        action="store_true",
        help=(
            "Keep reasoning/thinking parts as text blocks. Dropped by default because "
            "replaying provider reasoning blocks in a raw request requires signatures."
        ),
    )
    export_thread_parser.add_argument(
        "--flatten-tools",
        dest="flatten_tools",
        action="store_true",
        help=(
            "Render tool calls and results as plain text instead of native tool_use/"
            "tool_result blocks, producing a body that needs no tool configuration."
        ),
    )
    export_thread_parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Write the export JSON to this path. Omit to print it to stdout.",
    )


def add_export_atif_parser(subparsers: SubcommandParsers, scenario_names: list[str]) -> None:
    """Add the ``export-atif`` subcommand and its flags."""
    export_atif_parser = subparsers.add_parser(
        "export-atif",
        help="Export a run's agents as ATIF trajectories, one JSON file per agent",
    )
    export_atif_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario the run belongs to",
    )
    export_atif_parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Path to the run directory (e.g. runs/veyru/1742234567)",
    )
    export_atif_parser.add_argument(
        "--agent-id",
        type=str,
        default=None,
        help="Export only this agent. Omit to export every agent in the run.",
    )
    export_atif_parser.add_argument(
        "--round",
        dest="round",
        type=int,
        default=None,
        help=(
            "Exclusive round cutoff, as for export-thread: --round=R keeps rounds 1..R-1. "
            "Omit for the whole run."
        ),
    )
    export_atif_parser.add_argument(
        "--out-dir",
        type=str,
        required=True,
        help="Directory to write <agent_id>.json files into (created if missing)",
    )


def _requested_frames(raw: str) -> list[ExportFrame]:
    """Parse the --frames flag, naming any value that is not a table."""
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise SystemExit("--frames needs at least one table name.")
    valid = {frame.value for frame in ExportFrame}
    unknown = [name for name in names if name not in valid]
    if unknown:
        raise SystemExit(
            f"Unknown table(s): {', '.join(unknown)}. Choose from {', '.join(sorted(valid))}."
        )
    return [ExportFrame(name) for name in names]


async def handle_export(args: argparse.Namespace) -> None:
    """Export many runs as CSV tables, and optionally as a zip of their folders.

    Reads the runs directory directly, so it needs no server and no database. It
    covers runs that were never evaluated and runs still in progress; their metric
    cells are empty rather than zero.
    """
    frames_requested = _requested_frames(raw=args.frames)
    if args.include_logs and not args.raw:
        raise SystemExit("--include-logs only affects the raw zip; pass --raw as well.")
    if args.include_atif and not args.raw:
        raise SystemExit("--include-atif only affects the raw zip; pass --raw as well.")

    selection, summaries = await resolved_local_runs(args=args)
    records = await load_export_run_records(runs=summaries)
    preview = build_export_preview(
        records=records,
        missing_run_ids=[],
        raw_bytes_estimate=None,
    )
    logger.info(
        "Exporting %d runs across %s: %d columns, %d metrics",
        preview.run_count,
        ", ".join(preview.scenario_names),
        len(preview.columns),
        len(preview.metrics),
    )
    if preview.runs_without_report:
        logger.info(
            "%d of them have no evaluation report, so their metric cells are empty",
            len(preview.runs_without_report),
        )

    request = CsvExportRequest(
        selection=selection,
        frames=frames_requested,
        columns=list(dict.fromkeys(column.key for column in preview.columns)),
        metrics=[metric.metric_name for metric in preview.metrics],
        repeat_run_columns=args.repeat_run_columns,
        include_metric_summaries=args.include_metric_summaries,
    )
    out_dir = Path(args.out).resolve()
    written = write_frames_to_directory(
        frames=build_export_frames(records=records, request=request),
        legend=build_legend_frame(records=records, request=request),
        out_dir=out_dir,
    )
    for path in written:
        print(path)

    if args.raw:
        zip_path = out_dir / "runs.zip"
        try:
            with zip_path.open("wb") as handle:
                # In a worker thread: the ATIF writer runs its own event loop per run.
                tally = await asyncio.to_thread(
                    write_runs_zip,
                    runs=summaries,
                    include_logs=args.include_logs,
                    include_atif=args.include_atif,
                    destination=handle,
                )
        except ExportTooLargeError as exc:
            zip_path.unlink(missing_ok=True)
            raise SystemExit(str(exc)) from exc
        logger.info("Raw zip: %d runs, %d files", tally.run_count, tally.file_count)
        print(zip_path)


async def handle_export_atif(args: argparse.Namespace) -> None:
    """Write one ATIF trajectory file per agent to ``--out-dir``.

    A seat swapped to another model mid-run gets one file per generation.
    """
    context = await load_atif_run_context(
        run_dir=Path(args.run_dir).resolve(),
        scenario_name=args.scenario_name,
    )
    if args.agent_id is None:
        trajectories = build_run_trajectories(context=context, cutoff_round=args.round)
    else:
        trajectories = build_agent_trajectories(
            context=context,
            agent_id=args.agent_id,
            cutoff_round=args.round,
        )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for trajectory in trajectories:
        out_path = out_dir / trajectory_file_name(trajectory=trajectory)
        out_path.write_text(serialize_trajectory(trajectory=trajectory) + "\n")
        logger.info(
            "Wrote ATIF trajectory %s (%d steps) -> %s",
            trajectory.trajectory_id,
            trajectory.final_metrics.total_steps,
            out_path,
        )


async def handle_export_thread(args: argparse.Namespace) -> None:
    """Export one agent's reconstructed thread as a provider-native request body.

    Writes the ``ThreadExport`` JSON to ``--out`` (or stdout). The consumer
    appends their own trailing user message (and ``max_tokens`` for Anthropic)
    to ``request`` and POSTs it straight to the provider.
    """
    if args.format == "anthropic":
        output_format: ThreadExportFormat | None = "anthropic_messages"
    elif args.format == "openai":
        output_format = "openai_chat"
    else:
        output_format = None

    export = await export_agent_thread_from_run_dir(
        run_dir=Path(args.run_dir).resolve(),
        scenario_name=args.scenario_name,
        agent_id=args.agent_id,
        cutoff_round=args.round,
        output_format=output_format,
        include_thinking=args.include_thinking,
        flatten_tools=args.flatten_tools,
    )
    payload = export.model_dump_json(indent=2)
    if args.out is None:
        print(payload)
        return
    out_path = Path(args.out)
    out_path.write_text(payload + "\n")
    logger.info(
        "Wrote thread export for agent %s (%s, %d messages) -> %s",
        export.meta.agent_id,
        export.meta.format,
        export.meta.num_messages,
        out_path,
    )
