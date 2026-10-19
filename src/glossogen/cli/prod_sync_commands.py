"""The ``login``, ``push-to-prod`` and ``sync-metadata-to-prod`` subcommands."""

import argparse
import logging
from pathlib import Path

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.oauth_client import CREDENTIALS_PATH, run_login
from glossogen.prod_sync.prod_metadata_sync import MetadataSyncSpec, run_metadata_sync
from glossogen.prod_sync.prod_push import PushSpec, run_push_to_prod

logger = logging.getLogger(__name__)


def add_login_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``login`` subcommand and its flags."""
    login_parser = subparsers.add_parser(
        "login",
        help=(
            "Authenticate the CLI against a remote glossogen server via OAuth 2.0 "
            "PKCE. Opens a browser to the consent page; the CLI's "
            "loopback server collects the code and writes the resulting tokens "
            "to ~/.glossogen/credentials.json."
        ),
    )
    login_parser.add_argument(
        "--url",
        dest="url",
        type=str,
        required=True,
        help=(
            "Base URL of the glossogen backend to authenticate against "
            "(e.g. https://your-backend.example.com)."
        ),
    )
    login_parser.add_argument(
        "--timeout",
        dest="timeout_seconds",
        type=float,
        default=300.0,
        help="Seconds to wait for the OAuth callback before aborting (default: 300).",
    )


def add_push_to_prod_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``push-to-prod`` subcommand and its flags."""
    push_parser = subparsers.add_parser(
        "push-to-prod",
        help=(
            "Walk the local runs directory, diff against the remote glossogen "
            "server (filtered by label + has-report), and POST each missing "
            "run's bundle to /api/g/{slug}/runs/import using the OAuth token "
            "from `glossogen login`."
        ),
    )
    push_parser.add_argument(
        "--runs-dir",
        dest="runs_dir",
        type=str,
        default="./runs",
        help="Root directory of local runs (default: ./runs).",
    )
    push_parser.add_argument(
        "--label",
        dest="labels",
        action="append",
        default=[],
        help=(
            "Require the run's labels.json to contain this label. Repeatable; "
            "all listed labels must be present (AND semantics)."
        ),
    )
    push_parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        default=[],
        help=(
            "Restrict to runs of this scenario (repeatable, OR semantics). "
            "When omitted, every scenario directory is considered."
        ),
    )
    push_parser.add_argument(
        "--include-incomplete",
        dest="include_incomplete",
        action="store_true",
        help=(
            "Sync runs even when their <scenario>_report.json is missing. "
            "Off by default — completed runs (those with an eval report) are "
            "the safe set to sync."
        ),
    )
    push_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print the diff (what would be uploaded) without sending bytes.",
    )
    push_parser.add_argument(
        "--concurrency",
        dest="concurrency",
        type=int,
        default=1,
        help=(
            "Max concurrent uploads (default 1, hard-capped at 16). The export "
            "side holds the bundle bytes in memory, so high concurrency can "
            "overwhelm the laptop on bundles that are still large."
        ),
    )


def add_sync_metadata_to_prod_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``sync-metadata-to-prod`` subcommand and its flags."""
    sync_metadata_parser = subparsers.add_parser(
        "sync-metadata-to-prod",
        help=(
            "Sync local run metadata onto runs that already exist on prod. "
            "Walks local runs/, diffs each run's labels.json and evaluation "
            "report against what the remote returns from /runs, and PUTs "
            "the drifted ones. Also PUTs every local label description the "
            "remote glossary is missing or records differently; descriptions "
            "only the remote has are left alone. Local is the source of "
            "truth (use `push-to-prod` for runs that aren't yet on prod at "
            "all)."
        ),
    )
    sync_metadata_parser.add_argument(
        "--runs-dir",
        dest="runs_dir",
        type=str,
        default="./runs",
        help="Root directory of local runs (default: ./runs).",
    )
    sync_metadata_parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        default=[],
        help=(
            "Restrict to runs of this scenario (repeatable, OR semantics). "
            "When omitted, every scenario directory is considered."
        ),
    )
    sync_metadata_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print the per-run drift without sending any PUTs.",
    )
    sync_metadata_parser.add_argument(
        "--concurrency",
        dest="concurrency",
        type=int,
        default=4,
        help=(
            "Max concurrent PUTs (default 4, hard-capped at 8). Lightweight "
            "compared to bundle uploads because the payload is just the "
            "label list."
        ),
    )


async def handle_login(args: argparse.Namespace) -> None:
    """Drive the ``glossogen login`` subcommand."""
    try:
        credentials = await run_login(
            issuer_url=args.url,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        logger.exception("Login failed")
        raise SystemExit(f"Login failed: {exc}") from exc
    print(
        f"Logged in to {credentials.issuer_url} as group "
        f"{credentials.group_slug!r}. "
        f"Credentials saved to {CREDENTIALS_PATH}."
    )


async def handle_push_to_prod(args: argparse.Namespace) -> None:
    """Drive the ``glossogen push-to-prod`` subcommand."""
    concurrency = max(1, min(int(args.concurrency), 16))
    scenarios_arg: list[str] = args.scenarios
    scenarios = frozenset(scenarios_arg) if scenarios_arg else None
    spec = PushSpec(
        runs_dir=Path(args.runs_dir),
        labels=frozenset(args.labels),
        scenarios=scenarios,
        require_report=not args.include_incomplete,
        dry_run=args.dry_run,
        concurrency=concurrency,
    )
    tally = await run_push_to_prod(spec=spec)
    print(
        f"Done. uploaded={len(tally.uploaded)}  "
        f"skipped={len(tally.skipped)}  "
        f"failed={len(tally.failed)}"
    )
    if tally.failed:
        raise SystemExit(1)


async def handle_sync_metadata_to_prod(args: argparse.Namespace) -> None:
    """Drive the ``glossogen sync-metadata-to-prod`` subcommand."""
    concurrency = max(1, min(int(args.concurrency), 8))
    scenarios_arg: list[str] = args.scenarios
    scenarios = frozenset(scenarios_arg) if scenarios_arg else None
    spec = MetadataSyncSpec(
        runs_dir=Path(args.runs_dir),
        scenarios=scenarios,
        dry_run=args.dry_run,
        concurrency=concurrency,
    )
    tally = await run_metadata_sync(spec=spec)
    print(
        f"Done. labels={len(tally.synced_labels)}  eval={len(tally.synced_eval)}  "
        f"descriptions={len(tally.synced_descriptions)}  "
        f"unchanged={len(tally.unchanged)}  failed={len(tally.failed)}"
    )
    if tally.failed:
        raise SystemExit(1)
