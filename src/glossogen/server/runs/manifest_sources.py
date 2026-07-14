"""Readers for a run directory's derivation-provenance manifest files.

A derived run records where it came from in one of four sidecar files:
``fork_manifest.json``, ``replace_manifest.json`` (both replace-agent and
round-anchored resume), and ``cross_run_replace_manifest.json``. These readers
project each file onto its response DTO and are shared by both the listing
(``discovery``) and detail (``detail_reader``) paths.
"""

from datetime import UTC, datetime
from pathlib import Path

import orjson

from glossogen.server.runs.models import (
    CrossRunReplaceAgentSource,
    ForkSource,
    ReplaceAgentSource,
    ResumeAtRoundSource,
)


def read_fork_source(run_dir: Path) -> ForkSource | None:
    """Read fork provenance from fork_manifest.json if it exists."""
    manifest_path = run_dir / "fork_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    forked_at = datetime.fromtimestamp(raw["forked_at"], tz=UTC)
    return ForkSource(
        source_run_id=raw["source_run_id"],
        target_message_id=raw["target_message_id"],
        forked_at=forked_at,
    )


def read_replace_agent_source(run_dir: Path) -> ReplaceAgentSource | None:
    """Read replace-agent provenance from replace_manifest.json if it exists.

    Returns ``None`` when the manifest is absent or when ``replaced_agent_id``
    is null (a round-anchored resume; surfaced via
    :func:`read_resume_at_round_source`).
    """
    manifest_path = run_dir / "replace_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    if raw.get("replaced_agent_id") is None:
        return None
    replaced_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    target_event_id = raw.get("target_event_id") or raw.get("target_message_id", "")
    return ReplaceAgentSource(
        source_run_id=raw["source_run_id"],
        round_start=raw["round_start"],
        target_event_id=target_event_id,
        replaced_agent_id=raw["replaced_agent_id"],
        replacement_model=raw["replacement_model"],
        replacement_provider=raw["replacement_provider"],
        replaced_at=replaced_at,
    )


def read_resume_at_round_source(run_dir: Path) -> ResumeAtRoundSource | None:
    """Read round-anchored-resume provenance from replace_manifest.json.

    Returns ``None`` when the manifest is absent or when ``replaced_agent_id``
    is set (a replace-agent run; surfaced via
    :func:`read_replace_agent_source`).
    """
    manifest_path = run_dir / "replace_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    if raw.get("replaced_agent_id") is not None:
        return None
    resumed_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    return ResumeAtRoundSource(
        source_run_id=raw["source_run_id"],
        round_start=raw["round_start"],
        rounds_after_resume=raw["rounds_after_swap"],
        target_event_id=raw["target_event_id"],
        resumed_at=resumed_at,
    )


def read_cross_run_replace_agent_source(run_dir: Path) -> CrossRunReplaceAgentSource | None:
    """Read cross-run provenance from cross_run_replace_manifest.json if it exists."""
    manifest_path = run_dir / "cross_run_replace_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    replaced_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    return CrossRunReplaceAgentSource(
        source_a_run_id=raw["source_a_run_id"],
        source_b_run_id=raw["source_b_run_id"],
        round_start=raw["round_start"],
        source_b_round_end=raw["source_b_round_end"],
        target_event_id=raw["target_event_id"],
        replaced_agent_id=raw["replaced_agent_id"],
        imported_model=raw["imported_model"],
        imported_provider=raw["imported_provider"],
        replaced_at=replaced_at,
    )
