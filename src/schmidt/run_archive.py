"""Filesystem helpers for simulation run directories.

Provides directory claiming, JSONL event-id lookup, point-in-time JSONL
truncation, and one-shot cleanup of legacy ``.git`` directories from runs
created before the git-backed run history was removed. The JSONL event log
is the canonical state ledger; these helpers operate on it directly.
"""

import logging
import shutil
import time
from pathlib import Path
from typing import Any, Callable, NamedTuple

import aiofiles
import orjson

logger = logging.getLogger(__name__)


class EventLocation(NamedTuple):
    """Position of a single event line inside a JSONL file."""

    line_number: int
    end_offset: int
    event_dict: dict[str, Any]


async def find_event_offset(log_path: Path, event_id: str) -> EventLocation | None:
    """Scan a JSONL file for the line whose ``event_id`` matches.

    Returns the byte offset of the first byte AFTER the matched line's
    trailing newline, so ``log_path.read_bytes()[:end_offset]`` yields a
    truncated copy that includes the matched event.
    """
    return await _find_offset_by_predicate(
        log_path=log_path,
        predicate=lambda raw: raw.get("event_id") == event_id,
    )


async def _find_offset_by_predicate(
    log_path: Path,
    predicate: Callable[[dict[str, Any]], bool],
) -> EventLocation | None:
    """Walk the JSONL line-by-line, returning the location of the first matching line."""
    offset = 0
    line_number = 0
    async with aiofiles.open(log_path, mode="rb") as f:
        async for line in f:
            line_number += 1
            line_bytes_len = len(line)
            offset += line_bytes_len
            stripped = line.strip()
            if not stripped:
                continue
            raw: dict[str, Any] = orjson.loads(stripped)
            if predicate(raw):
                return EventLocation(
                    line_number=line_number,
                    end_offset=offset,
                    event_dict=raw,
                )
    return None


_EXCLUDED_COPY_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "stream.json",
        "__pycache__",
        # The source's labels would otherwise be inherited; if the orchestrator's
        # subsequent re-label step fails or races, the derived run shows up as
        # the source's "phase=baseline" entry in label-driven worklists.
        "labels.json",
        # Source-specific UI / eval caches. Inheriting these makes the derived
        # run look like the source: the FE shows "Completed at round N/M" from
        # the source's snapshot, the rolling evaluator thinks the run is
        # already evaluated (skipping it), and the streamlit Multi-swap tab
        # serves stale numbers.
        "run_summary_cache.json",
        "eval_in_progress.json",
        "multi_swap_cache.json",
        # Source-specific evaluation artifacts. The derived run will produce
        # its own when re-evaluated; inheriting the source's makes
        # ``has_evaluation`` true before any post-resume metric has run.
        "communication_open_coding.json",
        "communication_feature_presence.json",
        "protocol_explanation_responses.jsonl",
        "protocol_explanation_usage.json",
        "protocol_probe_responses.jsonl",
        "protocol_probe_usage.json",
        "protocol_probe_replica_self_similarity.json",
        "protocol_probe_agent_pair_similarity.json",
        "protocol_probe_cutoff_trajectory.json",
    }
)

_EXCLUDED_COPY_SUFFIXES: tuple[str, ...] = (
    "_stdout.log",
    "_start.log",
    "_debug.jsonl",
    ".pyc",
    # Source-scenario eval reports (every scenario writes ``<scenario>_report.json``).
    "_report.json",
)


def _ignore_excluded(src: str, names: list[str]) -> list[str]:
    """Return names to skip when copying a run directory.

    Signature matches the ``ignore`` callback expected by ``shutil.copytree``.
    """
    del src
    ignored: list[str] = []
    for name in names:
        if name in _EXCLUDED_COPY_NAMES:
            ignored.append(name)
            continue
        for suffix in _EXCLUDED_COPY_SUFFIXES:
            if name.endswith(suffix):
                ignored.append(name)
                break
    return ignored


async def copy_run_at_event(
    source_dir: Path,
    target_dir: Path,
    jsonl_path_within_run: Path,
    truncate_after_offset: int,
) -> None:
    """Copy ``source_dir`` into ``target_dir`` and truncate the run JSONL.

    The target directory must already exist (created by ``claim_run_dir``).
    Every file from the source is copied except `.git`, stream manifests,
    debug logs, and `*.pyc`. After copy, the JSONL at
    ``jsonl_path_within_run`` (relative to the run dir) is truncated to
    ``truncate_after_offset`` bytes so it ends at the target event.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source_dir.iterdir()):
        if entry.name in _EXCLUDED_COPY_NAMES:
            continue
        if any(entry.name.endswith(suffix) for suffix in _EXCLUDED_COPY_SUFFIXES):
            continue
        destination = target_dir / entry.name
        if entry.is_dir():
            shutil.copytree(src=entry, dst=destination, ignore=_ignore_excluded)
        else:
            shutil.copy2(src=entry, dst=destination)

    target_log_path = target_dir / jsonl_path_within_run
    raw = target_log_path.read_bytes()
    target_log_path.write_bytes(raw[:truncate_after_offset])
    logger.info(
        "Copied run %s -> %s (jsonl truncated to %d bytes)",
        source_dir,
        target_dir,
        truncate_after_offset,
    )


def strip_legacy_git_dir(run_dir: Path) -> None:
    """Delete ``run_dir/.git`` if it exists.

    Runs created before the git-backed history was removed retain a
    ``.git`` directory. Once removed the run is functionally identical to
    a fresh run and the deletion is idempotent.
    """
    git_dir = run_dir / ".git"
    if git_dir.is_dir():
        shutil.rmtree(git_dir, ignore_errors=True)
        logger.info("Removed legacy .git/ at %s", git_dir)


TRASH_DIR_NAME: str = "_trash"


def move_run_to_trash(runs_dir: Path, scenario_name: str, run_dir_name: str) -> Path:
    """Move a run directory into ``{runs_dir}/_trash/{scenario}/{run_dir_name}/``.

    A reversible alternative to ``shutil.rmtree``: the run's files are
    preserved under the trash directory so a deletion can be undone by moving
    the directory back. Returns the destination path. If a trashed run with
    the same name already exists, a numeric suffix is appended so no prior
    trashed run is overwritten.
    """
    source = runs_dir / scenario_name / run_dir_name
    trash_scenario_dir = runs_dir / TRASH_DIR_NAME / scenario_name
    trash_scenario_dir.mkdir(parents=True, exist_ok=True)

    destination = trash_scenario_dir / run_dir_name
    collision_index = 1
    while destination.exists():
        destination = trash_scenario_dir / f"{run_dir_name}.{collision_index}"
        collision_index += 1

    shutil.move(src=str(source), dst=str(destination))
    logger.info("Moved run %s to trash at %s", source, destination)
    return destination


def claim_run_dir(runs_dir: Path, scenario_name: str) -> Path:
    """Atomically claim a unique run directory using the current unix timestamp.

    Creates ``{runs_dir}/{scenario_name}/{unix_timestamp}/``. If another
    run already claimed the same second, sleeps 1s so the wall clock
    advances and retries. Uses ``mkdir(exist_ok=False)`` for atomic
    collision detection on POSIX filesystems.
    """
    base_dir = runs_dir / scenario_name
    while True:
        candidate = base_dir / str(int(time.time()))
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            time.sleep(1)
