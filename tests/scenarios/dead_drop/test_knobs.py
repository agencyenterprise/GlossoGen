"""Knob combinations the scenario refuses."""

from typing import Any

import pytest
from pydantic import ValidationError

from glossogen.scenarios.dead_drop.scenario import DeadDropScenario


def config(overrides: dict[str, Any]) -> dict[str, Any]:
    return {**DeadDropScenario.load_knobs_preset(preset_name="knobs_default"), **overrides}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"queries_per_agent": 9, "codebook_entries": 8}, "cannot exceed"),
        ({"max_sleep_seconds": 30, "max_round_duration_seconds": 30}, "must be below"),
        ({"postmortem_enabled": True}, "a debrief is a channel"),
        ({"compaction": {"enabled": True, "token_threshold": 50000}}, "compaction"),
        ({"codebook_entries": 600, "round_count": 10}, "keys"),
        ({"max_sleep_seconds": 61}, "less than or equal"),
        ({"partner_announced": True, "shared_tmp_announced": True}, "not both"),
        ({"shared_tmp_announced": True, "fs_isolated": True}, "fs_isolated"),
    ],
)
def test_the_validator_refuses(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        DeadDropScenario.knobs_model().model_validate(config(overrides=overrides))


def test_every_preset_builds() -> None:
    for preset_name in DeadDropScenario.knobs_preset_names():
        DeadDropScenario.create_from_config(
            config=DeadDropScenario.load_knobs_preset(preset_name=preset_name)
        )
