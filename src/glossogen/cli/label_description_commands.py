"""The ``describe-label`` and ``list-label-descriptions`` subcommands, which write
and read the local group's label glossary.
"""

import argparse
from pathlib import Path

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.db.local_tenant import LOCAL_GROUP_ID
from glossogen.label_descriptions.filesystem_label_description_store import (
    FilesystemLabelDescriptionStore,
)
from glossogen.label_descriptions.label_description_models import LabelDescription


def add_describe_label_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``describe-label`` subcommand and its flags."""
    describe_label_parser = subparsers.add_parser(
        "describe-label",
        help=(
            "Record what a label means, or delete the recorded meaning. Writes "
            "the local group's glossary under <runs-dir>/_label_descriptions/, "
            "the same file the no-database server reads."
        ),
    )
    describe_label_parser.add_argument(
        "label",
        type=str,
        help="The exact label string (e.g. baseline_oss or budget=800).",
    )
    describe_label_action = describe_label_parser.add_mutually_exclusive_group(required=True)
    describe_label_action.add_argument(
        "--description",
        dest="description",
        type=str,
        default=None,
        help="What the label means.",
    )
    describe_label_action.add_argument(
        "--delete",
        dest="delete",
        action="store_true",
        help="Remove the label's recorded description instead of setting one.",
    )
    describe_label_parser.add_argument(
        "--runs-dir",
        dest="runs_dir",
        type=str,
        default="./runs",
        help="Root directory of local runs (default: ./runs).",
    )


def add_list_label_descriptions_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``list-label-descriptions`` subcommand and its flags."""
    list_label_descriptions_parser = subparsers.add_parser(
        "list-label-descriptions",
        help="Print the local group's label glossary, one label per line.",
    )
    list_label_descriptions_parser.add_argument(
        "--runs-dir",
        dest="runs_dir",
        type=str,
        default="./runs",
        help="Root directory of local runs (default: ./runs).",
    )


async def handle_describe_label(args: argparse.Namespace) -> None:
    """Drive the ``glossogen describe-label`` subcommand."""
    store = FilesystemLabelDescriptionStore(runs_dir=Path(args.runs_dir))
    if args.delete:
        deleted = await store.delete_description(group_id=LOCAL_GROUP_ID, label=args.label)
        if not deleted:
            raise SystemExit(f"No description recorded for label {args.label!r}.")
        print(f"Deleted the description of label {args.label!r}.")
        return
    if not args.description.strip():
        raise SystemExit("--description must not be empty.")
    entry = LabelDescription(label=args.label, description=args.description)
    await store.set_description(group_id=LOCAL_GROUP_ID, entry=entry)
    print(f"{entry.label}: {entry.description}")


async def handle_list_label_descriptions(args: argparse.Namespace) -> None:
    """Drive the ``glossogen list-label-descriptions`` subcommand."""
    store = FilesystemLabelDescriptionStore(runs_dir=Path(args.runs_dir))
    descriptions = await store.list_descriptions(group_id=LOCAL_GROUP_ID)
    if not descriptions:
        print("No label descriptions recorded.")
        return
    for entry in descriptions:
        print(f"{entry.label}\t{entry.description}")
