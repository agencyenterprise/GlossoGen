"""When the Langfuse variables turn tracing on.

`.env.example` pre-fills the keys, so blanking them is how a user turns tracing
off. An empty key counts as unset, so a blanked key turns tracing off instead
of being sent to Langfuse and refused.
"""

import pytest

from glossogen.telemetry.telemetry_settings import load_telemetry_settings


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
def test_a_blank_key_disables_telemetry(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    """A blank value is read as unset."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", blank)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-1")
    monkeypatch.setenv("LANGFUSE_HOST", blank)

    settings = load_telemetry_settings()

    assert settings.public_key is None
    assert settings.host is None
    assert not settings.enabled


def test_two_set_keys_enable_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both keys set is what turns tracing on."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-1")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-1")
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)

    assert load_telemetry_settings().enabled


def test_an_unset_key_disables_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """With either key missing, no export is set up."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-1")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    assert not load_telemetry_settings().enabled
