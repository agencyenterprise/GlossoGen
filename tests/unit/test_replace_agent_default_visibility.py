"""The replace-agent default channel visibility, read off a source run's recorded knobs.

The knob is read through the scenario's knobs model with ``--knobs`` merged on
top, the same config the fork itself validates.
"""

from typing import Any

import pytest

from glossogen.cli import (
    _recorded_default_channel_visibility,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.testing.smoke_scenario import SmokeKnobs, SmokeScenario


def recorded_config(visibility: dict[str, bool]) -> dict[str, Any]:
    """A smoke config as a run records it, with ``visibility`` as the knob."""
    return SmokeKnobs(
        round_count=2,
        max_round_duration_seconds=45,
        model_overrides={},
        replace_agent_default_channel_visibility=visibility,
    ).model_dump(mode="json")


def test_the_recorded_knob_is_returned() -> None:
    assert _recorded_default_channel_visibility(
        scenario_cls=SmokeScenario,
        recorded_config=recorded_config(visibility={"postmortem": False}),
        knobs=None,
    ) == {"postmortem": False}


def test_knobs_merged_on_top_win() -> None:
    assert _recorded_default_channel_visibility(
        scenario_cls=SmokeScenario,
        recorded_config=recorded_config(visibility={"postmortem": False}),
        knobs={"replace_agent_default_channel_visibility": {"link": False}},
    ) == {"link": False}


def test_a_recorded_config_missing_a_required_knob_is_named_rather_than_guessed() -> None:
    config = recorded_config(visibility={})
    del config["round_count"]
    with pytest.raises(SystemExit, match="--visible-history-channel"):
        _recorded_default_channel_visibility(
            scenario_cls=SmokeScenario, recorded_config=config, knobs=None
        )
    assert (
        _recorded_default_channel_visibility(
            scenario_cls=SmokeScenario, recorded_config=config, knobs={"round_count": 2}
        )
        == {}
    )
