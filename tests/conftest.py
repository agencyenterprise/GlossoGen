"""Shared fixtures for the test suite.

Nothing here reaches the network. Tests that need an LLM use the fakes in
``tests/fakes``; tests that need a scenario construct it from its own preset.
"""

import pytest

from glossogen.event_bus import EventBus


@pytest.fixture
def event_bus() -> EventBus:
    """An EventBus with a queue large enough that no test fills it."""
    return EventBus(max_queue_size=1000)


@pytest.fixture(autouse=True)
def no_real_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test placeholder credentials.

    Scenarios that judge their own rounds build a provider when they are
    constructed, so they cannot be built at all without a key. The values are
    never sent anywhere — tests that exercise an LLM replace the provider
    outright — so this only removes the construction barrier, and a contributor
    with no keys still gets a green suite.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-sent")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent")
