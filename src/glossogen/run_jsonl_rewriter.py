"""Shared JSONL rewrite helper for derived runs (fork, replace-agent).

Both the fork and replace-agent flows clone a source run's git repo at a
target commit, then need to rewrite the in-place JSONL to (a) update the
embedded ``run_id``, (b) optionally apply text edits to ``message_sent``
events, and (c) drop a subset of events so derived agents start from a
clean state. The drop predicate is the only thing that varies between the
two flows.
"""

import logging
from pathlib import Path
from typing import Any, Callable

import orjson

logger = logging.getLogger(__name__)


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
    raw_bytes = log_path.read_bytes()
    lines = raw_bytes.split(b"\n")
    output_lines: list[bytes] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        event_dict = orjson.loads(stripped)

        if should_drop_event(event_dict):
            continue

        event_type = event_dict.get("event_type")

        if event_type == "simulation_started":
            event_dict["run_id"] = new_run_id

        if event_type == "message_sent":
            msg = event_dict.get("message", {})
            msg_id = msg.get("message_id", "")
            if msg_id in message_edits:
                msg["text"] = message_edits[msg_id]

        output_lines.append(orjson.dumps(event_dict))

    log_path.write_bytes(b"\n".join(output_lines) + b"\n")

    logger.info(
        "JSONL rewrite complete: %d lines, run_id=%s, %d message edits",
        len(output_lines),
        new_run_id,
        len(message_edits),
    )
    return len(output_lines)


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
    raw_bytes = log_path.read_bytes()
    lines = raw_bytes.split(b"\n")
    output_lines: list[bytes] = []
    patched = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        event_dict = orjson.loads(stripped)
        if not patched and event_dict.get("event_type") == "simulation_started":
            event_dict["scenario_config"] = scenario_config
            patched = True
        output_lines.append(orjson.dumps(event_dict))

    if not patched:
        raise ValueError(
            f"No simulation_started event found in {log_path}; cannot patch scenario_config"
        )

    log_path.write_bytes(b"\n".join(output_lines) + b"\n")
