"""Reads a remote server's paginated ``/runs`` listing for the prod sync commands.

``push-to-prod`` and ``sync-metadata-to-prod`` both diff local runs against
the remote group's listing. Each page is validated against
:class:`RemoteRunPage`, which names only the fields those commands read, so a
page missing one of them is refused instead of read as an empty value. The
server's full ``RunSummary`` is not used here: the CLI and the remote can run
different versions, and a field neither command reads should not fail a sync.
"""

import httpx
from pydantic import BaseModel

from glossogen.oauth_client import Credentials


class RemoteRunEntry(BaseModel):
    """One run in the remote listing, reduced to the fields the sync commands read.

    ``evaluation_content_hash`` is required and may be null: null means the
    remote holds no evaluation for the run, while a missing key is a page this
    client does not understand.
    """

    run_id: str
    labels: list[str]
    evaluation_content_hash: str | None


class RemoteRunPage(BaseModel):
    """One keyset page of the remote ``/runs`` listing."""

    runs: list[RemoteRunEntry]
    next_cursor: str | None


async def fetch_remote_runs(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    page_size: int,
    timeout: httpx.Timeout,
) -> list[RemoteRunEntry]:
    """Return every run the remote group owns, walking the keyset-paginated listing.

    Each response carries the ``next_cursor`` to send back for the following
    page; a null cursor or an empty page ends the walk.
    """
    entries: list[RemoteRunEntry] = []
    cursor: str | None = None
    while True:
        params: dict[str, str | int] = {"limit": page_size}
        if cursor is not None:
            params["cursor"] = cursor
        response = await client.get(
            url=f"{credentials.issuer_url}/api/g/{credentials.group_slug}/runs",
            params=params,
            headers={"Authorization": f"Bearer {credentials.access_token}"},
            timeout=timeout,
        )
        response.raise_for_status()
        page = RemoteRunPage.model_validate_json(response.content)
        entries.extend(page.runs)
        cursor = page.next_cursor
        if cursor is None or not page.runs:
            break
    return entries
