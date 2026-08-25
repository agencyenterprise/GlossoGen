"""FastAPI router for the group's label glossary.

A description belongs to a group and is addressed by the exact label string. The label
travels in the request body (or a query parameter for delete) rather than in the path,
because labels like ``src=veyru/1777638061`` carry path separators.

``GET /labels`` stays what it is, the union of labels the group's runs carry; this
router answers what those labels mean. A description for a label no run carries yet is
allowed, so a glossary entry can be written before the first run is labelled.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from glossogen.label_descriptions.label_description_models import (
    LabelDescription,
    LabelDescriptionsResponse,
)
from glossogen.label_descriptions.label_description_store_resolution import (
    label_description_store_for,
)
from glossogen.server.runs.lookup import get_identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


@router.get("/labels/descriptions", response_model=LabelDescriptionsResponse)
async def list_label_descriptions(request: Request) -> LabelDescriptionsResponse:
    """List the group's label descriptions, sorted by label."""
    identity = get_identity(request=request)
    store = label_description_store_for(request=request)
    descriptions = await store.list_descriptions(group_id=identity.active_group_id)
    return LabelDescriptionsResponse(descriptions=descriptions)


@router.put("/labels/descriptions", response_model=LabelDescription)
async def set_label_description(body: LabelDescription, request: Request) -> LabelDescription:
    """Record what a label means, replacing any previous description of it."""
    identity = get_identity(request=request)
    store = label_description_store_for(request=request)
    await store.set_description(group_id=identity.active_group_id, entry=body)
    logger.info("Described label %r (%d chars)", body.label, len(body.description))
    return body


@router.delete("/labels/descriptions", status_code=204)
async def delete_label_description(
    label: Annotated[str, Query(min_length=1)],
    request: Request,
) -> Response:
    """Remove a label's description."""
    identity = get_identity(request=request)
    store = label_description_store_for(request=request)
    deleted = await store.delete_description(group_id=identity.active_group_id, label=label)
    if not deleted:
        raise HTTPException(status_code=404, detail="No description recorded for that label.")
    logger.info("Deleted the description of label %r", label)
    return Response(status_code=204)
