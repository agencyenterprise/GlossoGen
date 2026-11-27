"""Rewriting the cloned JSONL of a fork.

The fork flows (replace-agent, cross-run replace-agent, fork-at-round) copy a
source run directory with its JSONL truncated at the boundary, then rewrite the
copy to carry the new ``run_id``, drop the source's ``simulation_ended`` markers,
and record the fork's validated config in its ``simulation_started``. A response
whose tool calls ran before the boundary but that was logged after it is
inserted into the copy, just before the boundary event.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Iterable

import aiofiles
import orjson

from glossogen.models.glossogen_build import GlossogenBuild
from glossogen.run_storage.jsonl_lines import JsonObjectLines, rewrite_json_objects

logger = logging.getLogger(__name__)


def drop_simulation_ended(event_dict: dict[str, Any]) -> bool:
    """Drop ``simulation_ended`` events from a fork's cloned log.

    A source that was killed or crashed and later resumed carries a mid-log
    end marker, which a clone cut after it keeps. That marker describes the
    source, not the fork, and a stale line would trip every orchestration
    that gates evaluation on ``simulation_ended`` while the fork still runs.
    """
    return event_dict.get("event_type") == "simulation_ended"


def _call_ids_without_response(records: Iterable[dict[str, Any]]) -> set[str]:
    """The ids of the invoked tool calls that no ``llm_response_received`` in ``records`` holds."""
    invoked: set[str] = set()
    held: set[str] = set()
    for record in records:
        event_type = record.get("event_type")
        if event_type == "tool_call_invoked":
            invoked.add(record["call_id"])
        elif event_type == "llm_response_received":
            held.update(call["call_id"] for call in record["tool_calls"])
    return invoked - held


def _responses_holding(
    records: Iterable[dict[str, Any]], call_ids: set[str]
) -> list[dict[str, Any]]:
    """Each ``llm_response_received`` in ``records`` that holds one of ``call_ids``.

    Each response keeps only the calls in ``call_ids``.
    """
    responses: list[dict[str, Any]] = []
    for record in records:
        if record.get("event_type") != "llm_response_received":
            continue
        kept_calls = [call for call in record["tool_calls"] if call["call_id"] in call_ids]
        if not kept_calls:
            continue
        record["tool_calls"] = kept_calls
        responses.append(record)
    return responses


async def insert_responses_cut_at_boundary(
    source_log_path: Path, log_path: Path, truncate_after_offset: int
) -> int:
    """Add to a fork's cut log each source response whose tool calls ran before the cut.

    The runner logs a response once its tool calls have run, so a response whose
    calls started before the boundary can sit after it in the source log. Each
    such response is written into ``log_path`` holding only the calls that have
    a ``tool_call_invoked`` before the boundary. The responses go just before
    the boundary event, which stays the log's last line, because resume reads
    any agent event after the boundary as the fork having played. A last source
    line with no newline, from a source that is still being written, is not
    read. Returns the number of responses inserted.
    """
    async with aiofiles.open(source_log_path, mode="rb") as source:
        raw = await source.read()
    head = raw[:truncate_after_offset]
    cut_call_ids = _call_ids_without_response(records=JsonObjectLines(lines=head.split(b"\n")))
    if not cut_call_ids:
        return 0
    complete_tail_lines = raw[truncate_after_offset:].split(b"\n")[:-1]
    responses = _responses_holding(
        records=JsonObjectLines(lines=complete_tail_lines), call_ids=cut_call_ids
    )
    if not responses:
        return 0
    boundary_line_start = head.rstrip(b"\n").rfind(b"\n") + 1
    inserted = b"".join(orjson.dumps(response) + b"\n" for response in responses)
    async with aiofiles.open(log_path, mode="wb") as log:
        await log.write(head[:boundary_line_start] + inserted + head[boundary_line_start:])
    logger.info(
        "Inserted %d responses whose tool calls ran before the boundary into %s",
        len(responses),
        log_path,
    )
    return len(responses)


def rewrite_run_jsonl(
    log_path: Path,
    new_run_id: str,
    glossogen_build: GlossogenBuild,
    message_edits: dict[str, str],
    should_drop_event: Callable[[dict[str, Any]], bool],
) -> int:
    """Rewrite ``log_path`` in place for a derived run.

    Walks the JSONL once: applies the new ``run_id`` and the deriving process's
    ``glossogen_build`` to the ``simulation_started`` event, applies any
    ``message_edits`` keyed by message ID, and drops events for which
    ``should_drop_event`` returns True. Returns the number of lines written.
    """

    def derive(event_dict: dict[str, Any]) -> dict[str, Any] | None:
        if should_drop_event(event_dict):
            return None

        event_type = event_dict.get("event_type")

        if event_type == "simulation_started":
            event_dict["run_id"] = new_run_id
            event_dict["glossogen_build"] = glossogen_build.model_dump(mode="json")

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

    A fork's cloned JSONL opens with the source's ``simulation_started``, which
    records the source's config. This writes the fork's validated config over
    it (merged knobs, the fork's ``round_count`` and pinned ``model_overrides``),
    so readers of the log (evaluate, the UI) see the config the fork runs under.
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
