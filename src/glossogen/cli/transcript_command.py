"""The ``transcript`` subcommand."""

import argparse
import logging
from pathlib import Path

import aiofiles

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.run_export.run_transcript import (
    TranscriptSection,
    render_run_transcript,
    section_heading,
)
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.scenario_contract.loader import get_scenario_class

logger = logging.getLogger(__name__)


def add_transcript_parser(subparsers: SubcommandParsers, scenario_names: list[str]) -> None:
    """Add the ``transcript`` subcommand and its flags."""
    parser = subparsers.add_parser(
        "transcript",
        help="Print a run's event log as plain text, round by round",
    )
    parser.add_argument(
        "scenario_name",
        type=str,
        help=f"Name of the scenario the run belongs to. Loaded: {', '.join(scenario_names)}",
    )
    parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Path to the run directory (e.g. runs/veyru/1742234567)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help=(
            "Write one file per round, round_00.txt for what comes before round 1, "
            "into this directory (created if missing). Omit to print to stdout."
        ),
    )


async def handle_transcript(args: argparse.Namespace) -> None:
    """Render the run's log and print it, or write one file per round."""
    run_dir = Path(args.run_dir).resolve()
    events = await load_events(
        log_path=event_log_path(run_dir=run_dir, scenario_name=args.scenario_name)
    )
    sections = render_run_transcript(events=events)
    readme_line = _scenario_readme_line(scenario_name=args.scenario_name)
    if args.out_dir is None:
        print(readme_line)
        for section in sections:
            print(_section_file_text(section=section))
        return
    await _write_section_files(
        sections=sections, readme_line=readme_line, out_dir=Path(args.out_dir)
    )


def _scenario_readme_line(scenario_name: str) -> str:
    """Where the scenario's README is, for a reader who needs the rules of the game."""
    readme = get_scenario_class(name=scenario_name).scenario_package_files() / "README.md"
    if readme.is_file():
        return f"Scenario README: {readme}"
    return "Scenario README: the scenario's package has none"


def _section_file_text(section: TranscriptSection) -> str:
    """A section with its heading, ending in a blank line."""
    return f"{section_heading(round_number=section.round_number)}\n{section.text}\n"


async def _write_section_files(
    sections: list[TranscriptSection], readme_line: str, out_dir: Path
) -> None:
    """Write ``round_NN.txt`` per section; the README line opens ``round_00.txt``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for section in sections:
        path = out_dir / f"round_{section.round_number:02d}.txt"
        text = _section_file_text(section=section)
        if section.round_number == 0:
            text = f"{readme_line}\n{text}"
        async with aiofiles.open(path, mode="w") as handle:
            await handle.write(text)
    logger.info("Wrote %d transcript files to %s", len(sections), out_dir)
