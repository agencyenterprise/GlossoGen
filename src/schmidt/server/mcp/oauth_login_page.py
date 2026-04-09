"""Minimal HTML login page for the OAuth authorization flow.

Renders a password form that carries the OAuth parameters as hidden fields.
On successful authentication the user is redirected to the client's
``redirect_uri`` with an authorization code appended.
"""

import hmac
import logging

from mcp.server.auth.provider import AuthorizationParams, construct_redirect_uri
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

logger = logging.getLogger(__name__)


async def _get_login(request: Request) -> Response:
    """Render the login form with OAuth params preserved as hidden fields."""
    params = request.query_params
    error_msg = params.get("error", "")
    html = _LOGIN_HTML.replace("{{error}}", _escape(error_msg))
    for field in _HIDDEN_FIELDS:
        html = html.replace(f"{{{{{field}}}}}", _escape(params.get(field, "")))
    return HTMLResponse(content=html)


async def _post_login(request: Request) -> Response:
    """Validate the password, issue an auth code, and redirect to the client."""
    form = await request.form()
    password = str(form.get("password", ""))
    provider = request.app.state.oauth_provider

    if provider._app_password is None or not hmac.compare_digest(password, provider._app_password):
        return RedirectResponse(
            url=construct_redirect_uri(
                str(request.url_for("oauth_login")),
                error="Invalid password",
                client_id=str(form.get("client_id", "")),
                redirect_uri=str(form.get("redirect_uri", "")),
                redirect_uri_provided_explicitly=str(
                    form.get("redirect_uri_provided_explicitly", "")
                ),
                code_challenge=str(form.get("code_challenge", "")),
                state=str(form.get("state", "")),
                scope=str(form.get("scope", "")),
                resource=str(form.get("resource", "")),
            ),
            status_code=303,
        )

    client_id = str(form.get("client_id", ""))
    scope_str = str(form.get("scope", ""))
    scopes = scope_str.split() if scope_str else []
    state = str(form.get("state", "")) if form.get("state") else None
    resource = str(form.get("resource", "")) if form.get("resource") else None

    redirect_uri_explicit_raw = str(form.get("redirect_uri_provided_explicitly", "1"))
    params = AuthorizationParams(
        state=state,
        scopes=scopes,
        code_challenge=str(form.get("code_challenge", "")),
        redirect_uri=AnyUrl(str(form.get("redirect_uri", ""))),
        redirect_uri_provided_explicitly=bool(int(redirect_uri_explicit_raw)),
        resource=resource,
    )

    code = await provider.create_authorization_code_for_login(
        client_id=client_id,
        params=params,
    )

    redirect_target = construct_redirect_uri(
        str(params.redirect_uri),
        code=code.code,
        state=params.state,
    )
    logger.info("OAuth login success for client %s — redirecting", client_id)
    return RedirectResponse(url=redirect_target, status_code=303)


def create_login_routes() -> list[Route]:
    """Create Starlette routes for the OAuth login page."""
    return [
        Route("/mcp/oauth/login", endpoint=_get_login, methods=["GET"], name="oauth_login"),
        Route("/mcp/oauth/login", endpoint=_post_login, methods=["POST"]),
    ]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_HIDDEN_FIELDS = [
    "client_id",
    "redirect_uri",
    "redirect_uri_provided_explicitly",
    "code_challenge",
    "state",
    "scope",
    "resource",
]


def _escape(value: str) -> str:
    """Minimal HTML escaping for attribute values."""
    return (
        value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )


# ------------------------------------------------------------------
# HTML template
# ------------------------------------------------------------------

_LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Schmidt — MCP Authorization</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0a0a0a; color: #e5e5e5;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; padding: 1rem;
  }
  .card {
    background: #171717; border: 1px solid #262626; border-radius: 12px;
    padding: 2rem; width: 100%; max-width: 400px;
  }
  h1 { font-size: 1.125rem; font-weight: 600; margin-bottom: 0.25rem; }
  .subtitle { font-size: 0.8125rem; color: #a3a3a3; margin-bottom: 1.5rem; }
  label { display: block; font-size: 0.8125rem; color: #a3a3a3; margin-bottom: 0.375rem; }
  input[type="password"] {
    width: 100%; padding: 0.5rem 0.75rem; font-size: 0.875rem;
    background: #0a0a0a; border: 1px solid #333; border-radius: 6px;
    color: #e5e5e5; outline: none;
  }
  input[type="password"]:focus { border-color: #555; }
  button {
    width: 100%; margin-top: 1rem; padding: 0.5rem; font-size: 0.875rem;
    font-weight: 500; background: #e5e5e5; color: #0a0a0a;
    border: none; border-radius: 6px; cursor: pointer;
  }
  button:hover { background: #d4d4d4; }
  .error { color: #ef4444; font-size: 0.8125rem; margin-bottom: 1rem; }
</style>
</head>
<body>
<div class="card">
  <h1>Authorize MCP Client</h1>
  <p class="subtitle">Enter the server password to grant access.</p>
  <div class="error">{{error}}</div>
  <form method="POST">
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autofocus required>
    <input type="hidden" name="client_id" value="{{client_id}}">
    <input type="hidden" name="redirect_uri" value="{{redirect_uri}}">
    <input type="hidden" name="redirect_uri_provided_explicitly"
           value="{{redirect_uri_provided_explicitly}}">
    <input type="hidden" name="code_challenge" value="{{code_challenge}}">
    <input type="hidden" name="state" value="{{state}}">
    <input type="hidden" name="scope" value="{{scope}}">
    <input type="hidden" name="resource" value="{{resource}}">
    <button type="submit">Authorize</button>
  </form>
</div>
</body>
</html>
"""
