"""Schema and reader for ``replace_manifest.json``.

Lives outside ``replace_agent.py`` so evaluators can read the manifest
without pulling in the scenario registry (which ``replace_agent`` needs
to launch a resumed simulation).
"""

from pathlib import Path

from pydantic import BaseModel, Field

REPLACE_MANIFEST_FILENAME = "replace_manifest.json"


class ReplaceManifest(BaseModel):
    """Persisted record of a replace-agent or round-anchored resume operation.

    Written once at operation time into ``replace_manifest.json`` inside
    the new run directory. The resume code path, evaluators, and inspection
    scripts read it to reconstruct what the replacement saw and which rounds
    were played after the swap.

    ``replaced_agent_id`` is ``None`` for a round-anchored resume — every
    agent keeps its full reconstructed history and no model/provider override
    is applied. ``replacement_model`` and ``replacement_provider`` are ``None``
    in the same case, and ``channels_with_visible_history`` /
    ``blocked_tool_call_channels`` are empty lists.

    ``channel_history_floors`` maps a channel id to a round floor for
    windowed history: the replaced agent sees that channel's messages
    only from the floor round onward (``ChannelVisibilityFromRound``).
    Channels absent from this map but present in
    ``channels_with_visible_history`` keep their full prior history.
    Defaults to empty so manifests written before windowing existed
    still load.
    """

    source_run_id: str
    source_run_dir: str
    round_start: int
    rounds_after_swap: int
    target_event_id: str
    replaced_agent_id: str | None
    replacement_model: str | None
    replacement_provider: str | None
    channels_with_visible_history: list[str]
    blocked_tool_call_channels: list[str]
    channel_history_floors: dict[str, int] = Field(default_factory=dict)
    replaced_at: float


def read_replace_manifest(run_dir: Path) -> ReplaceManifest | None:
    """Load ``replace_manifest.json`` from ``run_dir`` or return ``None`` if absent."""
    manifest_path = run_dir / REPLACE_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    return ReplaceManifest.model_validate_json(manifest_path.read_bytes())
