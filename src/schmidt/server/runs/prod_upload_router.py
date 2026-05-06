"""FastAPI router for uploading a single local run to a configured prod server.

Reads ``PROD_API_URL`` and ``PROD_PASSWORD`` from the application state.
The feature is disabled (``configured=False``) when either is unset.
"""

import asyncio
import logging
from pathlib import Path

import aiofiles
import httpx
import orjson
from fastapi import APIRouter, HTTPException, Request

from schmidt.evaluation.evaluation_report import EvaluationReport, load_report
from schmidt.server.runs.bundle_router import build_bundle_bytes
from schmidt.server.runs.discovery import compose_run_id, resolve_run
from schmidt.server.runs.models import (
    ProdUploadOutcome,
    ProdUploadResponse,
    ProdUploadStatusResponse,
    SyncMetadataResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_REQUEST_TIMEOUT_SECONDS = 600.0


def _read_prod_credentials(request: Request) -> tuple[str, str]:
    prod_url: str | None = getattr(request.app.state, "prod_api_url", None)
    prod_password: str | None = getattr(request.app.state, "prod_password", None)
    if not prod_url or not prod_password:
        raise HTTPException(
            status_code=503,
            detail="Prod upload is not configured (set PROD_API_URL and PROD_PASSWORD).",
        )
    return prod_url, prod_password


@router.get(
    "/prod-upload/status",
    response_model=ProdUploadStatusResponse,
)
async def prod_upload_status(request: Request) -> ProdUploadStatusResponse:
    """Report whether prod upload is configured on this server."""
    prod_url: str | None = getattr(request.app.state, "prod_api_url", None)
    prod_password: str | None = getattr(request.app.state, "prod_password", None)
    configured = bool(prod_url) and bool(prod_password)
    return ProdUploadStatusResponse(
        configured=configured,
        prod_url=prod_url if configured else None,
    )


async def _remote_run_exists(
    *,
    client: httpx.AsyncClient,
    prod_url: str,
    prod_password: str,
    scenario: str,
    run_dir_name: str,
) -> bool:
    """Return True when prod already has a run with this exact run_id."""
    response = await client.get(
        url=f"{prod_url}/api/runs/{scenario}/{run_dir_name}",
        headers={"Authorization": f"Bearer {prod_password}"},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True


async def _delete_remote_run(
    *,
    client: httpx.AsyncClient,
    prod_url: str,
    prod_password: str,
    scenario: str,
    run_dir_name: str,
) -> None:
    """Delete the run on prod. Treats 404 as success (already gone)."""
    response = await client.delete(
        url=f"{prod_url}/api/runs/{scenario}/{run_dir_name}",
        headers={"Authorization": f"Bearer {prod_password}"},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return
    response.raise_for_status()


async def _post_bundle(
    *,
    client: httpx.AsyncClient,
    prod_url: str,
    prod_password: str,
    run_id: str,
    bundle_bytes: bytes,
) -> None:
    scenario, run_dir_name = run_id.split("/", 1)
    filename = f"{scenario}_{run_dir_name}_bundle.tar.gz"
    response = await client.post(
        url=f"{prod_url}/api/runs/import",
        headers={"Authorization": f"Bearer {prod_password}"},
        files={"file": (filename, bundle_bytes, "application/gzip")},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


async def _build_bundle_for_run(*, runs_dir: Path, scenario: str, run_dir_name: str) -> bytes:
    resolved = resolve_run(
        runs_dir=runs_dir,
        scenario_name=scenario,
        run_dir_name=run_dir_name,
    )
    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)
    original_timestamp = int(resolved.run_dir.name.split("_")[0])
    return await asyncio.to_thread(
        build_bundle_bytes,
        resolved.run_dir,
        run_id,
        resolved.scenario_name,
        original_timestamp,
    )


@router.post(
    "/runs/{scenario}/{run_dir_name}/upload-to-prod",
    response_model=ProdUploadResponse,
)
async def upload_run_to_prod(
    scenario: str,
    run_dir_name: str,
    request: Request,
    force: bool = False,
) -> ProdUploadResponse:
    """Upload a single local run to the configured prod server.

    Default: returns ``already_present`` when prod already has the run; the
    bundle is neither rebuilt nor re-uploaded. Pass ``?force=true`` to
    delete the remote run first and re-upload, returning ``overridden``.
    """
    prod_url, prod_password = _read_prod_credentials(request=request)
    runs_dir: Path = request.app.state.runs_dir

    try:
        resolve_run(runs_dir=runs_dir, scenario_name=scenario, run_dir_name=run_dir_name)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")

    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)

    async with httpx.AsyncClient() as client:
        if not force:
            try:
                already_present = await _remote_run_exists(
                    client=client,
                    prod_url=prod_url,
                    prod_password=prod_password,
                    scenario=scenario,
                    run_dir_name=run_dir_name,
                )
            except Exception as exc:
                logger.exception("Failed to check prod for %s", run_id)
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to query prod server: {exc}",
                )

            if already_present:
                logger.info("Run %s already present on prod — skipping", run_id)
                return ProdUploadResponse(
                    run_id=run_id,
                    outcome=ProdUploadOutcome.ALREADY_PRESENT,
                )

        try:
            bundle_bytes = await _build_bundle_for_run(
                runs_dir=runs_dir,
                scenario=scenario,
                run_dir_name=run_dir_name,
            )
            if force:
                await _delete_remote_run(
                    client=client,
                    prod_url=prod_url,
                    prod_password=prod_password,
                    scenario=scenario,
                    run_dir_name=run_dir_name,
                )
            await _post_bundle(
                client=client,
                prod_url=prod_url,
                prod_password=prod_password,
                run_id=run_id,
                bundle_bytes=bundle_bytes,
            )
        except Exception as exc:
            logger.exception("Failed to upload %s to prod", run_id)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to upload to prod: {exc}",
            )

    outcome = ProdUploadOutcome.OVERRIDDEN if force else ProdUploadOutcome.UPLOADED
    logger.info(
        "%s %s to prod (%.2f MB)",
        "Overrode" if force else "Uploaded",
        run_id,
        len(bundle_bytes) / (1024 * 1024),
    )
    return ProdUploadResponse(run_id=run_id, outcome=outcome)


async def _read_local_metadata(
    *,
    run_dir: Path,
    scenario_name: str,
) -> tuple[list[str] | None, str | None, EvaluationReport | None]:
    """Read labels.json, note.md, <scenario>_report.json from the run dir."""
    labels: list[str] | None = None
    labels_path = run_dir / "labels.json"
    if labels_path.exists():
        async with aiofiles.open(labels_path, mode="rb") as f:
            labels = orjson.loads(await f.read())

    note: str | None = None
    note_path = run_dir / "note.md"
    if note_path.exists():
        async with aiofiles.open(note_path, mode="r", encoding="utf-8") as f:
            note = await f.read()

    report = await load_report(report_path=run_dir / f"{scenario_name}_report.json")

    return labels, note, report


@router.post(
    "/runs/{scenario}/{run_dir_name}/sync-metadata-to-prod",
    response_model=SyncMetadataResponse,
)
async def sync_run_metadata_to_prod(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> SyncMetadataResponse:
    """Read labels / note / eval report locally and PUT them onto the prod run.

    Returns 404 when prod does not have this run (caller should fall back
    to the full ``upload-to-prod`` flow). 503 when prod is not configured.
    """
    prod_url, prod_password = _read_prod_credentials(request=request)
    runs_dir: Path = request.app.state.runs_dir

    try:
        resolved = resolve_run(
            runs_dir=runs_dir,
            scenario_name=scenario,
            run_dir_name=run_dir_name,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Local run not found")

    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)

    labels, note, report = await _read_local_metadata(
        run_dir=resolved.run_dir,
        scenario_name=resolved.scenario_name,
    )

    payload = {
        "labels": labels,
        "note": note,
        "report": report.model_dump(mode="json") if report is not None else None,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(
                url=f"{prod_url}/api/runs/{scenario}/{run_dir_name}/metadata",
                headers={"Authorization": f"Bearer {prod_password}"},
                json=payload,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.exception("Failed to PUT metadata for %s to prod", run_id)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach prod server: {exc}",
            )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} is not on prod — upload the full bundle first.",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Prod metadata sync returned HTTP {response.status_code}: {response.text}",
        )

    data = response.json()
    return SyncMetadataResponse(
        run_id=data["run_id"],
        labels_written=bool(data["labels_written"]),
        note_written=bool(data["note_written"]),
        report_written=bool(data["report_written"]),
    )
