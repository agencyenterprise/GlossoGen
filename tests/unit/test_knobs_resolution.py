"""Tests for what `--config` names.

A scenario's presets live inside its own package, so a path to one is only
typeable by someone who can see that package: `src/glossogen/scenarios/...` from
a checkout, a path into `site-packages` from an install. Resolving a preset name
is what makes one command work in both places, and defaulting to the canonical
preset is what makes the flag optional.

The failures are `SystemExit` because these run at CLI preflight, before a run
directory exists.
"""

import json
from pathlib import Path

import pytest

from glossogen.knobs_resolution import DEFAULT_PRESET_NAME, resolve_knobs_config
from glossogen.scenario_loader import get_scenario_class

SCENARIO = get_scenario_class("prisoners_dilemma")


def test_a_preset_name_resolves_without_naming_a_path() -> None:
    """The name a scenario publishes, which is the same string in either layout."""
    resolved = resolve_knobs_config(scenario_cls=SCENARIO, requested=DEFAULT_PRESET_NAME)
    assert resolved.config == SCENARIO.load_knobs_preset(preset_name=DEFAULT_PRESET_NAME)
    assert DEFAULT_PRESET_NAME in resolved.source


def test_the_json_suffix_is_tolerated() -> None:
    """`knobs_default.json` is what the file is called, so it is what people type."""
    assert resolve_knobs_config(
        scenario_cls=SCENARIO, requested=f"{DEFAULT_PRESET_NAME}.json"
    ).config == SCENARIO.load_knobs_preset(preset_name=DEFAULT_PRESET_NAME)


def test_omitting_it_takes_the_canonical_preset() -> None:
    """The preset the scenario's own documentation calls the default."""
    resolved = resolve_knobs_config(scenario_cls=SCENARIO, requested=None)
    assert resolved.config == SCENARIO.load_knobs_preset(preset_name=DEFAULT_PRESET_NAME)


def test_a_file_still_wins(tmp_path: Path) -> None:
    """An experiment keeps its own knobs JSON outside any package."""
    own = tmp_path / "my_knobs.json"
    own.write_text(json.dumps({"round_count": 3}))
    resolved = resolve_knobs_config(scenario_cls=SCENARIO, requested=str(own))
    assert resolved.config == {"round_count": 3}
    assert resolved.source == str(own)


def test_a_file_named_like_a_preset_is_read_as_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Someone who copied a preset into their project meant their copy."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / f"{DEFAULT_PRESET_NAME}.json").write_text(json.dumps({"round_count": 99}))
    resolved = resolve_knobs_config(scenario_cls=SCENARIO, requested=f"{DEFAULT_PRESET_NAME}.json")
    assert resolved.config == {"round_count": 99}


def test_neither_a_file_nor_a_preset_says_which_presets_exist() -> None:
    """Naming the alternatives is the difference between a typo and a hunt."""
    with pytest.raises(SystemExit) as caught:
        resolve_knobs_config(scenario_cls=SCENARIO, requested="knobs_nonexistent")
    message = str(caught.value)
    assert "knobs_nonexistent" in message
    assert DEFAULT_PRESET_NAME in message
