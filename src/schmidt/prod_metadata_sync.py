"""Bulk sync of local run metadata (labels) to a remote schmidt server.

Backs the ``schmidt sync-metadata-to-prod`` subcommand. Walks ``--runs-dir``,
filters by scenario + report-present (same predicate as ``push-to-prod``),
diffs each run's local ``labels.json`` against the labels the remote already
holds, and PUTs the local list onto ``/api/g/{slug}/runs/{scenario}/{run_dir_name}/labels``
for every drifted run.

The PUT is a full replace — local is the source of truth. Runs that are
missing from the remote entirely are ignored here; ``push-to-prod`` is the
right tool for those.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx

from schmidt.oauth_client import Credentials, load_or_refresh_credentials
from schmidt.prod_push import HTTP_TIMEOUT, PushSpec, collect_local_runs

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS = frozenset({500, 502, 503, 504})
_RETRY_BASE_DELAY_SECONDS = 2.0
_MAX_RETRIES = 3
_PAGE_SIZE = 500


@dataclass(frozen=True)
class MetadataSyncSpec:
    """Resolved filter + target for one ``schmidt sync-metadata-to-prod`` call."""

    runs_dir: Path
    scenarios: frozenset[str] | None
    dry_run: bool
    concurrency: int


@dataclass(frozen=True)
class MetadataSyncTally:
    """Per-invocation outcome reported back to the CLI driver."""

    synced: list[str]
    failed: list[tuple[str, str]]


def _local_labels(run_dir: Path) -> list[str]:
    """Return the label list from ``labels.json`` or ``[]`` if missing/invalid."""
    path = run_dir / "labels.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    raw_list = cast(list[object], raw)
    out: list[str] = []
    for value in raw_list:
        if not isinstance(value, str):
            return []
        out.append(value)
    return out


async def fetch_remote_run_labels(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
) -> dict[str, list[str]]:
    """Return ``{run_id: labels}`` for every run the remote group owns.

    Uses the same ``/runs`` listing endpoint as ``push-to-prod`` but keeps
    the ``labels`` field so the caller can compute per-run drift without
    a second round-trip.
    """
    out: dict[str, list[str]] = {}
    offset = 0
    while True:
        response = await client.get(
            url=f"{credentials.issuer_url}/api/g/{credentials.group_slug}/runs",
            params={"offset": offset, "limit": _PAGE_SIZE},
            headers={"Authorization": f"Bearer {credentials.access_token}"},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        page = payload["runs"]
        for entry in page:
            out[entry["run_id"]] = entry["labels"]
        total = payload["total"]
        if len(out) >= total or not page:
            break
        offset += len(page)
    return out


async def _put_labels(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    scenario: str,
    run_dir_name: str,
    labels: list[str],
) -> None:
    """PUT a full label list, retrying transient errors up to ``_MAX_RETRIES``."""
    url = (
        f"{credentials.issuer_url}/api/g/{credentials.group_slug}"
        f"/runs/{scenario}/{run_dir_name}/labels"
    )
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = await client.put(
                url=url,
                headers={"Authorization": f"Bearer {credentials.access_token}"},
                json={"labels": labels},
                timeout=HTTP_TIMEOUT,
            )
            if response.status_code in _TRANSIENT_STATUS:
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
            else:
                response.raise_for_status()
                return
        except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as exc:
            last_error = exc
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_BASE_DELAY_SECONDS * attempt)
    assert last_error is not None
    raise last_error


async def _sync_one(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    scenario: str,
    run_dir_name: str,
    run_id: str,
    new_labels: list[str],
    semaphore: asyncio.Semaphore,
    position: int,
    total: int,
    tally: MetadataSyncTally,
) -> None:
    """PUT a single run's labels under the concurrency semaphore."""
    async with semaphore:
        try:
            await _put_labels(
                client=client,
                credentials=credentials,
                scenario=scenario,
                run_dir_name=run_dir_name,
                labels=new_labels,
            )
        except Exception as exc:
            logger.exception("[%d/%d] failed %s", position, total, run_id)
            tally.failed.append((run_id, str(exc)))
            return
        logger.info("[%d/%d] synced %s -> %s", position, total, run_id, new_labels)
        tally.synced.append(run_id)


async def run_metadata_sync(*, spec: MetadataSyncSpec) -> MetadataSyncTally:
    """Drive the full discover → diff → PUT flow for label sync.

    Returns a :class:`MetadataSyncTally` summarizing what happened so the
    CLI driver can print it and exit with an appropriate code.
    """
    credentials = await load_or_refresh_credentials()

    push_spec = PushSpec(
        runs_dir=spec.runs_dir,
        labels=frozenset(),
        scenarios=spec.scenarios,
        require_report=True,
        dry_run=False,
        concurrency=1,
    )
    local = collect_local_runs(spec=push_spec)
    logger.info("Local eligible: %d", len(local))

    tally = MetadataSyncTally(synced=[], failed=[])
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        remote = await fetch_remote_run_labels(client=client, credentials=credentials)
        logger.info("Remote total: %d", len(remote))

        drift: list[tuple[str, str, str, list[str]]] = []
        for run in local:
            remote_labels = remote.get(run.run_id)
            if remote_labels is None:
                continue
            local_lbl = _local_labels(run_dir=run.run_dir)
            if sorted(local_lbl) != sorted(remote_labels):
                drift.append((run.run_id, run.scenario_name, run.run_dir_name, local_lbl))

        logger.info("Label drift: %d", len(drift))

        if spec.dry_run:
            for run_id, _, _, new_labels in drift:
                logger.info("[dry-run] would PUT %s -> %s", run_id, new_labels)
            return tally

        semaphore = asyncio.Semaphore(spec.concurrency)
        tasks = [
            _sync_one(
                client=client,
                credentials=credentials,
                scenario=scenario,
                run_dir_name=run_dir_name,
                run_id=run_id,
                new_labels=new_labels,
                semaphore=semaphore,
                position=position,
                total=len(drift),
                tally=tally,
            )
            for position, (run_id, scenario, run_dir_name, new_labels) in enumerate(drift, start=1)
        ]
        await asyncio.gather(*tasks)

    logger.info("Finished. synced=%d failed=%d", len(tally.synced), len(tally.failed))
    if tally.failed:
        for run_id, err in tally.failed:
            logger.error("FAILED %s — %s", run_id, err)
    return tally
