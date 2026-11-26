"""The ``install-skill`` subcommand."""

import argparse
import logging
from pathlib import Path

from glossogen.agent_skills.skill_installation import (
    SkillAlreadyInstalled,
    install_skills,
    shipped_skill_names,
)
from glossogen.cli.subcommand_parsers import SubcommandParsers

logger = logging.getLogger(__name__)


def add_install_skill_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``install-skill`` subcommand and its flags."""
    parser = subparsers.add_parser(
        "install-skill",
        help=(
            "Copy the Claude Code skills that this glossogen ships "
            f"({', '.join(shipped_skill_names())}) into a project's skills folder"
        ),
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        default=".claude/skills",
        help="Skills folder to copy into, created if missing (default: .claude/skills)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Overwrite a skill folder that already exists, such as one from an older glossogen",
    )


def handle_install_skill(args: argparse.Namespace) -> None:
    """Copy the shipped skills and print where each one went."""
    try:
        installed = install_skills(target_dir=Path(args.target_dir), replace=args.replace)
    except SkillAlreadyInstalled as refusal:
        logger.exception("A skill folder already exists")
        raise SystemExit(str(refusal)) from refusal
    for skill_dir in installed:
        print(f"Installed {skill_dir}")
