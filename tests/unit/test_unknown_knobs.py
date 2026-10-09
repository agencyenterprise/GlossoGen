"""A knob the scenario does not declare is an error, except in what a run recorded."""

import logging

import pytest
from pydantic import ValidationError

from glossogen.scenario_loader import get_scenario_class, iter_scenario_classes


def test_a_misspelled_knob_is_refused() -> None:
    """A launch on `max_round_duration_secs=5` ran on the preset's duration."""
    scenario_cls = get_scenario_class(name="veyru")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    config["max_round_duration_secs"] = 5
    with pytest.raises(ValidationError, match="max_round_duration_secs"):
        scenario_cls.create_from_config(config=config)


def test_a_recorded_config_drops_a_knob_the_scenario_no_longer_has(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A run predating a knob's removal still rebuilds, and says which key it ignored."""
    scenario_cls = get_scenario_class(name="veyru")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    config["retired_knob"] = True
    with caplog.at_level(logging.WARNING):
        scenario = scenario_cls.create_from_recorded_config(config=config)
    assert scenario.name() == "veyru"
    assert "retired_knob" in caplog.text
    assert "retired_knob" not in scenario_cls.strip_unknown_knobs(config=config)


def test_every_shipped_preset_declares_only_known_knobs() -> None:
    for _, scenario_cls in iter_scenario_classes():
        for preset in scenario_cls.knobs_preset_names():
            config = scenario_cls.load_knobs_preset(preset_name=preset)
            assert scenario_cls.strip_unknown_knobs(config=config) == config, (
                scenario_cls.name(),
                preset,
            )
