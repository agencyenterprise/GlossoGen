# pyright: reportPrivateUsage=false

"""Validation and idempotency of run-bundle imports."""

import gzip
import io
import tarfile
from collections.abc import Iterator
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
from glossogen.server.runs.bundle_tar_limits import (
    MAX_BUNDLE_EXTENDED_HEADER_BYTES,
    MAX_BUNDLE_MEMBER_COUNT,
    BundleTarFile,
)
from glossogen.server.runs.models import BundleManifest

SCENARIO = "veyru"
ORIGIN_RUN_ID = f"{SCENARIO}/1770000100"


class _TarWithMembers:
    def __init__(self, members: list[tarfile.TarInfo]) -> None:
        self._members = members

    def __iter__(self) -> Iterator[tarfile.TarInfo]:
        return iter(self._members)


class _TrackingFile(io.BytesIO):
    def __init__(self, initial_bytes: bytes) -> None:
        super().__init__(initial_bytes)
        self.read_sizes: list[int | None] = []

    def read(self, size: int | None = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def _started(*, scenario_name: str) -> SimulationStarted:
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
        _started(scenario_name=SCENARIO).model_dump_json().encode()
        + b"\n"
        + ended.model_dump_json().encode()
        + b"\n"
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
    manifest_scenario_name: str,
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
    bundle = _bundle_with_event(
        _started(scenario_name="another_scenario"),
        manifest_scenario_name=SCENARIO,
    )

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


def _bundle_of_empty_members(count: int) -> bytes:
    """A gzipped tar of ``count`` identical empty-file headers, a few bytes each once
    compressed."""
    header = tarfile.TarInfo(name="empty").tobuf(format=tarfile.USTAR_FORMAT)
    return gzip.compress(header * count + bytes(1024))


async def test_a_bundle_with_more_members_than_the_ceiling_is_refused(tmp_path: Path) -> None:
    bundle = _bundle_of_empty_members(count=MAX_BUNDLE_MEMBER_COUNT + 1)

    with pytest.raises(HTTPException) as refusal:
        await import_run_bundle(
            file=UploadFile(file=io.BytesIO(bundle), filename="run.tar.gz"),
            request=_request(runs_dir=tmp_path / "runs"),
        )

    assert refusal.value.status_code == 413
    assert str(MAX_BUNDLE_MEMBER_COUNT) in str(refusal.value.detail)


def test_member_validation_stops_reading_at_the_ceiling() -> None:
    # Each member read is held in memory, so the refusal has to come before the
    # archive is read to its end, not after.
    bundle = _bundle_of_empty_members(count=MAX_BUNDLE_MEMBER_COUNT * 2)

    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tar:
        with pytest.raises(ExportTooLargeError):
            _validate_tar_members(tar=tar)
        assert tar.offset == (MAX_BUNDLE_MEMBER_COUNT + 1) * tarfile.BLOCKSIZE


def _bundle_of_one_header(member_type: bytes, size: int) -> bytes:
    """A gzipped tar holding one header that declares ``size`` bytes, and no data.

    A refusal that comes from the declared size never reads the data, so none is
    written."""
    header = tarfile.TarInfo(name="member")
    header.type = member_type
    header.size = size
    return gzip.compress(header.tobuf(format=tarfile.GNU_FORMAT) + bytes(1024))


async def _import_status(bundle: bytes, runs_dir: Path) -> HTTPException:
    with pytest.raises(HTTPException) as refusal:
        await import_run_bundle(
            file=UploadFile(file=io.BytesIO(bundle), filename="run.tar.gz"),
            request=_request(runs_dir=runs_dir),
        )
    return refusal.value


@pytest.mark.parametrize(
    "member_type", [tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK, tarfile.XHDTYPE]
)
async def test_an_extended_header_past_the_budget_is_refused_before_it_is_read(
    tmp_path: Path, member_type: bytes
) -> None:
    # tarfile reads these headers whole into memory, and gzip lets a small upload
    # declare gigabytes of one.
    bundle = _bundle_of_one_header(
        member_type=member_type, size=MAX_BUNDLE_EXTENDED_HEADER_BYTES + 1
    )

    refusal = await _import_status(bundle=bundle, runs_dir=tmp_path / "runs")

    assert refusal.status_code == 413
    assert "extended headers" in str(refusal.detail)


@pytest.mark.parametrize("member_type", [tarfile.XGLTYPE, tarfile.GNUTYPE_SPARSE])
async def test_a_header_type_a_bundle_never_carries_is_refused(
    tmp_path: Path, member_type: bytes
) -> None:
    refusal = await _import_status(
        bundle=_bundle_of_one_header(member_type=member_type, size=0),
        runs_dir=tmp_path / "runs",
    )

    assert refusal.status_code == 422
    assert "Unsupported" in str(refusal.detail)


async def test_a_pax_declared_sparse_map_is_refused(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        member = tarfile.TarInfo(name="sparse")
        member.pax_headers = {"GNU.sparse.major": "1", "GNU.sparse.minor": "0"}
        tar.addfile(member, io.BytesIO(b""))

    refusal = await _import_status(bundle=buffer.getvalue(), runs_dir=tmp_path / "runs")

    assert refusal.status_code == 422
    assert "sparse" in str(refusal.detail)


async def test_a_member_of_unknown_type_counts_toward_the_size_ceiling(tmp_path: Path) -> None:
    # tarfile decompresses and skips an unknown member's data, so its size costs the
    # server as much as a regular file's would.
    bundle = _bundle_of_one_header(member_type=b"Z", size=MAX_RAW_EXPORT_BYTES + 1)

    refusal = await _import_status(bundle=bundle, runs_dir=tmp_path / "runs")

    assert refusal.status_code == 413


async def test_a_chain_of_empty_extended_headers_is_refused_as_invalid(tmp_path: Path) -> None:
    # Each zero-size pax header costs nothing against the byte budget, and tarfile
    # recurses once per header, so a short chain ends in a RecursionError.
    header = tarfile.TarInfo(name="x")
    header.type = tarfile.XHDTYPE
    chain = header.tobuf(format=tarfile.GNU_FORMAT) * 500
    member = tarfile.TarInfo(name="f").tobuf(format=tarfile.USTAR_FORMAT)
    bundle = gzip.compress(chain + member + bytes(1024))

    refusal = await _import_status(bundle=bundle, runs_dir=tmp_path / "runs")

    assert refusal.status_code == 422


def test_a_bundle_with_long_names_and_long_links_still_reads() -> None:
    # A GNU-format writer puts a long link and a long name before one member.
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        for index in range(3):
            member = tarfile.TarInfo(name=f"{'d' * 120}/{index}")
            member.type = tarfile.SYMTYPE
            member.linkname = "l" * 120
            tar.addfile(member)
    buffer.seek(0)

    with BundleTarFile.open(fileobj=buffer, mode="r:gz") as tar:
        _validate_tar_members(tar=tar)
        assert len(tar.getnames()) == 3
