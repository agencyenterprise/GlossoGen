"""OAuth 2.0 PKCE client for ``glossogen login`` against a remote MCP server.

Drives the user through the discovery → registration → authorize →
exchange flow against a backend that exposes the MCP OAuth endpoints,
then persists the resulting tokens to ``~/.glossogen/credentials.json``.

Used by the ``login`` subcommand to acquire credentials and by
``push-to-prod`` to load + refresh them on each invocation.
"""

import asyncio
import base64
import hashlib
import http.server
import json
import logging
import secrets
import socket
import threading
import urllib.parse
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import httpx
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path.home() / ".glossogen" / "credentials.json"
_CALLBACK_PATH = "/callback"
_SUCCESS_HTML = b"""<!doctype html><html><body style="font-family:system-ui;padding:40px">
<h1>glossogen CLI authorized</h1>
<p>You can close this window and return to the terminal.</p>
</body></html>"""


class Credentials(BaseModel):
    """Local copy of an MCP OAuth grant."""

    model_config = ConfigDict(extra="forbid")

    issuer_url: str
    group_slug: str
    client_id: str
    client_secret: str | None
    access_token: str
    refresh_token: str | None
    expires_at: datetime

    def is_expired(self, *, leeway_seconds: int) -> bool:
        """Return True if the access token has less than ``leeway_seconds`` left."""
        return datetime.now(tz=UTC) >= self.expires_at - timedelta(seconds=leeway_seconds)


class OAuthMetadata(NamedTuple):
    """Subset of RFC 8414 authorization-server metadata the CLI cares about."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str


def _generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for an S256 PKCE exchange."""
    verifier_bytes = secrets.token_urlsafe(64)[:128].encode("ascii")
    verifier = verifier_bytes.decode("ascii")
    digest = hashlib.sha256(verifier_bytes).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def _fetch_metadata(*, client: httpx.AsyncClient, issuer_url: str) -> OAuthMetadata:
    """Fetch ``/.well-known/oauth-authorization-server`` from the issuer."""
    response = await client.get(
        url=f"{issuer_url.rstrip('/')}/.well-known/oauth-authorization-server",
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return OAuthMetadata(
        issuer=data["issuer"],
        authorization_endpoint=data["authorization_endpoint"],
        token_endpoint=data["token_endpoint"],
        registration_endpoint=data["registration_endpoint"],
    )


async def _register_client(
    *,
    client: httpx.AsyncClient,
    registration_endpoint: str,
    redirect_uri: str,
) -> tuple[str, str | None]:
    """Dynamically register an OAuth client. Returns ``(client_id, client_secret)``."""
    response = await client.post(
        url=registration_endpoint,
        json={
            "client_name": "glossogen CLI",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["client_id"], data.get("client_secret")


def _claim_loopback_port() -> int:
    """Reserve a free localhost port for the OAuth callback handler."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _CallbackState:
    """Mutable state shared between the loopback HTTP handler and the CLI loop."""

    def __init__(self) -> None:
        self.code: str | None = None
        self.state: str | None = None
        self.error: str | None = None
        self.event = threading.Event()


def _make_callback_handler(state: _CallbackState) -> type[http.server.BaseHTTPRequestHandler]:
    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != _CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            params = urllib.parse.parse_qs(parsed.query)
            state.code = (params.get("code") or [None])[0]
            state.state = (params.get("state") or [None])[0]
            state.error = (params.get("error") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_SUCCESS_HTML)
            state.event.set()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # Suppress the default per-request stderr noise.
            pass

    return CallbackHandler


def _wait_for_callback(*, port: int, timeout_seconds: float) -> _CallbackState:
    """Run the loopback server until the OAuth callback fires (or timeout)."""
    state = _CallbackState()
    handler = _make_callback_handler(state=state)
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not state.event.wait(timeout=timeout_seconds):
            raise TimeoutError(f"Did not receive OAuth callback within {timeout_seconds:.0f}s")
    finally:
        server.shutdown()
        server.server_close()
    return state


async def _exchange_code_for_tokens(
    *,
    client: httpx.AsyncClient,
    token_endpoint: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str | None,
) -> dict[str, object]:
    """POST the authorization code to ``token_endpoint`` and return the JSON payload."""
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret is not None:
        body["client_secret"] = client_secret
    response = await client.post(
        url=token_endpoint,
        data=body,
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


async def _refresh_access_token(
    *,
    client: httpx.AsyncClient,
    token_endpoint: str,
    refresh_token: str,
    client_id: str,
    client_secret: str | None,
) -> dict[str, object]:
    """Exchange a refresh token for a new access (+ refresh) token pair."""
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if client_secret is not None:
        body["client_secret"] = client_secret
    response = await client.post(
        url=token_endpoint,
        data=body,
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


async def _fetch_group_slug(
    *,
    client: httpx.AsyncClient,
    issuer_url: str,
    access_token: str,
) -> str:
    """Hit ``/mcp/whoami`` to learn the group bound to the access token."""
    response = await client.get(
        url=f"{issuer_url.rstrip('/')}/mcp/whoami",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["group_slug"]


def save_credentials(*, credentials: Credentials, path: Path) -> None:
    """Write the credentials JSON file with 0600 permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = credentials.model_dump_json(indent=2)
    path.write_text(serialized, encoding="utf-8")
    path.chmod(0o600)


def load_credentials(*, path: Path) -> Credentials:
    """Load credentials from disk (raises FileNotFoundError if missing)."""
    if not path.exists():
        raise FileNotFoundError(
            f"No credentials at {path}; run `glossogen login` first to authenticate."
        )
    raw = path.read_text(encoding="utf-8")
    return Credentials.model_validate_json(raw)


async def run_login(*, issuer_url: str, timeout_seconds: float) -> Credentials:
    """End-to-end PKCE login against ``issuer_url``; persists and returns credentials.

    Opens the user's browser, runs a loopback HTTP server for the
    callback, exchanges the code for tokens, then calls
    ``/mcp/whoami`` to learn the consented ``group_slug``.
    """
    issuer_url = issuer_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        metadata = await _fetch_metadata(client=client, issuer_url=issuer_url)
        port = _claim_loopback_port()
        redirect_uri = f"http://127.0.0.1:{port}{_CALLBACK_PATH}"
        client_id, client_secret = await _register_client(
            client=client,
            registration_endpoint=metadata.registration_endpoint,
            redirect_uri=redirect_uri,
        )

        code_verifier, code_challenge = _generate_pkce_pair()
        state_nonce = secrets.token_urlsafe(24)
        authorize_query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": state_nonce,
                "scope": "read write",
            }
        )
        authorize_url = f"{metadata.authorization_endpoint}?{authorize_query}"
        logger.info("Opening %s", authorize_url)
        webbrowser.open(authorize_url)

        callback = await _await_callback(port=port, timeout_seconds=timeout_seconds)
        if callback.error is not None:
            raise RuntimeError(f"OAuth authorization failed: {callback.error}")
        if callback.code is None:
            raise RuntimeError("OAuth callback fired without a code")
        if callback.state != state_nonce:
            raise RuntimeError(
                "OAuth callback `state` does not match the value the CLI sent — "
                "possible CSRF or session mix-up"
            )

        token_payload = await _exchange_code_for_tokens(
            client=client,
            token_endpoint=metadata.token_endpoint,
            code=callback.code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
        )
        access_token_obj = token_payload["access_token"]
        if not isinstance(access_token_obj, str):
            raise RuntimeError("Token endpoint returned a non-string access_token")
        access_token: str = access_token_obj
        refresh_token_raw = token_payload.get("refresh_token")
        refresh_token: str | None = (
            refresh_token_raw if isinstance(refresh_token_raw, str) else None
        )
        expires_in_raw = token_payload.get("expires_in", 3600)
        expires_in: int = expires_in_raw if isinstance(expires_in_raw, int) else 3600

        group_slug = await _fetch_group_slug(
            client=client,
            issuer_url=issuer_url,
            access_token=access_token,
        )

        credentials = Credentials(
            issuer_url=issuer_url,
            group_slug=group_slug,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.now(tz=UTC) + timedelta(seconds=expires_in),
        )
        save_credentials(credentials=credentials, path=CREDENTIALS_PATH)
        return credentials


async def _await_callback(*, port: int, timeout_seconds: float) -> _CallbackState:
    """Async wrapper that runs the blocking loopback server in a thread."""
    return await asyncio.to_thread(
        _wait_for_callback,
        port=port,
        timeout_seconds=timeout_seconds,
    )


async def refresh_credentials(*, credentials: Credentials) -> Credentials:
    """Trade the stored refresh token for a fresh access token.

    Raises ``RuntimeError`` if no refresh_token is stored or the server
    rejects the refresh — callers should fall back to ``glossogen login``.
    """
    if credentials.refresh_token is None:
        raise RuntimeError("No refresh_token in credentials; run `glossogen login` again.")
    async with httpx.AsyncClient() as client:
        metadata = await _fetch_metadata(client=client, issuer_url=credentials.issuer_url)
        try:
            payload = await _refresh_access_token(
                client=client,
                token_endpoint=metadata.token_endpoint,
                refresh_token=credentials.refresh_token,
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
            )
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Refresh failed ({exc.response.status_code}); run `glossogen login` again."
            ) from exc

        access_token_obj = payload["access_token"]
        if not isinstance(access_token_obj, str):
            raise RuntimeError("Token endpoint returned a non-string access_token")
        access_token: str = access_token_obj
        new_refresh_raw = payload.get("refresh_token")
        new_refresh: str | None = (
            new_refresh_raw if isinstance(new_refresh_raw, str) else credentials.refresh_token
        )
        expires_in_raw = payload.get("expires_in", 3600)
        expires_in: int = expires_in_raw if isinstance(expires_in_raw, int) else 3600

    refreshed = Credentials(
        issuer_url=credentials.issuer_url,
        group_slug=credentials.group_slug,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        access_token=access_token,
        refresh_token=new_refresh,
        expires_at=datetime.now(tz=UTC) + timedelta(seconds=expires_in),
    )
    save_credentials(credentials=refreshed, path=CREDENTIALS_PATH)
    return refreshed


async def load_or_refresh_credentials() -> Credentials:
    """Return live credentials from disk, silently refreshing if near expiry.

    Convenience wrapper used by every command that needs an access token.
    """
    credentials = load_credentials(path=CREDENTIALS_PATH)
    if credentials.is_expired(leeway_seconds=60):
        logger.info("Access token expired; refreshing via stored refresh_token")
        credentials = await refresh_credentials(credentials=credentials)
    return credentials


def delete_credentials(*, path: Path) -> None:
    """Remove the credentials file (used by ``glossogen logout``-style flows)."""
    if path.exists():
        path.unlink()


__all__ = [
    "CREDENTIALS_PATH",
    "Credentials",
    "delete_credentials",
    "load_credentials",
    "load_or_refresh_credentials",
    "refresh_credentials",
    "run_login",
    "save_credentials",
]


# Suppress unused-imports complaints if json isn't directly used by name above.
_ = json
