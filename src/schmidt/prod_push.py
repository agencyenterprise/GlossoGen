"""Bulk push of local run bundles to a remote schmidt server.

Backs the ``schmidt push-to-prod`` subcommand. Walks ``--runs-dir``,
filters by label + scenario + report-present, diffs against the remote's
``/api/g/{slug}/runs`` listing, then POSTs each missing run's bundle to
``/api/g/{slug}/runs/import`` using the OAuth Bearer token loaded from
``~/.schmidt/credentials.json``.

The remote bundle-import endpoint is idempotent on ``run_id`` and the
remote ``_rename_to_original_timestamp`` step preserves the source
timestamp, so re-running this script is safe.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx

from schmidt.oauth_client import Credentials, load_or_refresh_credentials
from schmidt.server.runs.bundle_router import build_bundle_bytes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PushSpec:
    """Resolved filter + target for one ``schmidt push-to-prod`` invocation."""

    runs_dir: Path
    labels: frozenset[str]
    scenarios: frozenset[str] | None
    require_report: bool
    dry_run: bool
    concurrency: int


@dataclass(frozen=True)
class _LocalRun:
    """A local run dir that matches the push filter, ready for upload."""

    run_id: str
    scenario_name: str
    run_dir_name: str
    run_dir: Path


@dataclass(frozen=True)
class PushTally:
    """Per-invocation outcome reported back to the CLI driver."""

    uploaded: list[str]
    skipped: list[str]
    failed: list[tuple[str, str]]


_TRANSIENT_STATUS = frozenset({500, 502, 503, 504})
_RETRY_BASE_DELAY_SECONDS = 2.0
_MAX_RETRIES = 3
_HTTP_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=30.0)


def _load_labels(run_dir: Path) -> list[str] | None:
    """Return the label list from ``labels.json`` or ``None`` if missing/invalid."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return None
    try:
        raw = json.loads(labels_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, list):
        return None
    raw_list = cast(list[object], raw)
    result: list[str] = []
    for value in raw_list:
        if not isinstance(value, str):
            return None
        result.append(value)
    return result


def collect_local_runs(*, spec: PushSpec) -> list[_LocalRun]:
    """Walk the local runs directory and return everything matching the spec.

    Filter precedence: scenario allowlist (if set) → label-set
    superset → optional report-present check. Returns runs sorted by
    ``run_id``.
    """
    results: list[_LocalRun] = []
    if not spec.runs_dir.is_dir():
        return results
    for scenario_dir in spec.runs_dir.iterdir():
        if not scenario_dir.is_dir():
            continue
        scenario_name = scenario_dir.name
        if scenario_name.startswith("_"):
            continue
        if spec.scenarios is not None and scenario_name not in spec.scenarios:
            continue
        report_filename = f"{scenario_name}_report.json"
        for run_dir in scenario_dir.iterdir():
            if not run_dir.is_dir():
                continue
            labels = _load_labels(run_dir=run_dir)
            if labels is None:
                continue
            label_set = set(labels)
            if not spec.labels.issubset(label_set):
                continue
            if spec.require_report and not (run_dir / report_filename).exists():
                continue
            results.append(
                _LocalRun(
                    run_id=f"{scenario_name}/{run_dir.name}",
                    scenario_name=scenario_name,
                    run_dir_name=run_dir.name,
                    run_dir=run_dir,
                )
            )
    results.sort(key=lambda r: r.run_id)
    return results


async def fetch_remote_run_ids(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
) -> set[str]:
    """Pull every run_id already present on the remote for the active group.

    The remote ``/runs`` endpoint paginates at 50 rows per page by default,
    so this walks pages until ``len(seen) >= total`` to gather every id.
    """
    seen: set[str] = set()
    offset = 0
    page_size = 500
    while True:
        response = await client.get(
            url=f"{credentials.issuer_url}/api/g/{credentials.group_slug}/runs",
            params={"offset": offset, "limit": page_size},
            headers={"Authorization": f"Bearer {credentials.access_token}"},
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        page = payload["runs"]
        seen.update(entry["run_id"] for entry in page)
        total = payload["total"]
        if len(seen) >= total or not page:
            break
        offset += len(page)
    return seen


def _make_bundle(*, run: _LocalRun) -> bytes:
    """Build the tar.gz bundle for a local run (sync, runs in a worker thread)."""
    original_timestamp = int(run.run_dir_name.split("_")[0])
    return build_bundle_bytes(
        run.run_dir,
        run.run_id,
        run.scenario_name,
        original_timestamp,
    )


async def _post_bundle(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    run: _LocalRun,
    bundle_bytes: bytes,
) -> dict[str, object]:
    """POST a built bundle to the remote import endpoint and return the JSON body."""
    filename = f"{run.scenario_name}_{run.run_dir_name}_bundle.tar.gz"
    response = await client.post(
        url=f"{credentials.issuer_url}/api/g/{credentials.group_slug}/runs/import",
        headers={"Authorization": f"Bearer {credentials.access_token}"},
        files={"file": (filename, bundle_bytes, "application/gzip")},
        timeout=_HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


async def _upload_with_retry(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    run: _LocalRun,
) -> dict[str, object]:
    """Build + POST a bundle, retrying transient errors up to ``_MAX_RETRIES`` times."""
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            bundle_bytes = await asyncio.to_thread(_make_bundle, run=run)
            return await _post_bundle(
                client=client,
                credentials=credentials,
                run=run,
                bundle_bytes=bundle_bytes,
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403, 422):
                raise
            if status not in _TRANSIENT_STATUS:
                raise
            last_error = exc
        except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as exc:
            last_error = exc
        if attempt < _MAX_RETRIES:
            delay = _RETRY_BASE_DELAY_SECONDS * attempt
            logger.warning(
                "Transient error on %s (attempt %d/%d): %s — retrying in %.1fs",
                run.run_id,
                attempt,
                _MAX_RETRIES,
                last_error,
                delay,
            )
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error


async def _push_one(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    run: _LocalRun,
    semaphore: asyncio.Semaphore,
    position: int,
    total: int,
    tally: PushTally,
) -> None:
    """Upload a single run under the concurrency semaphore and update the tally."""
    async with semaphore:
        try:
            result = await _upload_with_retry(
                client=client,
                credentials=credentials,
                run=run,
            )
        except Exception as exc:
            logger.exception("[%d/%d] failed %s", position, total, run.run_id)
            tally.failed.append((run.run_id, str(exc)))
            return
        logger.info(
            "[%d/%d] uploaded %s -> %s",
            position,
            total,
            run.run_id,
            result.get("run_dir"),
        )
        tally.uploaded.append(run.run_id)


async def run_push_to_prod(*, spec: PushSpec) -> PushTally:
    """Drive the full discover → diff → upload flow.

    Returns a :class:`PushTally` summarizing what happened so the CLI
    driver can print it and exit with an appropriate code.
    """
    credentials = await load_or_refresh_credentials()

    local = collect_local_runs(spec=spec)
    logger.info(
        "Local matches: %d (labels=%s, require_report=%s)",
        len(local),
        sorted(spec.labels) or "<any>",
        spec.require_report,
    )

    tally = PushTally(uploaded=[], skipped=[], failed=[])
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        remote_ids = await fetch_remote_run_ids(client=client, credentials=credentials)
        logger.info("Remote already has: %d runs", len(remote_ids))

        to_upload: list[_LocalRun] = []
        for run in local:
            if run.run_id in remote_ids:
                tally.skipped.append(run.run_id)
            else:
                to_upload.append(run)

        logger.info("To upload: %d  (skipped: %d)", len(to_upload), len(tally.skipped))

        if spec.dry_run:
            for run in to_upload:
                logger.info("[dry-run] would upload %s", run.run_id)
            return tally

        semaphore = asyncio.Semaphore(spec.concurrency)
        tasks = [
            _push_one(
                client=client,
                credentials=credentials,
                run=run,
                semaphore=semaphore,
                position=position,
                total=len(to_upload),
                tally=tally,
            )
            for position, run in enumerate(to_upload, start=1)
        ]
        await asyncio.gather(*tasks)

    logger.info(
        "Finished. uploaded=%d skipped=%d failed=%d",
        len(tally.uploaded),
        len(tally.skipped),
        len(tally.failed),
    )
    if tally.failed:
        for run_id, err in tally.failed:
            logger.error("FAILED %s — %s", run_id, err)
    return tally
