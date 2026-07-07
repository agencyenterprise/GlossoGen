"""Clerk webhook receiver: keeps the local ``groups`` table in sync with Clerk orgs.

Signature verification uses ``svix`` (the underlying provider for Clerk
webhooks). Only ``organization.*`` events are acted on; membership events are
accepted and ignored because session JWTs already carry membership claims.
"""

import logging
import os
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from svix.webhooks import Webhook, WebhookVerificationError

from glossogen.db.pool import DbPool
from glossogen.db.queries import soft_delete_group_by_clerk_org_id, upsert_group

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clerk", tags=["clerk"])


class WebhookAccepted(BaseModel):
    """Response payload returned for every accepted Clerk webhook."""

    accepted: bool
    event_type: str


def _get_pool(request: Request) -> DbPool:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool not initialized",
        )
    return pool


def _get_webhook_secret() -> str:
    secret = os.environ.get("CLERK_WEBHOOK_SECRET")
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CLERK_WEBHOOK_SECRET is not configured",
        )
    return secret


def _verify_signature(secret: str, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
    """Verify Svix signature and return the parsed payload."""
    webhook = Webhook(secret)
    try:
        payload = webhook.verify(body, headers)
    except WebhookVerificationError as exc:
        logger.warning("Clerk webhook signature verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Svix signature",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clerk webhook payload is not a JSON object",
        )
    return cast(dict[str, Any], payload)


def _extract_org_fields(data: dict[str, Any]) -> tuple[str, str, str]:
    """Pull ``id``, ``slug``, ``name`` from a Clerk ``organization.*`` event body."""
    org_id = data.get("id")
    slug = data.get("slug")
    name = data.get("name")
    if not isinstance(org_id, str) or not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization event missing id",
        )
    if not isinstance(slug, str) or not slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization event missing slug",
        )
    if not isinstance(name, str) or not name:
        name = slug
    return org_id, slug, name


@router.post("/webhook", response_model=WebhookAccepted)
async def receive_webhook(request: Request) -> WebhookAccepted:
    """Receive and act on a Clerk webhook event.

    Returns 200 even for ignored event types so Clerk does not retry them.
    """
    secret = _get_webhook_secret()
    body = await request.body()
    payload = _verify_signature(
        secret=secret,
        body=body,
        headers={key: value for key, value in request.headers.items()},
    )

    raw_event_type = payload.get("type")
    if not isinstance(raw_event_type, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clerk webhook payload missing 'type'",
        )
    event_type = raw_event_type
    raw_data = payload.get("data")
    if not isinstance(raw_data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clerk webhook payload missing 'data' object",
        )
    data = cast(dict[str, Any], raw_data)

    pool = _get_pool(request=request)

    if event_type in {"organization.created", "organization.updated"}:
        clerk_org_id, slug, name = _extract_org_fields(data=data)
        async with pool.connection() as conn:
            group = await upsert_group(
                conn=conn,
                clerk_org_id=clerk_org_id,
                slug=slug,
                name=name,
            )
        logger.info(
            "Clerk webhook %s applied: clerk_org_id=%s group_id=%s slug=%s",
            event_type,
            clerk_org_id,
            group.id,
            group.slug,
        )
    elif event_type == "organization.deleted":
        clerk_org_id_value = data.get("id")
        if not isinstance(clerk_org_id_value, str) or not clerk_org_id_value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="organization.deleted event missing id",
            )
        async with pool.connection() as conn:
            await soft_delete_group_by_clerk_org_id(
                conn=conn,
                clerk_org_id=clerk_org_id_value,
            )
        logger.info(
            "Clerk webhook organization.deleted applied: clerk_org_id=%s",
            clerk_org_id_value,
        )
    else:
        logger.debug("Clerk webhook %s acknowledged but ignored", event_type)

    return WebhookAccepted(accepted=True, event_type=event_type)
