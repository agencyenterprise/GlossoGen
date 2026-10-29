"""The server's environment configuration, and the app built from it.

``docker-compose.yml`` passes ``OAUTH_ISSUER_URL`` through as an empty string
when ``.env`` does not set it. The server used to take that as an issuer URL,
mount MCP, and fail to start.
"""

import pytest

from glossogen.server.app_factory import create_app
from glossogen.server.server_runtime_config import load_server_runtime_config


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_issuer_url_starts_the_server_without_mcp(
    monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    monkeypatch.setenv("OAUTH_ISSUER_URL", blank)

    runtime_config = load_server_runtime_config()
    app = create_app(identity_provider=None, runtime_config=runtime_config)

    assert runtime_config.oauth_issuer_url is None
    assert not any(getattr(route, "path", "").startswith("/mcp") for route in app.routes)


def test_an_unset_issuer_url_reads_as_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OAUTH_ISSUER_URL", raising=False)

    assert load_server_runtime_config().oauth_issuer_url is None


def test_a_set_issuer_url_is_read_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAUTH_ISSUER_URL", "https://glossogen.example.com")

    assert load_server_runtime_config().oauth_issuer_url == "https://glossogen.example.com"
