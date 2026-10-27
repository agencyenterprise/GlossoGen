"""What the players are told under each prompt_detail: the full wording explains the
mechanics, the lean one leaves them out."""

import pytest

from glossogen.scenarios.carrier_song.ids import PLAYER_A
from glossogen.scenarios.carrier_song.scenario import CarrierSongScenario
from tests.scenarios.carrier_song.carrier_song_play import build

MECHANICS = [
    "64 whole numbers",
    "between -2 and 2",
    "±2",
    "channel noise",
    "7Z2CRV",
    "stays in place",
    "A-Z",
]
"""Phrases that explain how the channel works: the song's length, the volume limit,
the channel noise, the code's format and example, and the executor's persistence."""


def everything_a_player_reads(scenario: CarrierSongScenario) -> str:
    [agent] = [
        a
        for a in scenario.get_agents(default_model="m", default_provider="anthropic")
        if a.agent_id == PLAYER_A
    ]
    prompts = scenario.runner_prompts(agent_id=PLAYER_A)
    assert prompts is not None
    descriptions = [tool.description for tool in scenario.get_tools()]
    briefing = scenario.get_injection(round_number=1, agent_id=PLAYER_A)
    return "\n".join([agent.system_prompt, prompts.system_suffix, briefing, *descriptions])


def test_the_full_wording_explains_the_mechanics() -> None:
    text = everything_a_player_reads(scenario=build(overrides={"prompt_detail": "full"}))

    for phrase in MECHANICS:
        assert phrase in text, phrase


def test_the_lean_wording_leaves_the_mechanics_out() -> None:
    text = everything_a_player_reads(scenario=build(overrides={"prompt_detail": "lean"}))

    for phrase in MECHANICS:
        assert phrase not in text, phrase
    assert "noise(song)" in text
    assert "Read the song with read_song()" not in text


@pytest.mark.parametrize("prompt_detail", ["full", "lean"])
def test_both_wordings_name_every_tool_and_the_secret(prompt_detail: str) -> None:
    scenario = build(overrides={"prompt_detail": prompt_detail})
    text = everything_a_player_reads(scenario=scenario)

    for name in (
        "read_song",
        "write_executor",
        "read_output",
        "end_round",
        "read_received",
        "submit_decoding",
        "run_python",
    ):
        assert name in text, name
    assert "Your secret code is 2G48H8" in text
