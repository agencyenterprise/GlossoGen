"""Tests for what `--config` and `--knobs` name.

A scenario's presets live inside its own package, so a path to one is only
typeable by someone who can see that package: `src/glossogen/scenarios/...` from
a checkout, a path into `site-packages` from an install. Resolving a preset name
is what makes one command work in both places, and both flags resolve the same
way so there is one rule to remember rather than two.

Neither falls back to a preset of its own accord: `--config` is required, and
`--knobs` absent means no overrides.

The failures are `SystemExit` because these run at CLI preflight, before a run
directory exists.
"""

import json
from pathlib import Path

import pytest

from glossogen.knobs_resolution import resolve_knobs_config, resolve_knobs_overrides
from glossogen.scenario_loader import get_scenario_class

SCENARIO = get_scenario_class("prisoners_dilemma")
PRESET = "knobs_default"


def test_a_preset_name_resolves_without_naming_a_path() -> None:
    """The name a scenario publishes, which is the same string in either layout."""
    resolved = resolve_knobs_config(scenario_cls=SCENARIO, requested=PRESET)
    assert resolved.config == SCENARIO.load_knobs_preset(preset_name=PRESET)
    assert PRESET in resolved.source


def test_the_json_suffix_is_tolerated() -> None:
    """`knobs_default.json` is what the file is called, so it is what people type."""
    resolved = resolve_knobs_config(scenario_cls=SCENARIO, requested=f"{PRESET}.json")
    assert resolved.config == SCENARIO.load_knobs_preset(preset_name=PRESET)


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
    (tmp_path / f"{PRESET}.json").write_text(json.dumps({"round_count": 99}))
    resolved = resolve_knobs_config(scenario_cls=SCENARIO, requested=f"{PRESET}.json")
    assert resolved.config == {"round_count": 99}


def test_neither_a_file_nor_a_preset_says_which_presets_exist() -> None:
    """Naming the alternatives is the difference between a typo and a hunt."""
    with pytest.raises(SystemExit) as caught:
        resolve_knobs_config(scenario_cls=SCENARIO, requested="knobs_nonexistent")
    message = str(caught.value)
    assert "knobs_nonexistent" in message
    assert PRESET in message


def test_a_file_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    """Knobs are a mapping; a list would fail later, against the knobs model."""
    own = tmp_path / "wrong.json"
    own.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(SystemExit) as caught:
        resolve_knobs_config(scenario_cls=SCENARIO, requested=str(own))
    assert str(own) in str(caught.value)


def test_overrides_are_absent_rather_than_defaulted() -> None:
    """No `--knobs` means no overrides, which is a resumed run's normal state.

    `--config` is required and has no fallback either, so nothing in the CLI
    picks a configuration nobody asked for.
    """
    assert resolve_knobs_overrides(scenario_cls=SCENARIO, requested=None) is None


def test_overrides_take_a_preset_name_too() -> None:
    """One vocabulary across both flags, so there is one rule to remember."""
    resolved = resolve_knobs_overrides(scenario_cls=SCENARIO, requested=PRESET)
    assert resolved is not None
    assert resolved.config == SCENARIO.load_knobs_preset(preset_name=PRESET)


def test_overrides_reject_an_unknown_name_by_naming_the_flag() -> None:
    """The message says which flag was wrong, since both resolve the same way."""
    with pytest.raises(SystemExit) as caught:
        resolve_knobs_overrides(scenario_cls=SCENARIO, requested="knobs_nonexistent")
    assert "--knobs" in str(caught.value)
