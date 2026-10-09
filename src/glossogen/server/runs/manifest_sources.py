"""Readers for a run directory's derivation-provenance manifest files.

A derived run records where it came from in a sidecar file:
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
from typing import Literal, NamedTuple

from pydantic import BaseModel

from glossogen.cross_run_replace_manifest import read_cross_run_replace_manifest
from glossogen.replace_manifest import (
    boundary_round_of,
    read_replace_manifest,
    rounds_after_of,
)
from glossogen.server.runs.models import (
    CrossRunReplaceAgentSource,
    ForkAtRoundSource,
    ForkSource,
    ReplaceAgentSource,
)

FORK_MANIFEST_FILENAME = "fork_manifest.json"

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


class ForkManifest(BaseModel):
    """The shape of ``fork_manifest.json``.

    Nothing in this codebase writes the file. Runs forked at a message
    carry it, and this model reads them.
    """

    source_run_id: str
    target_message_id: str
    forked_at: float


def read_fork_source(run_dir: Path) -> ForkSource | None:
    """Read fork provenance from fork_manifest.json if it exists."""
    manifest_path = run_dir / FORK_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    manifest = ForkManifest.model_validate_json(manifest_path.read_bytes())
    return ForkSource(
        source_run_id=manifest.source_run_id,
        target_message_id=manifest.target_message_id,
        forked_at=datetime.fromtimestamp(manifest.forked_at, tz=UTC),
    )


def read_replace_agent_source(run_dir: Path) -> ReplaceAgentSource | None:
    """Read replace-agent provenance from replace_manifest.json if it exists.

    The manifest records the entry round as ``round_start``, so the fork
    boundary is one behind it. Returns ``None`` when the manifest is
    absent or when ``replaced_agent_id`` is null (a fork-at-round run;
    surfaced via :func:`read_fork_at_round_source`).
    """
    manifest = read_replace_manifest(run_dir=run_dir)
    if manifest is None or manifest.replaced_agent_id is None:
        return None
    if manifest.replacement_model is None or manifest.replacement_provider is None:
        raise ValueError(
            f"{run_dir} replace_manifest.json names replaced agent "
            f"{manifest.replaced_agent_id!r} without a replacement model and provider"
        )
    return ReplaceAgentSource(
        source_run_id=manifest.source_run_id,
        after_round=boundary_round_of(entry_round=manifest.round_start),
        target_event_id=manifest.target_event_id,
        replaced_agent_id=manifest.replaced_agent_id,
        replacement_model=manifest.replacement_model,
        replacement_provider=manifest.replacement_provider,
        replaced_at=datetime.fromtimestamp(manifest.replaced_at, tz=UTC),
    )


def read_fork_at_round_source(run_dir: Path) -> ForkAtRoundSource | None:
    """Read fork-at-round provenance from replace_manifest.json.

    The manifest records the entry round as ``round_start`` and the rounds
    past it as ``rounds_after_swap``. Returns ``None`` when the manifest is
    absent or when ``replaced_agent_id`` is set (a replace-agent run;
    surfaced via :func:`read_replace_agent_source`).
    """
    manifest = read_replace_manifest(run_dir=run_dir)
    if manifest is None or manifest.replaced_agent_id is not None:
        return None
    return ForkAtRoundSource(
        source_run_id=manifest.source_run_id,
        after_round=boundary_round_of(entry_round=manifest.round_start),
        rounds_after=rounds_after_of(stored_window=manifest.rounds_after_swap),
        target_event_id=manifest.target_event_id,
        forked_at=datetime.fromtimestamp(manifest.replaced_at, tz=UTC),
    )


def read_cross_run_replace_agent_source(run_dir: Path) -> CrossRunReplaceAgentSource | None:
    """Read cross-run provenance from cross_run_replace_manifest.json if it exists."""
    manifest = read_cross_run_replace_manifest(run_dir=run_dir)
    if manifest is None:
        return None
    return CrossRunReplaceAgentSource(
        source_a_run_id=manifest.source_a_run_id,
        source_b_run_id=manifest.source_b_run_id,
        after_round=boundary_round_of(entry_round=manifest.round_start),
        source_b_round_end=manifest.source_b_round_end,
        target_event_id=manifest.target_event_id,
        replaced_agent_id=manifest.replaced_agent_id,
        imported_model=manifest.imported_model,
        imported_provider=manifest.imported_provider,
        replaced_at=datetime.fromtimestamp(manifest.replaced_at, tz=UTC),
    )


def read_derivation_fields(run_dir: Path) -> DerivationFields | None:
    """Probe the run dir's manifest files to classify the derivation and pull boundary fields.

    Order matters: cross-run manifests coexist with no replace manifest;
    a plain replace-agent manifest with ``replaced_agent_id is None``
    encodes a fork-at-round derivation. Returns ``None`` when neither
    manifest exists.
    """
    cross_run = read_cross_run_replace_manifest(run_dir=run_dir)
    if cross_run is not None:
        return DerivationFields(
            derivation_type="cross_run_replace_agent",
            after_round=boundary_round_of(entry_round=cross_run.round_start),
            rounds_after=rounds_after_of(stored_window=cross_run.rounds_after_swap),
            replaced_agent_id=cross_run.replaced_agent_id,
            replacement_model=None,
            replacement_provider=None,
            imported_model=cross_run.imported_model,
            imported_provider=cross_run.imported_provider,
            source_b_run_id=cross_run.source_b_run_id,
            source_b_round_end=cross_run.source_b_round_end,
        )

    replace = read_replace_manifest(run_dir=run_dir)
    if replace is None:
        return None
    derivation_type: DerivationType = "replace_agent"
    if replace.replaced_agent_id is None:
        derivation_type = "fork_at_round"
    return DerivationFields(
        derivation_type=derivation_type,
        after_round=boundary_round_of(entry_round=replace.round_start),
        rounds_after=rounds_after_of(stored_window=replace.rounds_after_swap),
        replaced_agent_id=replace.replaced_agent_id,
        replacement_model=replace.replacement_model,
        replacement_provider=replace.replacement_provider,
        imported_model=None,
        imported_provider=None,
        source_b_run_id=None,
        source_b_round_end=None,
    )
