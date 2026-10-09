# pyright: reportPrivateUsage=false

"""Validation and idempotency of run-bundle imports."""

import io
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import orjson
import pytest
from fastapi import HTTPException, Request, UploadFile

from glossogen.db.local_tenant import LOCAL_GROUP_ID
from glossogen.models.event import RunStatus, SimulationEnded, SimulationStarted
from glossogen.run_export.export_limits import MAX_RAW_EXPORT_BYTES, ExportTooLargeError
from glossogen.server.identity.identity_model import Identity
from glossogen.server.runs.bundle_router import (
    _validate_tar_members,
    build_bundle_bytes,
    import_run_bundle,
)
from glossogen.server.runs.models import BundleManifest

SCENARIO = "veyru"
ORIGIN_RUN_ID = f"{SCENARIO}/1770000100"


class _TarWithMembers:
    def __init__(self, members: list[tarfile.TarInfo]) -> None:
        self._members = members

    def getmembers(self) -> list[tarfile.TarInfo]:
        return self._members


class _TrackingFile(io.BytesIO):
    def __init__(self, initial_bytes: bytes) -> None:
        super().__init__(initial_bytes)
        self.read_sizes: list[int | None] = []

    def read(self, size: int | None = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def _started(*, scenario_name: str = SCENARIO) -> SimulationStarted:
    return SimulationStarted(
        run_id=ORIGIN_RUN_ID,
        scenario_name=scenario_name,
        scenario_description="",
        channel_ids=["link"],
        scenario_config={},
        provider="anthropic",
        round_number=0,
    )


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    ended = SimulationEnded(
        reason=RunStatus.SCENARIO_COMPLETE,
        total_messages=0,
        total_cost_usd=0.0,
        round_number=0,
    )
    (run_dir / f"{SCENARIO}.jsonl").write_bytes(
        _started().model_dump_json().encode() + b"\n" + ended.model_dump_json().encode() + b"\n"
    )


def _request(runs_dir: Path) -> Request:
    app = SimpleNamespace(state=SimpleNamespace(runs_dir=runs_dir, db_pool=None))
    request = Request(scope={"type": "http", "method": "POST", "headers": [], "app": app})
    request.state.identity = Identity(
        user_id="local-user", active_group_id=LOCAL_GROUP_ID, is_local_mode=True
    )
    return request


def _bundle_with_event(
    event: SimulationStarted,
    *,
    manifest_scenario_name: str = SCENARIO,
) -> bytes:
    buffer = io.BytesIO()
    manifest = BundleManifest(
        run_id=event.run_id,
        scenario_name=manifest_scenario_name,
        exported_at=datetime.now(tz=UTC),
        original_timestamp=1770000100,
    )
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        event_bytes = event.model_dump_json().encode() + b"\n"
        event_info = tarfile.TarInfo(name=f"{manifest_scenario_name}.jsonl")
        event_info.size = len(event_bytes)
        tar.addfile(event_info, io.BytesIO(event_bytes))

        manifest_bytes = orjson.dumps(manifest.model_dump(mode="json"))
        manifest_info = tarfile.TarInfo(name="bundle_manifest.json")
        manifest_info.size = len(manifest_bytes)
        tar.addfile(manifest_info, io.BytesIO(manifest_bytes))
    return buffer.getvalue()


async def test_reimport_finds_a_run_renamed_after_a_timestamp_collision(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    renamed_dir = runs_dir / SCENARIO / "1770000101"
    _write_run(run_dir=renamed_dir)
    bundle = build_bundle_bytes(
        run_dir=renamed_dir,
        run_id=ORIGIN_RUN_ID,
        scenario_name=SCENARIO,
        original_timestamp=1770000100,
    )
    source = _TrackingFile(bundle)

    response = await import_run_bundle(
        file=UploadFile(file=source, filename="run.tar.gz"),
        request=_request(runs_dir=runs_dir),
    )

    assert response.run_id == ORIGIN_RUN_ID
    assert response.run_dir == str(renamed_dir)
    assert not (runs_dir / SCENARIO / "1770000100").exists()
    assert source.read_sizes[0] == 1


async def test_a_manifest_scenario_must_match_the_jsonl_event(tmp_path: Path) -> None:
    bundle = _bundle_with_event(_started(scenario_name="another_scenario"))

    with pytest.raises(HTTPException) as refusal:
        await import_run_bundle(
            file=UploadFile(file=io.BytesIO(bundle), filename="run.tar.gz"),
            request=_request(runs_dir=tmp_path / "runs"),
        )

    assert refusal.value.status_code == 422
    assert "records 'another_scenario'" in str(refusal.value.detail)


async def test_a_manifest_scenario_must_be_a_safe_scenario_name(tmp_path: Path) -> None:
    bundle = _bundle_with_event(
        _started(scenario_name=".."),
        manifest_scenario_name="..",
    )

    with pytest.raises(HTTPException) as refusal:
        await import_run_bundle(
            file=UploadFile(file=io.BytesIO(bundle), filename="run.tar.gz"),
            request=_request(runs_dir=tmp_path / "runs"),
        )

    assert refusal.value.status_code == 422
    assert "Invalid scenario name" in str(refusal.value.detail)


async def test_a_traversal_member_is_reported_as_an_invalid_bundle(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        tar.addfile(tarfile.TarInfo(name="../outside"))

    with pytest.raises(HTTPException) as refusal:
        await import_run_bundle(
            file=UploadFile(file=io.BytesIO(buffer.getvalue()), filename="run.tar.gz"),
            request=_request(runs_dir=tmp_path / "runs"),
        )

    assert refusal.value.status_code == 422
    assert "traversal" in str(refusal.value.detail)


def test_a_bundle_cannot_declare_more_than_the_raw_export_ceiling() -> None:
    oversized = tarfile.TarInfo(name="large.bin")
    oversized.size = MAX_RAW_EXPORT_BYTES + 1
    tar = cast(tarfile.TarFile, cast(object, _TarWithMembers([oversized])))

    with pytest.raises(ExportTooLargeError):
        _validate_tar_members(tar=tar)
