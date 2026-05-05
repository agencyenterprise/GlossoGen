"""Schema and reader for ``cross_run_replace_manifest.json``.

A cross-run replace-agent operation imports one agent — with its full
pydantic-ai history — from a different completed run (Sim B) into a
target run (Sim A) at a chosen round boundary. The manifest captures
the provenance of both runs and the parameters needed to reconstruct
the imported agent's history on resume.

Lives outside ``cross_run_replace_agent.py`` so evaluators and the
discovery layer can read the manifest without pulling in the scenario
registry.
"""

from pathlib import Path

from pydantic import BaseModel

CROSS_RUN_REPLACE_MANIFEST_FILENAME = "cross_run_replace_manifest.json"
IMPORTED_HISTORY_SOURCE_FILENAME = "imported_history_source.jsonl"


class CrossRunReplaceManifest(BaseModel):
    """Persisted record of a cross-run replace-agent operation.

    Written once at cross-run-replace time into
    ``cross_run_replace_manifest.json`` inside the new run directory.
    The resume code path, evaluators, and inspection scripts read it to
    reconstruct what the imported agent saw and which rounds were played
    after the swap.

    ``source_a_run_id`` / ``source_a_run_dir`` describe the *target* run
    (the timeline being modified). ``source_b_run_id`` /
    ``source_b_run_dir`` describe the run the imported agent comes from.
    ``imported_history_source`` is the relative path inside the new run
    dir of the verbatim copy of Sim B's JSONL used to rebuild the
    imported agent's pydantic-ai history.

    ``source_b_round_end`` is the last round of Sim B whose events feed
    into the imported agent's history. ``source_b_cutoff_event_id`` is
    the ``RoundAdvanced`` event for ``source_b_round_end + 1`` in Sim B,
    or the empty string when Sim B never advanced past
    ``source_b_round_end`` (in which case the cutoff is Sim B's last
    event timestamp).
    """

    source_a_run_id: str
    source_a_run_dir: str
    source_b_run_id: str
    source_b_run_dir: str
    imported_history_source: str
    round_start: int
    rounds_after_swap: int
    target_event_id: str
    source_b_round_end: int
    source_b_cutoff_event_id: str
    replaced_agent_id: str
    imported_model: str
    imported_provider: str
    channels_with_visible_history: list[str]
    blocked_tool_call_channels: list[str]
    replaced_at: float


def read_cross_run_replace_manifest(run_dir: Path) -> CrossRunReplaceManifest | None:
    """Load ``cross_run_replace_manifest.json`` from ``run_dir`` or return ``None``."""
    manifest_path = run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    return CrossRunReplaceManifest.model_validate_json(manifest_path.read_bytes())
