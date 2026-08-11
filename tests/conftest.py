"""Shared fixtures for the test suite.

Nothing here reaches the network. Tests that need an LLM use the fakes in
``tests/fakes``; tests that need a scenario construct it from its own preset.
"""

import pytest

from glossogen.event_bus import EventBus

METRICS_ML_OPTION = "--metrics-ml"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the opt-in flag for tests that need the `metrics-ml` extra.

    Those tests download and run a real model, which is minutes of wall clock
    and gigabytes of dependency. They are off by default so `make test` stays
    something anyone can run, and available on demand so the code they cover is
    not permanently untestable.
    """
    parser.addoption(
        METRICS_ML_OPTION,
        action="store_true",
        default=False,
        help="run tests that need the metrics-ml extra (downloads and runs a real model)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip `metrics_ml` tests unless the flag was passed.

    The skip reason names the flag, so a reader who wonders why the real
    perplexity path is not covered finds out how to cover it.
    """
    if config.getoption(METRICS_ML_OPTION):
        return
    skip = pytest.mark.skip(reason=f"needs the metrics-ml extra; pass {METRICS_ML_OPTION} to run")
    for item in items:
        if item.get_closest_marker("metrics_ml") is not None:
            item.add_marker(skip)


@pytest.fixture
def event_bus() -> EventBus:
    """An EventBus with a queue large enough that no test fills it."""
    return EventBus(max_queue_size=1000)


@pytest.fixture(autouse=True)
def no_real_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test placeholder credentials.

    Scenarios that judge their own rounds build a provider when constructed, so
    they cannot be built at all without a key. Nothing is ever sent: tests that
    exercise an LLM replace the provider outright. This removes the construction
    barrier and nothing else, so a contributor with no keys still gets a green
    suite.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-sent")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent")
