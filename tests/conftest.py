"""Shared fixtures for the test suite.

Nothing here reaches the network. Tests that need an LLM use the fakes in
``tests/fakes``; tests that need a scenario construct it from its own preset.
"""

import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from glossogen.runtime.event_bus import EventBus
from glossogen.scenario_contract import registration
from glossogen.scenario_contract.catalog import (
    built_in_scenario_sources,
    current_scenario_catalog,
    load_scenario_catalog,
)
from tests.fakes.catalog_installation import scenario_catalog_installed

METRICS_ML_OPTION = "--metrics-ml"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


def pytest_configure(config: pytest.Config) -> None:
    """Load the built-in scenario catalog before any test module is collected.

    The CLI loads it before dispatching a command, and every scenario lookup
    raises until it has. Test modules list the built-ins at import time to
    parametrize over them, so loading has to happen before collection.
    """
    _ = config
    load_scenario_catalog(sources=built_in_scenario_sources())


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


@pytest.fixture
def isolated_scenario_imports(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Let a test load scenarios from ``tmp_path`` without the rest of the suite seeing them.

    Restores the registry, ``sys.path``, the current catalog and the run readers'
    event-type lookup, and forgets the modules the test imported from outside the
    repository, so two tests can each import a module called
    ``scenarios.reactor_purge`` from their own directories. Modules from the
    repository (``tests.fakes.*``) stay, so a later test does not import a second
    copy of their classes.
    """
    monkeypatch.setattr(registration, "_REGISTERED", dict(registration.registered_scenarios()))
    monkeypatch.setattr(sys, "path", list(sys.path))
    before = set(sys.modules)
    with scenario_catalog_installed(catalog=current_scenario_catalog()):
        yield
    outside_repository = [
        name
        for name in set(sys.modules) - before
        if not _lives_in_repository(module=sys.modules[name])
    ]
    for name in outside_repository:
        del sys.modules[name]


def _lives_in_repository(module: ModuleType) -> bool:
    """Whether ``module`` was imported from a file or package directory under the repository."""
    locations = [getattr(module, "__file__", None), *getattr(module, "__path__", [])]
    return any(
        location is not None and Path(location).is_relative_to(REPOSITORY_ROOT)
        for location in locations
    )


@pytest.fixture(autouse=True)
def no_scenario_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the variables that choose which scenarios and runs a command loads.

    A developer with ``GLOSSOGEN_SCENARIOS`` or ``GLOSSOGEN_RUNS_DIR`` exported
    would otherwise change what every test that drives ``main()`` loads. A test
    that needs one sets it itself.
    """
    monkeypatch.delenv("GLOSSOGEN_SCENARIOS", raising=False)
    monkeypatch.delenv("GLOSSOGEN_RUNS_DIR", raising=False)


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
