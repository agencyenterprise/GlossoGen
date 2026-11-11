# pyright: reportPrivateUsage=false

"""How ``push-to-prod`` uploads one run's bundle and reads the import endpoint's reply.

The reply is read with :class:`ImportedBundleReceipt`, not the server's
``ImportBundleResponse``, so these tests serve a body built from the server's model:
if the server's reply stops carrying a field the receipt needs, they fail.
"""

import gzip
import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from glossogen.oauth_client import Credentials
from glossogen.prod_sync.prod_push import ImportedBundleReceipt, LocalRun, _upload_with_retry
from glossogen.server.runs.models import ImportBundleResponse

_IMPORT_PATH = "/api/g/ae-group/runs/import"


def _credentials() -> Credentials:
    return Credentials(
        issuer_url="https://prod.example",
        group_slug="ae-group",
        client_id="client",
        client_secret=None,
        access_token="token",
        refresh_token=None,
        expires_at=datetime(2100, 1, 1, tzinfo=UTC),
    )


def _local_run(runs_dir: Path) -> LocalRun:
    run_dir = runs_dir / "veyru" / "1770000100"
    run_dir.mkdir(parents=True)
    (run_dir / "veyru.jsonl").write_text('{"event_type": "simulation_started"}\n')
    (run_dir / "veyru_debug.jsonl").write_text("{}\n")
    (run_dir / "labels.json").write_text('["baseline"]')
    return LocalRun(
        run_id="veyru/1770000100",
        scenario_name="veyru",
        run_dir_name="1770000100",
        run_dir=run_dir,
        labels=["baseline"],
    )


def _uploaded_bundle(request: httpx.Request) -> tarfile.TarFile:
    """The tar inside the multipart body of an import request."""
    body = request.content
    start = body.index(b"\x1f\x8b")
    end = body.rindex(b"\r\n--")
    return tarfile.open(fileobj=io.BytesIO(gzip.decompress(body[start:end])))


async def test_the_server_reply_is_read_into_the_receipt(tmp_path: Path) -> None:
    run = _local_run(runs_dir=tmp_path)
    requests: list[httpx.Request] = []
    server_reply = ImportBundleResponse(
        run_id=run.run_id,
        scenario_name=run.scenario_name,
        run_dir="/srv/runs/veyru/1770000100",
    )

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code=200, content=server_reply.model_dump_json())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler=handle)) as client:
        receipt = await _upload_with_retry(client=client, credentials=_credentials(), run=run)

    assert receipt == ImportedBundleReceipt(
        run_id="veyru/1770000100",
        run_dir="/srv/runs/veyru/1770000100",
    )
    [request] = requests
    assert request.method == "POST"
    assert request.url.path == _IMPORT_PATH
    assert request.headers["Authorization"] == "Bearer token"
    with _uploaded_bundle(request=request) as tar:
        names = sorted(tar.getnames())
        manifest_file = tar.extractfile("bundle_manifest.json")
        assert manifest_file is not None
        manifest = json.loads(manifest_file.read())
    assert names == ["bundle_manifest.json", "labels.json", "veyru.jsonl"]
    assert (manifest["run_id"], manifest["original_timestamp"]) == ("veyru/1770000100", 1770000100)


async def test_a_reply_with_fields_this_client_does_not_read_is_accepted(tmp_path: Path) -> None:
    run = _local_run(runs_dir=tmp_path)

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _IMPORT_PATH
        return httpx.Response(
            status_code=200,
            json={"run_id": run.run_id, "run_dir": "/srv/runs/x", "added_later": 1},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler=handle)) as client:
        receipt = await _upload_with_retry(client=client, credentials=_credentials(), run=run)

    assert receipt.run_dir == "/srv/runs/x"


async def test_a_reply_missing_the_run_dir_is_refused(tmp_path: Path) -> None:
    run = _local_run(runs_dir=tmp_path)

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _IMPORT_PATH
        return httpx.Response(status_code=200, json={"run_id": run.run_id})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler=handle)) as client:
        with pytest.raises(ValidationError):
            await _upload_with_retry(client=client, credentials=_credentials(), run=run)
