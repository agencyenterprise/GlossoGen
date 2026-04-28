"""Schema and reader for ``replace_manifest.json``.

Lives outside ``replace_agent.py`` so evaluators can read the manifest
without pulling in the scenario registry (which ``replace_agent`` needs
to launch a resumed simulation).
"""

from pathlib import Path

from pydantic import BaseModel

REPLACE_MANIFEST_FILENAME = "replace_manifest.json"


class ReplaceManifest(BaseModel):
    """Persisted record of a replace-agent operation.

    Written once at replace-agent time into ``replace_manifest.json`` inside
    the new run directory. The resume code path, evaluators, and inspection
    scripts read it to reconstruct what the replacement saw and which rounds
    were played after the swap.
    """

    source_run_id: str
    source_run_dir: str
    round_start: int
    rounds_after_swap: int
    target_message_id: str
    replaced_agent_id: str
    replacement_model: str
    replacement_provider: str
    channels_with_visible_history: list[str]
    blocked_tool_call_channels: list[str]
    replaced_at: float


def read_replace_manifest(run_dir: Path) -> ReplaceManifest | None:
    """Load ``replace_manifest.json`` from ``run_dir`` or return ``None`` if absent."""
    manifest_path = run_dir / REPLACE_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    return ReplaceManifest.model_validate_json(manifest_path.read_bytes())
