"""``GET /mcp/consent-request/{request_id}``: who a parked MCP consent request is for.

Client registration is open to anyone, so the consent page cannot assume the request
came from a client the user knows. It reads this route to show the client's name and
the redirect URI the authorization code will be sent to, before the user approves.

Provider-agnostic, and unauthenticated like the rest of ``/mcp``: the request id is an
unguessable token that only the page the authorizing client sent the user to holds, and
the answer repeats what that client registered and asked for.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp")


class ConsentRequestResponse(BaseModel):
    """Response for ``GET /mcp/consent-request/{request_id}``.

    ``client_name`` is chosen by whoever registered the client. ``redirect_uri`` is
    where the authorization code goes once the request is approved.
    """

    client_name: str | None
    redirect_uri: str
    scopes: list[str]


@router.get(
    "/consent-request/{request_id}",
    response_model=ConsentRequestResponse,
)
async def describe_consent_request(request: Request, request_id: str) -> ConsentRequestResponse:
    """Return the client name, redirect URI and scopes of a parked consent request.

    404 when the request expired, was already approved, or its client is gone.
    """
    oauth_provider = getattr(request.app.state, "oauth_provider", None)
    if oauth_provider is None:
        raise HTTPException(status_code=503, detail="MCP OAuth is not configured")

    description = await oauth_provider.describe_pending_consent(request_id=request_id)
    if description is None:
        raise HTTPException(
            status_code=404,
            detail="Consent request expired, already used, or its client is gone",
        )
    return ConsentRequestResponse(
        client_name=description.client_name,
        redirect_uri=description.redirect_uri,
        scopes=description.scopes,
    )
