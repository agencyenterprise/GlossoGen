"""Writing ``replace_manifest.json`` files for tests.

One builder owns the full field literal, so a schema change to
``ReplaceManifest`` breaks one place and every suite keeps pinning the same
on-disk shape.
"""

from pathlib import Path

import orjson

from glossogen.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest


def write_replace_manifest(
    run_dir: Path,
    round_start: int,
    rounds_after_swap: int,
    target_event_id: str,
    replaced_agent_id: str | None,
    channels_with_visible_history: list[str],
    blocked_tool_call_channels: list[str],
    channel_history_floors: dict[str, int],
) -> None:
    """Write a manifest with the frozen on-disk field names into ``run_dir``."""
    manifest = ReplaceManifest(
        source_run_id="smoke/1",
        source_run_dir="/runs/smoke/1",
        round_start=round_start,
        rounds_after_swap=rounds_after_swap,
        target_event_id=target_event_id,
        replaced_agent_id=replaced_agent_id,
        replacement_model=None,
        replacement_provider=None,
        channels_with_visible_history=channels_with_visible_history,
        blocked_tool_call_channels=blocked_tool_call_channels,
        channel_history_floors=channel_history_floors,
        replaced_at=1_700_000_000.0,
    )
    (run_dir / REPLACE_MANIFEST_FILENAME).write_bytes(orjson.dumps(manifest.model_dump()))
