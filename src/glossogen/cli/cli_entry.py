"""The ``glossogen`` entry point: builds the parser and dispatches to a subcommand."""

import argparse
import asyncio
import logging
import os
from collections.abc import Coroutine
from typing import Any, Protocol

from glossogen.cli.analyze_command import add_analyze_parser, handle_analyze
from glossogen.cli.derivation_commands import (
    add_cross_run_replace_agent_parser,
    add_fork_at_round_parser,
    add_replace_agent_parser,
    handle_cross_run_replace_agent,
    handle_fork_at_round,
    handle_replace_agent,
)
from glossogen.cli.evaluate_command import add_evaluate_parser, handle_evaluate
from glossogen.cli.export_commands import (
    add_export_atif_parser,
    add_export_parser,
    add_export_thread_parser,
    handle_export,
    handle_export_atif,
    handle_export_thread,
)
from glossogen.cli.label_description_commands import (
    add_describe_label_parser,
    add_list_label_descriptions_parser,
    handle_describe_label,
    handle_list_label_descriptions,
)
from glossogen.cli.prod_sync_commands import (
    add_login_parser,
    add_push_to_prod_parser,
    add_sync_metadata_to_prod_parser,
    handle_login,
    handle_push_to_prod,
    handle_sync_metadata_to_prod,
)
from glossogen.cli.run_command import add_run_parser, handle_run
from glossogen.cli.scenario_authoring_commands import (
    add_new_scenario_parser,
    add_validate_parser,
    handle_new_scenario,
    handle_validate,
)
from glossogen.cli.serve_command import add_serve_parser, handle_serve
from glossogen.dotenv_loader import load_env_from_working_directory
from glossogen.scenario_loader import available_scenario_names, get_scenario_class


class _CommandHandler(Protocol):
    """A subcommand that runs to completion on its parsed flags."""

    def __call__(self, args: argparse.Namespace) -> None:
        """Run the subcommand."""
        ...


class _AsyncCommandHandler(Protocol):
    """A subcommand whose handler is a coroutine, run on a fresh event loop."""

    def __call__(self, args: argparse.Namespace) -> Coroutine[Any, Any, None]:
        """Return the coroutine that runs the subcommand."""
        ...


# The subcommands that parse every flag strictly. `run` and `evaluate` are absent:
# they resolve the scenario first and parse a second time, keeping `run`'s trailing
# key=value overrides.
_SYNC_COMMANDS: dict[str, _CommandHandler] = {
    "serve": handle_serve,
    "validate": handle_validate,
    "new-scenario": handle_new_scenario,
}
_ASYNC_COMMANDS: dict[str, _AsyncCommandHandler] = {
    "replace-agent": handle_replace_agent,
    "cross-run-replace-agent": handle_cross_run_replace_agent,
    "fork-at-round": handle_fork_at_round,
    "login": handle_login,
    "push-to-prod": handle_push_to_prod,
    "sync-metadata-to-prod": handle_sync_metadata_to_prod,
    "describe-label": handle_describe_label,
    "list-label-descriptions": handle_list_label_descriptions,
    "export": handle_export,
    "analyze": handle_analyze,
    "export-atif": handle_export_atif,
    "export-thread": handle_export_thread,
}


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser and all subcommand parsers."""
    parser = argparse.ArgumentParser(prog="glossogen")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scenario_names = available_scenario_names()

    add_run_parser(subparsers=subparsers, scenario_names=scenario_names)
    add_evaluate_parser(subparsers=subparsers, scenario_names=scenario_names)
    add_export_parser(subparsers=subparsers)
    add_analyze_parser(subparsers=subparsers)
    add_export_thread_parser(subparsers=subparsers, scenario_names=scenario_names)
    add_export_atif_parser(subparsers=subparsers, scenario_names=scenario_names)
    add_validate_parser(subparsers=subparsers, scenario_names=scenario_names)
    add_new_scenario_parser(subparsers=subparsers)
    add_serve_parser(subparsers=subparsers)
    add_replace_agent_parser(subparsers=subparsers, scenario_names=scenario_names)
    add_cross_run_replace_agent_parser(subparsers=subparsers, scenario_names=scenario_names)
    add_fork_at_round_parser(subparsers=subparsers, scenario_names=scenario_names)
    add_login_parser(subparsers=subparsers)
    add_push_to_prod_parser(subparsers=subparsers)
    add_sync_metadata_to_prod_parser(subparsers=subparsers)
    add_describe_label_parser(subparsers=subparsers)
    add_list_label_descriptions_parser(subparsers=subparsers)

    return parser


def main() -> None:
    """Parse the command line and dispatch to the subcommand it names."""

    load_env_from_working_directory()

    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser = _build_parser()

    # First pass: discover the command (and scenario name for run/evaluate).
    known_args, _ = parser.parse_known_args()

    sync_handler = _SYNC_COMMANDS.get(known_args.command)
    if sync_handler is not None:
        sync_handler(args=parser.parse_args())
        return
    async_handler = _ASYNC_COMMANDS.get(known_args.command)
    if async_handler is not None:
        asyncio.run(async_handler(args=parser.parse_args()))
        return

    scenario_cls = get_scenario_class(name=known_args.scenario_name)

    # Second pass: parse known flags and capture remaining key=value overrides.
    args, remaining = parser.parse_known_args()

    if args.command == "run":
        handle_run(parser=parser, args=args, remaining=remaining, scenario_cls=scenario_cls)
    else:
        asyncio.run(handle_evaluate(args=args, scenario_cls=scenario_cls))
