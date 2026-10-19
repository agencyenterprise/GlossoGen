"""The run-selection flags `export` and `analyze` share, resolved against a runs
directory on disk.
"""

import argparse
from pathlib import Path
from typing import NamedTuple

from glossogen.knob_filter import KnobFilterValueError, knob_filter_problem
from glossogen.models.event import RunStatus
from glossogen.run_export.export_request_models import (
    ExplicitRunSelection,
    FilterRunSelection,
    RunSelection,
)
from glossogen.run_export.run_selection_resolution import resolve_selection
from glossogen.server.runs.discovery import discover_runs
from glossogen.server.runs.models import RunSummary


def add_run_selection_flags(parser: argparse.ArgumentParser, verb: str) -> None:
    """Add the flags :func:`_export_selection_from_args` reads.

    Shared by `export` and `analyze` because that function reads them off
    whichever namespace it is given: a parser missing one raises AttributeError
    on every invocation of its command, not only on the ones that pass it.

    ``verb`` names the command in the ``--run-id`` help, the one line that
    differed between the two copies this replaced.
    """
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        metavar="NAME",
        help="Only these scenarios (repeatable). Omit for every scenario.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="LABEL",
        help="Only runs carrying every one of these labels (repeatable)",
    )
    parser.add_argument(
        "--run-id-contains",
        type=str,
        default=None,
        help="Only runs whose scenario/run_dir_name id contains this substring",
    )
    parser.add_argument(
        "--run-id",
        action="append",
        default=[],
        metavar="ID",
        help=(
            f"{verb} exactly these run ids (repeatable, e.g. veyru/1777638061). "
            "Cannot be combined with the filter flags."
        ),
    )
    parser.add_argument(
        "--knob",
        action="append",
        default=[],
        metavar="CONDITION",
        help=(
            "Only runs whose recorded scenario_config satisfies this condition, "
            "written <knob><operator><value> with the operator one of "
            "= != >= <= > <. Quote it, or the shell reads > and < as redirection: "
            "--knob 'round_time_budget_seconds>=200' --knob postmortem_enabled=true. "
            "Repeatable; every condition must hold."
        ),
    )
    parser.add_argument(
        "--contains-agent-id",
        type=str,
        default=None,
        metavar="AGENT_ID",
        help="Only runs that registered this agent (e.g. field_observer)",
    )
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        choices=[status.value for status in RunStatus],
        help="Only runs in this state (e.g. scenario_complete to skip crashed runs)",
    )


def _export_selection_from_args(args: argparse.Namespace) -> RunSelection:
    """Build the selection the flags describe, refusing a mix of the two forms."""
    filter_flags_used = bool(
        args.scenario
        or args.label
        or args.run_id_contains
        or args.status is not None
        or args.contains_agent_id is not None
        or args.knob
    )
    if args.run_id and filter_flags_used:
        raise SystemExit(
            "Pass either --run-id or the filter flags (--scenario / --label / "
            "--run-id-contains / --status / --contains-agent-id / --knob), not both."
        )
    if args.run_id:
        return ExplicitRunSelection(kind="explicit", run_ids=list(args.run_id))
    status = None
    if args.status is not None:
        status = RunStatus(args.status)
    # Checked before building, so the model's own validator never fires here. It
    # would raise, and reporting a mistyped flag through an exception means either
    # a pydantic traceback on stderr or a logging rule broken to avoid one.
    problem = knob_filter_problem(raw_filters=list(args.knob))
    if problem is not None:
        raise SystemExit(problem)
    return FilterRunSelection(
        kind="filters",
        scenario=list(args.scenario),
        labels=list(args.label),
        run_id_contains=args.run_id_contains,
        status=status,
        contains_agent_id=args.contains_agent_id,
        knob=list(args.knob),
    )


class LocalSelection(NamedTuple):
    """The selection the flags describe, and the runs it resolves to on disk."""

    selection: RunSelection
    summaries: list[RunSummary]


async def resolved_local_runs(args: argparse.Namespace) -> LocalSelection:
    """Resolve the selection the flags describe against a runs directory on disk.

    Shared by the export and the analysis commands: both read the runs directory
    directly, so neither needs a server or a database, and both refuse the same
    three ways (a named run that is not there, a selection matching nothing, and one
    over the run ceiling).
    """
    selection = _export_selection_from_args(args=args)
    runs_dir = Path(args.runs_dir).resolve()
    if not runs_dir.is_dir():
        raise SystemExit(f"No runs directory at {runs_dir}")
    summaries = await discover_runs(runs_dir=runs_dir)
    try:
        resolved = resolve_selection(candidates=summaries, selection=selection)
    except KnobFilterValueError as exc:
        raise SystemExit(str(exc)) from exc

    if resolved.missing_run_ids:
        raise SystemExit(f"No run found for: {', '.join(sorted(resolved.missing_run_ids))}")
    if not resolved.summaries:
        raise SystemExit("That selection matches no runs.")
    if len(resolved.summaries) > args.max_runs:
        raise SystemExit(
            f"That selection is {len(resolved.summaries)} runs, over the --max-runs "
            f"limit of {args.max_runs}."
        )
    return LocalSelection(selection=selection, summaries=resolved.summaries)
