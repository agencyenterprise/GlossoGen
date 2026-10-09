"""The prod sync commands read the remote ``/runs`` listing through one validated page shape."""

from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from glossogen.oauth_client import Credentials
from glossogen.prod_metadata_sync import fetch_remote_run_metadata
from glossogen.prod_push import fetch_remote_run_ids


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


def _client_serving(pages: dict[str | None, dict[str, object]]) -> httpx.AsyncClient:
    """A client whose ``/runs`` answers the page keyed by the request's cursor."""

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/g/ae-group/runs"
        return httpx.Response(status_code=200, json=pages[request.url.params.get("cursor")])

    return httpx.AsyncClient(transport=httpx.MockTransport(handler=handle))


def _entry(run_id: str, evaluation_content_hash: str | None) -> dict[str, object]:
    return {
        "run_id": run_id,
        "labels": ["baseline"],
        "evaluation_content_hash": evaluation_content_hash,
        "total_cost_usd": 1.5,
    }


async def test_every_page_is_read_until_the_cursor_runs_out() -> None:
    pages: dict[str | None, dict[str, object]] = {
        None: {
            "runs": [_entry(run_id="veyru/1", evaluation_content_hash="h1")],
            "next_cursor": "c2",
        },
        "c2": {
            "runs": [_entry(run_id="veyru/2", evaluation_content_hash=None)],
            "next_cursor": None,
        },
    }
    async with _client_serving(pages=pages) as client:
        metadata = await fetch_remote_run_metadata(client=client, credentials=_credentials())
        run_ids = await fetch_remote_run_ids(client=client, credentials=_credentials())

    assert run_ids == {"veyru/1", "veyru/2"}
    assert metadata["veyru/1"].evaluation_content_hash == "h1"
    assert metadata["veyru/2"].evaluation_content_hash is None
    assert metadata["veyru/2"].labels == ["baseline"]


async def test_a_page_missing_the_evaluation_hash_is_refused() -> None:
    """A missing key is not read as "no remote evaluation", which would re-push every report."""
    entry = _entry(run_id="veyru/1", evaluation_content_hash="h1")
    del entry["evaluation_content_hash"]
    pages: dict[str | None, dict[str, object]] = {None: {"runs": [entry], "next_cursor": None}}

    async with _client_serving(pages=pages) as client:
        with pytest.raises(ValidationError, match="evaluation_content_hash"):
            await fetch_remote_run_metadata(client=client, credentials=_credentials())
