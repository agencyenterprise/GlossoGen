"""Bulk sync of local run metadata (labels + evaluation report) to a remote.

Backs the ``glossogen sync-metadata-to-prod`` subcommand. Walks ``--runs-dir``,
filters by scenario + report-present (same predicate as ``push-to-prod``),
and for every local run that already exists on the remote:

* PUTs the local labels onto ``/runs/{scenario}/{run_dir_name}/labels``
  when the lists differ.
* PUTs the local evaluation report onto
  ``/runs/{scenario}/{run_dir_name}/evaluation`` when the local
  ``compute_measurements_hash`` differs from the remote's cached
  ``evaluation_content_hash`` (from the paginated ``/runs`` listing).

Runs that are missing from the remote entirely are ignored here;
``push-to-prod`` is the right tool for those.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, cast

import httpx

from glossogen.evaluation.reports.evaluation_report import compute_measurements_hash, load_report
from glossogen.oauth_client import Credentials, load_or_refresh_credentials
from glossogen.prod_push import HTTP_TIMEOUT, LocalRun, PushSpec, collect_local_runs

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS = frozenset({500, 502, 503, 504})
_RETRY_BASE_DELAY_SECONDS = 2.0
_MAX_RETRIES = 3
_PAGE_SIZE = 500


class RemoteMetadata(NamedTuple):
    """Sync-relevant fields returned by the paginated ``/runs`` list endpoint."""

    labels: list[str]
    evaluation_content_hash: str | None


@dataclass(frozen=True)
class MetadataSyncSpec:
    """Resolved filter + target for one ``glossogen sync-metadata-to-prod`` call."""

    runs_dir: Path
    scenarios: frozenset[str] | None
    dry_run: bool
    concurrency: int


@dataclass
class MetadataSyncTally:
    """Per-invocation outcome reported back to the CLI driver.

    ``synced_labels``: runs where a labels PUT fired.
    ``synced_eval``: runs where an eval PUT fired (hash mismatch or no
    remote hash).
    ``unchanged``: runs already on prod with matching labels + eval hash.
    ``failed``: (run_id, error) pairs.
    """

    synced_labels: list[str] = field(default_factory=lambda: [])
    synced_eval: list[str] = field(default_factory=lambda: [])
    unchanged: list[str] = field(default_factory=lambda: [])
    failed: list[tuple[str, str]] = field(default_factory=lambda: [])


class _SyncPlan(NamedTuple):
    """Per-run decision derived from local vs. remote diff."""

    run_id: str
    scenario_name: str
    run_dir_name: str
    run_dir: Path
    new_labels: list[str] | None
    push_eval: bool
    eval_reason: str


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


async def fetch_remote_run_metadata(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
) -> dict[str, RemoteMetadata]:
    """Return ``{run_id: RemoteMetadata}`` for every run the remote group owns.

    Uses the same ``/runs`` listing endpoint as ``push-to-prod`` but keeps
    both ``labels`` and ``evaluation_content_hash`` so per-run drift can be
    computed locally without a second round-trip.
    """
    out: dict[str, RemoteMetadata] = {}
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
            out[entry["run_id"]] = RemoteMetadata(
                labels=entry["labels"],
                evaluation_content_hash=entry.get("evaluation_content_hash"),
            )
        total = payload["total"]
        if len(out) >= total or not page:
            break
        offset += len(page)
    return out


async def _local_report_hash(*, run_dir: Path, scenario: str) -> str | None:
    """Return the digest of the local report's measurements, or ``None`` if absent."""
    report = await load_report(report_path=run_dir / f"{scenario}_report.json")
    if report is None:
        return None
    return compute_measurements_hash(measurements=report.measurements)


async def _put_with_retry(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    suffix: str,
    json_body: dict[str, object],
) -> None:
    """PUT a JSON body to ``{group base}/{suffix}``, retrying transient errors."""
    url = f"{credentials.issuer_url}/api/g/{credentials.group_slug}{suffix}"
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = await client.put(
                url=url,
                headers={"Authorization": f"Bearer {credentials.access_token}"},
                json=json_body,
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


async def _put_labels(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    scenario: str,
    run_dir_name: str,
    labels: list[str],
) -> None:
    """PUT a full label list, retrying transient errors up to ``_MAX_RETRIES``."""
    await _put_with_retry(
        client=client,
        credentials=credentials,
        suffix=f"/runs/{scenario}/{run_dir_name}/labels",
        json_body={"labels": labels},
    )


async def _put_evaluation(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    scenario: str,
    run_dir_name: str,
    run_dir: Path,
) -> bool:
    """Load the local evaluation report and PUT it onto the remote run.

    Returns ``False`` (silently) when no local report exists. The PUT body
    is the full ``EvaluationReport`` JSON; the remote endpoint replaces
    its on-disk copy and updates its ``evaluation_content_hash`` row.
    """
    report = await load_report(report_path=run_dir / f"{scenario}_report.json")
    if report is None:
        return False
    await _put_with_retry(
        client=client,
        credentials=credentials,
        suffix=f"/runs/{scenario}/{run_dir_name}/evaluation",
        json_body=report.model_dump(mode="json"),
    )
    return True


async def _sync_one(
    *,
    client: httpx.AsyncClient,
    credentials: Credentials,
    plan: _SyncPlan,
    semaphore: asyncio.Semaphore,
    position: int,
    total: int,
    tally: MetadataSyncTally,
) -> None:
    """PUT labels (when drifted) + evaluation report (when drifted) for one run."""
    async with semaphore:
        try:
            if plan.new_labels is not None:
                await _put_labels(
                    client=client,
                    credentials=credentials,
                    scenario=plan.scenario_name,
                    run_dir_name=plan.run_dir_name,
                    labels=plan.new_labels,
                )
            if plan.push_eval:
                await _put_evaluation(
                    client=client,
                    credentials=credentials,
                    scenario=plan.scenario_name,
                    run_dir_name=plan.run_dir_name,
                    run_dir=plan.run_dir,
                )
        except Exception as exc:
            logger.exception("[%d/%d] failed %s", position, total, plan.run_id)
            tally.failed.append((plan.run_id, str(exc)))
            return
        if plan.new_labels is not None:
            logger.info(
                "[%d/%d] synced %s labels=%s",
                position,
                total,
                plan.run_id,
                plan.new_labels,
            )
            tally.synced_labels.append(plan.run_id)
        if plan.push_eval:
            logger.info(
                "[%d/%d] synced %s eval (%s)",
                position,
                total,
                plan.run_id,
                plan.eval_reason,
            )
            tally.synced_eval.append(plan.run_id)


def _plan_run_sync(
    *,
    run_id: str,
    scenario_name: str,
    run_dir_name: str,
    run_dir: Path,
    local_labels: list[str],
    local_hash: str | None,
    remote: RemoteMetadata,
) -> _SyncPlan:
    """Decide labels + eval PUTs for one run from the local + remote diff."""
    new_labels: list[str] | None
    if sorted(local_labels) != sorted(remote.labels):
        new_labels = local_labels
    else:
        new_labels = None

    push_eval = False
    eval_reason = "unchanged"
    if local_hash is None:
        # Nothing to push (no local report) — treat as unchanged.
        pass
    elif remote.evaluation_content_hash is None:
        push_eval = True
        eval_reason = "no-remote-hash"
    elif remote.evaluation_content_hash != local_hash:
        push_eval = True
        eval_reason = "drifted"

    return _SyncPlan(
        run_id=run_id,
        scenario_name=scenario_name,
        run_dir_name=run_dir_name,
        run_dir=run_dir,
        new_labels=new_labels,
        push_eval=push_eval,
        eval_reason=eval_reason,
    )


async def _build_plans(
    *,
    local: list[LocalRun],
    remote: dict[str, RemoteMetadata],
) -> list[_SyncPlan]:
    """Build one ``_SyncPlan`` per local run that also exists on remote."""
    plans: list[_SyncPlan] = []
    for run in local:
        remote_meta = remote.get(run.run_id)
        if remote_meta is None:
            continue
        local_hash = await _local_report_hash(
            run_dir=run.run_dir,
            scenario=run.scenario_name,
        )
        plans.append(
            _plan_run_sync(
                run_id=run.run_id,
                scenario_name=run.scenario_name,
                run_dir_name=run.run_dir_name,
                run_dir=run.run_dir,
                local_labels=_local_labels(run_dir=run.run_dir),
                local_hash=local_hash,
                remote=remote_meta,
            )
        )
    return plans


async def run_metadata_sync(*, spec: MetadataSyncSpec) -> MetadataSyncTally:
    """Drive the full discover → diff → PUT flow for metadata sync.

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

    tally = MetadataSyncTally()
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        remote = await fetch_remote_run_metadata(client=client, credentials=credentials)
        logger.info("Remote total: %d", len(remote))

        plans = await _build_plans(local=local, remote=remote)

        label_drift = sum(1 for p in plans if p.new_labels is not None)
        eval_drift = sum(1 for p in plans if p.push_eval and p.eval_reason == "drifted")
        eval_missing_hash = sum(1 for p in plans if p.eval_reason == "no-remote-hash")
        unchanged = sum(1 for p in plans if p.new_labels is None and not p.push_eval)
        logger.info(
            "On-prod targets: %d (label-drift: %d, eval-drift: %d, "
            "eval-no-remote-hash: %d, unchanged: %d)",
            len(plans),
            label_drift,
            eval_drift,
            eval_missing_hash,
            unchanged,
        )

        if spec.dry_run:
            for plan in plans:
                if plan.new_labels is None and not plan.push_eval:
                    logger.info("[dry-run] %s unchanged", plan.run_id)
                    tally.unchanged.append(plan.run_id)
                    continue
                actions: list[str] = []
                if plan.new_labels is not None:
                    actions.append(f"labels={plan.new_labels}")
                if plan.push_eval:
                    actions.append(f"eval ({plan.eval_reason})")
                logger.info("[dry-run] %s %s", plan.run_id, " + ".join(actions))
            return tally

        for plan in plans:
            if plan.new_labels is None and not plan.push_eval:
                tally.unchanged.append(plan.run_id)

        actionable = [p for p in plans if p.new_labels is not None or p.push_eval]
        semaphore = asyncio.Semaphore(spec.concurrency)
        tasks = [
            _sync_one(
                client=client,
                credentials=credentials,
                plan=plan,
                semaphore=semaphore,
                position=position,
                total=len(actionable),
                tally=tally,
            )
            for position, plan in enumerate(actionable, start=1)
        ]
        await asyncio.gather(*tasks)

    logger.info(
        "Finished. labels=%d eval=%d unchanged=%d failed=%d",
        len(tally.synced_labels),
        len(tally.synced_eval),
        len(tally.unchanged),
        len(tally.failed),
    )
    if tally.failed:
        for run_id, err in tally.failed:
            logger.error("FAILED %s — %s", run_id, err)
    return tally
