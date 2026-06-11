"""Clerk-gated approval endpoint for parked OAuth consent requests.

The MCP server's OAuth ``authorize`` endpoint cannot synchronously issue an
authorization code in Clerk mode — the user must first sign in via Clerk
on the frontend and pick which group they want to authorize. Backend's
:meth:`SchmidtOAuthProvider.authorize` parks the request and redirects to
``{frontend_url}/mcp-consent?request_id=...``; the frontend page (which
forces Clerk sign-in via the existing middleware) then POSTs back here
once the desired org is active on the Clerk session.

This router lives outside the main identity middleware (which is bypassed
for ``/mcp/*`` paths) and does its own Clerk JWT verification inline, so
the FE can hit it without the middleware's URL-slug match.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from schmidt.db.local_tenant import LOCAL_GROUP_SLUG
from schmidt.db.queries import get_group_by_id, get_group_by_slug
from schmidt.server.identity.clerk_verifier import InvalidClerkToken, verify_clerk_session_token
from schmidt.server.identity.settings import IdentitySettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp")


class ApproveConsentRequest(BaseModel):
    """Body for ``POST /mcp/consent/approve`` — the parked request to materialize."""

    model_config = ConfigDict(extra="forbid")

    request_id: str


class ApproveConsentResponse(BaseModel):
    """Response for ``POST /mcp/consent/approve`` — where the browser should go next."""

    redirect_url: str
    group_slug: str


class WhoAmIResponse(BaseModel):
    """Response for ``GET /mcp/whoami`` — group bound to the calling OAuth token."""

    group_id: str
    group_slug: str


def _bearer_token(request: Request) -> str | None:
    """Pull the JWT out of an ``Authorization: Bearer ...`` header."""
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer ") :].strip()
    if not token:
        return None
    return token


@router.post(
    "/consent/approve",
    response_model=ApproveConsentResponse,
)
async def approve_consent(
    request: Request,
    body: ApproveConsentRequest,
) -> ApproveConsentResponse:
    """Verify the caller's Clerk JWT and materialize the parked OAuth code.

    The group the token will be bound to is taken from the JWT's active
    ``org_slug`` claim (Clerk's ``organizationSyncOptions`` keeps that
    aligned with whichever org the user just selected on the FE).
    """
    identity_settings: IdentitySettings = request.app.state.identity_settings
    if identity_settings.is_local_mode:
        raise HTTPException(
            status_code=400,
            detail="Consent approval is only used in Clerk mode",
        )
    if identity_settings.clerk_jwt_key is None:
        raise HTTPException(
            status_code=503,
            detail="Server misconfigured: CLERK_JWT_KEY is not set",
        )

    token = _bearer_token(request=request)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        claims = verify_clerk_session_token(
            token=token,
            clerk_jwt_key=identity_settings.clerk_jwt_key,
            authorized_parties=identity_settings.clerk_authorized_parties,
        )
    except InvalidClerkToken as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if claims.org_slug is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Active Clerk org missing — pick a group on the consent page " "before approving"
            ),
        )

    async with request.app.state.db_pool.connection() as conn:
        group = await get_group_by_slug(conn=conn, slug=claims.org_slug)
    if group is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown group slug: {claims.org_slug!r}",
        )

    try:
        redirect_url = await request.app.state.oauth_provider.approve_pending_consent(
            request_id=body.request_id,
            group_id=group.id,
        )
    except Exception as exc:
        logger.exception("Failed to approve consent request %s", body.request_id)
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info(
        "MCP consent approved: client mint for group=%s by user=%s",
        group.slug,
        claims.user_id,
    )
    return ApproveConsentResponse(redirect_url=redirect_url, group_slug=group.slug)


@router.get(
    "/whoami",
    response_model=WhoAmIResponse,
)
async def whoami(request: Request) -> WhoAmIResponse:
    """Return the group bound to the calling OAuth access token.

    Lets the CLI learn its ``group_slug`` after the OAuth exchange so it
    can store it in ``~/.schmidt/credentials.json`` and address per-group
    REST endpoints without prompting the user.
    """
    token = _bearer_token(request=request)
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
        # No-database local mode: every token is bound to the local group.
        return WhoAmIResponse(group_id=str(group_id), group_slug=LOCAL_GROUP_SLUG)

    async with pool.connection() as conn:
        group = await get_group_by_id(conn=conn, group_id=group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Token bound to unknown group")

    return WhoAmIResponse(group_id=str(group.id), group_slug=group.slug)
