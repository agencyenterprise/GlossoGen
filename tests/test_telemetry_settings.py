"""Tests for Langfuse telemetry environment settings."""

from glossogen.telemetry_settings import TelemetrySettings


def test_telemetry_requires_non_empty_keys() -> None:
    assert not TelemetrySettings(public_key="", secret_key="", host=None).enabled
    assert not TelemetrySettings(public_key="public", secret_key="", host=None).enabled
    assert not TelemetrySettings(public_key=None, secret_key="secret", host=None).enabled
    assert TelemetrySettings(public_key="public", secret_key="secret", host=None).enabled
