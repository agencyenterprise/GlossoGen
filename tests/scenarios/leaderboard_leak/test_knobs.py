"""The knobs refuse settings whose agent-facing text would be false or unaudited."""

from typing import Any

import pytest
from pydantic import ValidationError

from glossogen.scenarios.leaderboard_leak.scenario import LeaderboardLeakScenario


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sheet_entries": 3}, "greater than or equal to 4"),
        ({"sheet_entries": 600}, "the limit is 10000"),
        ({"disclosure": "comments_read", "comments_visible": False}, "makes false"),
        ({"postmortem_enabled": True}, "postmortem_enabled must be false"),
        ({"compaction": {"enabled": True}}, "compaction.enabled must be false"),
        ({"channel_noise_level": 0.1}, "channel_noise_level must be 0"),
    ],
)
def test_an_inconsistent_setting_is_refused(overrides: dict[str, Any], message: str) -> None:
    preset = LeaderboardLeakScenario.load_knobs_preset(preset_name="knobs_default")
    with pytest.raises(ValidationError, match=message):
        LeaderboardLeakScenario.knobs_model().model_validate(obj={**preset, **overrides})


@pytest.mark.parametrize(
    "preset_name", ["knobs_default", "knobs_chat_control", "knobs_no_comment_control"]
)
def test_every_preset_validates(preset_name: str) -> None:
    LeaderboardLeakScenario.knobs_model().model_validate(
        obj=LeaderboardLeakScenario.load_knobs_preset(preset_name=preset_name)
    )
