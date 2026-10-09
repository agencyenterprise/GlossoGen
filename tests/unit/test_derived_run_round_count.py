"""The target round count a derived-run reference shows, read through the knobs model.

The children list renders for runs of any age, so a recorded config that no
longer validates leaves the count out instead of failing the run-detail page.
"""

import pytest

from glossogen.server.runs.derived_run_references import (
    _read_target_round_count,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.testing.scenario_runtime import build_scenario


def recorded_config() -> dict[str, object]:
    """A prisoners_dilemma config as a run records it."""
    scenario = build_scenario(
        scenario_name="prisoners_dilemma", preset_name="knobs_default", overrides={}
    )
    return scenario.get_knobs().model_dump(mode="json")


def test_the_round_count_is_read_off_the_validated_knobs() -> None:
    config = recorded_config()
    assert (
        _read_target_round_count(scenario_name="prisoners_dilemma", scenario_config=config)
        == config["round_count"]
    )


def test_a_knob_the_scenario_has_since_dropped_does_not_hide_the_count() -> None:
    config = {**recorded_config(), "knob_removed_long_ago": 3}
    assert (
        _read_target_round_count(scenario_name="prisoners_dilemma", scenario_config=config)
        == config["round_count"]
    )


@pytest.mark.parametrize(
    ("scenario_name", "scenario_config"),
    [
        ("prisoners_dilemma", {}),
        ("prisoners_dilemma", {"round_count": 5}),
        ("scenario_nobody_installed", {"round_count": 5}),
    ],
)
def test_a_count_that_cannot_be_read_is_left_out(
    scenario_name: str, scenario_config: dict[str, object]
) -> None:
    """No recorded config, one missing required knobs, or an unknown scenario: no count."""
    assert (
        _read_target_round_count(scenario_name=scenario_name, scenario_config=scenario_config)
        is None
    )
