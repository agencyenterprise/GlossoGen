"""The derivation-provenance readers validate each manifest instead of filling in missing fields."""

from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from pydantic import ValidationError

from glossogen.server.runs.manifest_sources import (
    FORK_MANIFEST_FILENAME,
    read_derivation_fields,
    read_fork_source,
    read_replace_agent_source,
)
from tests.fakes.replace_manifests import write_replace_manifest


def test_a_fork_manifest_projects_onto_its_source(tmp_path: Path) -> None:
    (tmp_path / FORK_MANIFEST_FILENAME).write_bytes(
        orjson.dumps(
            {"source_run_id": "veyru/1", "target_message_id": "m-9", "forked_at": 1_780_000_000.0}
        )
    )

    source = read_fork_source(run_dir=tmp_path)

    assert source is not None
    assert source.source_run_id == "veyru/1"
    assert source.target_message_id == "m-9"
    assert source.forked_at == datetime.fromtimestamp(1_780_000_000.0, tz=UTC)


def test_a_fork_manifest_missing_a_field_is_refused(tmp_path: Path) -> None:
    (tmp_path / FORK_MANIFEST_FILENAME).write_bytes(
        orjson.dumps({"source_run_id": "veyru/1", "forked_at": 1_780_000_000.0})
    )

    with pytest.raises(ValidationError, match="target_message_id"):
        read_fork_source(run_dir=tmp_path)


def test_a_replace_manifest_naming_a_seat_without_its_replacement_is_refused(
    tmp_path: Path,
) -> None:
    write_replace_manifest(
        run_dir=tmp_path,
        round_start=5,
        rounds_after_swap=3,
        target_event_id="evt-a",
        replaced_agent_id="field_observer",
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        channel_history_floors={},
    )

    with pytest.raises(ValueError, match="without a replacement model and provider"):
        read_replace_agent_source(run_dir=tmp_path)


def test_a_replace_manifest_with_no_seat_is_a_fork_at_round(tmp_path: Path) -> None:
    write_replace_manifest(
        run_dir=tmp_path,
        round_start=5,
        rounds_after_swap=3,
        target_event_id="evt-a",
        replaced_agent_id=None,
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        channel_history_floors={},
    )

    fields = read_derivation_fields(run_dir=tmp_path)

    assert fields is not None
    assert fields.derivation_type == "fork_at_round"
    assert fields.after_round == 4
    assert fields.rounds_after == 4
    assert read_replace_agent_source(run_dir=tmp_path) is None
