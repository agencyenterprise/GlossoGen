"""Readers for a run directory's derivation-provenance manifest files.

A derived run records where it came from in one of four sidecar files:
``fork_manifest.json``, ``replace_manifest.json`` (both replace-agent and
fork-at-round), and ``cross_run_replace_manifest.json``. These readers
project each file onto its response DTO and are shared by both the listing
(``discovery``) and detail (``detail_reader``) paths;
:func:`read_derivation_fields` is the same probe projected for the
derived-children listing. Window arithmetic goes through
``replace_manifest.boundary_round_of`` / ``rounds_after_of`` so the frozen
on-disk schema is translated by one rule.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast

import orjson

from glossogen.cross_run_replace_manifest import CROSS_RUN_REPLACE_MANIFEST_FILENAME
from glossogen.replace_manifest import (
    REPLACE_MANIFEST_FILENAME,
    boundary_round_of,
    rounds_after_of,
)
from glossogen.server.runs.models import (
    CrossRunReplaceAgentSource,
    ForkAtRoundSource,
    ForkSource,
    ReplaceAgentSource,
)

DerivationType = Literal["replace_agent", "fork_at_round", "cross_run_replace_agent"]


class DerivationFields(NamedTuple):
    """All manifest-derived fields needed to describe a derived run."""

    derivation_type: DerivationType
    after_round: int
    rounds_after: int
    replaced_agent_id: str | None
    replacement_model: str | None
    replacement_provider: str | None
    imported_model: str | None
    imported_provider: str | None
    source_b_run_id: str | None
    source_b_round_end: int | None


def _read_manifest(manifest_path: Path) -> dict[str, Any] | None:
    """Parse a manifest file to a raw dict, or ``None`` when it is absent."""
    if not manifest_path.exists():
        return None
    return cast(dict[str, Any], orjson.loads(manifest_path.read_bytes()))


def read_fork_source(run_dir: Path) -> ForkSource | None:
    """Read fork provenance from fork_manifest.json if it exists."""
    raw = _read_manifest(manifest_path=run_dir / "fork_manifest.json")
    if raw is None:
        return None
    forked_at = datetime.fromtimestamp(raw["forked_at"], tz=UTC)
    return ForkSource(
        source_run_id=raw["source_run_id"],
        target_message_id=raw["target_message_id"],
        forked_at=forked_at,
    )


def read_replace_agent_source(run_dir: Path) -> ReplaceAgentSource | None:
    """Read replace-agent provenance from replace_manifest.json if it exists.

    The manifest records the entry round as ``round_start``, so the fork
    boundary is one behind it. Returns ``None`` when the manifest is
    absent or when ``replaced_agent_id`` is null (a fork-at-round run;
    surfaced via :func:`read_fork_at_round_source`).
    """
    raw = _read_manifest(manifest_path=run_dir / REPLACE_MANIFEST_FILENAME)
    if raw is None:
        return None
    if raw.get("replaced_agent_id") is None:
        return None
    replaced_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    target_event_id = raw.get("target_event_id") or raw.get("target_message_id", "")
    return ReplaceAgentSource(
        source_run_id=raw["source_run_id"],
        after_round=boundary_round_of(entry_round=raw["round_start"]),
        target_event_id=target_event_id,
        replaced_agent_id=raw["replaced_agent_id"],
        replacement_model=raw["replacement_model"],
        replacement_provider=raw["replacement_provider"],
        replaced_at=replaced_at,
    )


def read_fork_at_round_source(run_dir: Path) -> ForkAtRoundSource | None:
    """Read fork-at-round provenance from replace_manifest.json.

    The manifest records the entry round as ``round_start`` and the rounds
    past it as ``rounds_after_swap``. Returns ``None`` when the manifest is
    absent or when ``replaced_agent_id`` is set (a replace-agent run;
    surfaced via :func:`read_replace_agent_source`).
    """
    raw = _read_manifest(manifest_path=run_dir / REPLACE_MANIFEST_FILENAME)
    if raw is None:
        return None
    if raw.get("replaced_agent_id") is not None:
        return None
    forked_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    return ForkAtRoundSource(
        source_run_id=raw["source_run_id"],
        after_round=boundary_round_of(entry_round=raw["round_start"]),
        rounds_after=rounds_after_of(stored_window=raw["rounds_after_swap"]),
        target_event_id=raw["target_event_id"],
        forked_at=forked_at,
    )


def read_cross_run_replace_agent_source(run_dir: Path) -> CrossRunReplaceAgentSource | None:
    """Read cross-run provenance from cross_run_replace_manifest.json if it exists."""
    raw = _read_manifest(manifest_path=run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME)
    if raw is None:
        return None
    replaced_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    return CrossRunReplaceAgentSource(
        source_a_run_id=raw["source_a_run_id"],
        source_b_run_id=raw["source_b_run_id"],
        after_round=boundary_round_of(entry_round=raw["round_start"]),
        source_b_round_end=raw["source_b_round_end"],
        target_event_id=raw["target_event_id"],
        replaced_agent_id=raw["replaced_agent_id"],
        imported_model=raw["imported_model"],
        imported_provider=raw["imported_provider"],
        replaced_at=replaced_at,
    )


def read_derivation_fields(run_dir: Path) -> DerivationFields | None:
    """Probe the run dir's manifest files to classify the derivation and pull boundary fields.

    Order matters: cross-run manifests coexist with no replace manifest;
    a plain replace-agent manifest with ``replaced_agent_id is None``
    encodes a fork-at-round derivation. Returns ``None`` when neither
    manifest exists.
    """
    cross_raw = _read_manifest(manifest_path=run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME)
    if cross_raw is not None:
        return DerivationFields(
            derivation_type="cross_run_replace_agent",
            after_round=boundary_round_of(entry_round=cross_raw["round_start"]),
            rounds_after=rounds_after_of(stored_window=cross_raw["rounds_after_swap"]),
            replaced_agent_id=cross_raw["replaced_agent_id"],
            replacement_model=None,
            replacement_provider=None,
            imported_model=cross_raw["imported_model"],
            imported_provider=cross_raw["imported_provider"],
            source_b_run_id=cross_raw["source_b_run_id"],
            source_b_round_end=cross_raw["source_b_round_end"],
        )

    replace_raw = _read_manifest(manifest_path=run_dir / REPLACE_MANIFEST_FILENAME)
    if replace_raw is not None:
        after_round = boundary_round_of(entry_round=replace_raw["round_start"])
        rounds_after = rounds_after_of(stored_window=replace_raw["rounds_after_swap"])
        replaced_agent_id = replace_raw.get("replaced_agent_id")
        if replaced_agent_id is None:
            return DerivationFields(
                derivation_type="fork_at_round",
                after_round=after_round,
                rounds_after=rounds_after,
                replaced_agent_id=None,
                replacement_model=None,
                replacement_provider=None,
                imported_model=None,
                imported_provider=None,
                source_b_run_id=None,
                source_b_round_end=None,
            )
        return DerivationFields(
            derivation_type="replace_agent",
            after_round=after_round,
            rounds_after=rounds_after,
            replaced_agent_id=replaced_agent_id,
            replacement_model=replace_raw["replacement_model"],
            replacement_provider=replace_raw["replacement_provider"],
            imported_model=None,
            imported_provider=None,
            source_b_run_id=None,
            source_b_round_end=None,
        )

    return None
