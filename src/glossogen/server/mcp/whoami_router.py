"""``GET /mcp/whoami``: the group bound to the calling OAuth access token.

Provider-agnostic. The token was minted by the platform's own OAuth provider, so
answering needs no identity provider at all, and ``glossogen whoami`` works whether
or not one is installed.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from glossogen.db.local_tenant import LOCAL_GROUP_SLUG
from glossogen.db.queries import get_group_by_id
from glossogen.server.identity.bearer_credential import bearer_from_header

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp")


class WhoAmIResponse(BaseModel):
    """Response for ``GET /mcp/whoami``: the group bound to the calling OAuth token."""

    group_id: str
    group_slug: str


@router.get(
    "/whoami",
    response_model=WhoAmIResponse,
)
async def whoami(request: Request) -> WhoAmIResponse:
    """Return the group bound to the calling OAuth access token.

    Lets the CLI learn its ``group_slug`` after the OAuth exchange so it can store it
    in ``~/.glossogen/credentials.json`` and address per-group REST endpoints without
    prompting the user.
    """
    token = bearer_from_header(request=request)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    oauth_provider = getattr(request.app.state, "oauth_provider", None)
    if oauth_provider is None:
        raise HTTPException(status_code=503, detail="MCP OAuth is not configured")

    group_id = await oauth_provider.load_access_token_with_group(token=token)
    if group_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    pool = request.app.state.db_pool
    if pool is None:
        # No-database single-tenant mode: every token is bound to the local group.
        return WhoAmIResponse(group_id=str(group_id), group_slug=LOCAL_GROUP_SLUG)

    async with pool.connection() as conn:
        group = await get_group_by_id(conn=conn, group_id=group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Token bound to unknown group")

    return WhoAmIResponse(group_id=str(group.id), group_slug=group.slug)
