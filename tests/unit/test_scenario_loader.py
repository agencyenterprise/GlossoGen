"""Resolving scenario names through the loader, and a scenario loaded from outside glossogen.

The fake package under ``tests/fakes/external_scenario`` stands in for a
scenario defined outside the built-in package. It is loaded through a module
source, the way a project lists one in ``[tool.glossogen] scenarios``.
"""

from collections.abc import Iterator

import orjson
import pytest

from glossogen.scenario_contract.catalog import (
    ScenarioNotLoaded,
    built_in_scenario_sources,
    current_scenario_catalog,
    load_scenario_catalog,
)
from glossogen.scenario_contract.loader import (
    available_scenario_names,
    find_scenario_class,
    get_scenario_class,
    iter_scenario_classes,
)
from glossogen.scenario_contract.scenario_source_kinds import ModuleSource
from tests.fakes.catalog_installation import scenario_catalog_installed
from tests.fakes.scenario_with_bad_preset.scenario import ScenarioWithBadPreset

BUILT_IN_SCENARIOS = dict(current_scenario_catalog().classes())

FAKE_PACKAGE = "tests.fakes.external_scenario"
EXTERNAL_NAME = "external_scenario"


@pytest.fixture
def with_external() -> Iterator[None]:
    """Load the built-ins plus the fake external package, then restore the catalog.

    Restoring goes through ``scenario_catalog_installed``, which puts back the run
    readers' event-type lookup too.
    """
    with scenario_catalog_installed(catalog=current_scenario_catalog()):
        load_scenario_catalog(
            sources=(
                *built_in_scenario_sources(),
                ModuleSource(module=FAKE_PACKAGE, origin="test"),
            )
        )
        yield


def test_a_built_in_scenario_resolves() -> None:
    """The built-ins are always in the catalog."""
    assert get_scenario_class(name="veyru") is BUILT_IN_SCENARIOS["veyru"]


def test_a_built_in_is_named_after_its_package_directory() -> None:
    """Built-ins register under their directory, so recorded run names do not change."""
    for name, scenario_cls in BUILT_IN_SCENARIOS.items():
        assert scenario_cls.name() == name
        assert scenario_cls.scenario_package_files().name == name


@pytest.mark.usefixtures("with_external")
def test_a_scenario_from_a_source_resolves_and_is_listed() -> None:
    """Name lookups and listings do not distinguish built-ins from loaded sources."""
    resolved = get_scenario_class(name=EXTERNAL_NAME)

    assert resolved.__module__ == f"{FAKE_PACKAGE}.scenario"
    assert EXTERNAL_NAME in available_scenario_names()
    assert (EXTERNAL_NAME, resolved) in iter_scenario_classes()


@pytest.mark.usefixtures("with_external")
def test_a_scenario_from_a_source_serves_its_own_presets() -> None:
    """Presets come from the scenario's own package, not a path under glossogen."""
    resolved = get_scenario_class(name=EXTERNAL_NAME)

    assert resolved.knobs_preset_names() == ["knobs_external_default"]
    preset = resolved.load_knobs_preset(preset_name="knobs_external_default")
    assert preset["round_count"] == 2
    assert preset["seed"] == 42


@pytest.mark.usefixtures("with_external")
def test_a_scenario_from_a_source_builds_and_renders_from_its_own_package() -> None:
    """Resolving a scenario is not the same as it working.

    Builds it the way the CLI does, from its own preset, and checks the agent's
    prompt came from a template inside the scenario's package.
    """
    scenario_cls = get_scenario_class(name=EXTERNAL_NAME)

    config = scenario_cls.prepare_config(
        config=dict(scenario_cls.load_knobs_preset(preset_name="knobs_external_default"))
    )
    scenario = scenario_cls.create_from_config(config=config)
    agents = scenario.get_agents(default_model="m", default_provider="anthropic")

    assert [channel.channel_id for channel in scenario.get_channels()] == ["link"]
    assert len(agents) == 1
    assert "the link" in agents[0].system_prompt, "prompt rendered from the scenario's package"
    assert scenario.judge_round_result(round_number=1, trigger="round_timeout")[0].success


def test_an_unknown_name_is_not_an_error_for_find() -> None:
    """A run whose scenario this process has not loaded is an ordinary outcome."""
    assert find_scenario_class(name="no_such_scenario") is None


def test_an_unknown_name_says_what_is_loaded_and_from_where() -> None:
    """The error is the only place a caller learns what it could have asked for."""
    with pytest.raises(ScenarioNotLoaded) as caught:
        get_scenario_class(name="no_such_scenario")

    message = str(caught.value)
    assert "'no_such_scenario' is not loaded" in message
    assert "veyru" in message
    assert "glossogen.scenarios (built-in)" in message
    assert isinstance(caught.value, ValueError)


def test_a_preset_that_does_not_parse_is_not_reported_as_missing() -> None:
    """The two failures are different questions and must not read the same.

    ``load_knobs_preset`` raises ValueError for a preset it does not ship, and
    orjson raises a ValueError subclass for one it cannot parse. A caller that
    cannot tell them apart says "not found" about a file sitting right there.
    """
    assert ScenarioWithBadPreset.knobs_preset_names() == ["knobs_broken"], "it does ship it"
    with pytest.raises(orjson.JSONDecodeError):
        ScenarioWithBadPreset.load_knobs_preset(preset_name="knobs_broken")
    with pytest.raises(ValueError, match="not found"):
        ScenarioWithBadPreset.load_knobs_preset(preset_name="knobs_absent")
