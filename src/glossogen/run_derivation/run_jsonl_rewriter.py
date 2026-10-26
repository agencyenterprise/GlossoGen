"""Shared JSONL rewrite helper for derived runs (fork, replace-agent).

Both the fork and replace-agent flows copy a source run directory and
truncate its JSONL at a target event, then rewrite it to (a) update the
embedded ``run_id``, (b) optionally apply text edits to ``message_sent``
events, and (c) drop a subset of events so derived agents start from a
clean state. The drop predicate is the only thing that varies between the
two flows.
"""

import logging
from pathlib import Path
from typing import Any, Callable

from glossogen.jsonl_lines import rewrite_json_objects

logger = logging.getLogger(__name__)


def drop_simulation_ended(event_dict: dict[str, Any]) -> bool:
    """Drop ``simulation_ended`` events from a fork's cloned log.

    A source that was killed or crashed and later resumed carries a mid-log
    end marker; a fork past the source's final round is truncated just before
    the last one. Either way an end marker inside a clone describes the
    source, not the fork, and a stale line would trip every orchestration
    that gates evaluation on ``simulation_ended`` while the fork still runs.
    """
    return event_dict.get("event_type") == "simulation_ended"


def rewrite_run_jsonl(
    log_path: Path,
    new_run_id: str,
    message_edits: dict[str, str],
    should_drop_event: Callable[[dict[str, Any]], bool],
) -> int:
    """Rewrite ``log_path`` in place for a derived run.

    Walks the JSONL once: applies the new ``run_id`` to the
    ``simulation_started`` event, applies any ``message_edits`` keyed by
    message ID, and drops events for which ``should_drop_event`` returns
    True. Returns the number of lines written.
    """

    def derive(event_dict: dict[str, Any]) -> dict[str, Any] | None:
        if should_drop_event(event_dict):
            return None

        event_type = event_dict.get("event_type")

        if event_type == "simulation_started":
            event_dict["run_id"] = new_run_id

        if event_type == "message_sent":
            msg = event_dict.get("message", {})
            msg_id = msg.get("message_id", "")
            if msg_id in message_edits:
                msg["text"] = message_edits[msg_id]

        return event_dict

    rewritten = rewrite_json_objects(lines=log_path.read_bytes().split(b"\n"), transform=derive)
    log_path.write_bytes(rewritten.content)

    logger.info(
        "JSONL rewrite complete: %d lines, run_id=%s, %d message edits",
        rewritten.line_count,
        new_run_id,
        len(message_edits),
    )
    return rewritten.line_count


def patch_simulation_started_scenario_config(
    log_path: Path,
    scenario_config: dict[str, Any],
) -> None:
    """Overwrite the first ``simulation_started`` event's ``scenario_config``.

    Derived runs (fork, replace-agent) clone a source repo at an old commit
    where the JSONL may predate later schema additions or backfills. After
    validation produces an authoritative merged config, this helper writes
    it into the cloned JSONL so downstream readers (evaluate, UI) see a
    config that matches the new run's actual configuration.
    """
    patched = False

    def patch_first_start(event_dict: dict[str, Any]) -> dict[str, Any]:
        nonlocal patched
        if not patched and event_dict.get("event_type") == "simulation_started":
            event_dict["scenario_config"] = scenario_config
            patched = True
        return event_dict

    rewritten = rewrite_json_objects(
        lines=log_path.read_bytes().split(b"\n"), transform=patch_first_start
    )

    if not patched:
        raise ValueError(
            f"No simulation_started event found in {log_path}; cannot patch scenario_config"
        )

    log_path.write_bytes(rewritten.content)
