"""spot_the_difference with ``score_characters`` off tells the agents nothing about characters.

The run plays two rounds through the real round loop with the judge stubbed to a
correct verdict, so the round result, the discussion phase and the next round's
briefing all reach the agents. Every text an agent receives is then scanned for
words about characters, brevity or shorthand.
"""

import re
from pathlib import Path

import pytest

from glossogen.models.event import (
    AgentRegistered,
    InjectionDelivered,
    MessageSent,
    WorldEventDelivered,
)
from glossogen.scenarios.spot_the_difference.difference_judge import SubmissionJudgment
from glossogen.testing.scenario_runtime import build_scenario, fast_round_overrides
from glossogen.testing.scripted_agent import PacedTurn, RoundGate, SayTurn, ToolTurn
from glossogen.testing.simulation_harness import (
    SimulationResult,
    never_times_out,
    run_round_paced_simulation,
)
from tests.scenarios.custom_tool_harness import first_case_of, stub_the_judge

SCENARIO = "spot_the_difference"
TOOL = "submit_differences"

pytestmark = pytest.mark.xdist_group(SCENARIO)

PRESSURE_WORDS = re.compile(
    r"\b(characters?|chars?|short\w*|terse\w*|concise\w*|brief|briefly|brevity|compact\w*|"
    r"abbreviat\w*|minimi[sz]\w*|efficien\w*|codes?|codebook|compress\w*|fewest|fewer|"
    r"shorthand|budget\w*|econom\w*)\b",
    flags=re.IGNORECASE,
)


async def play_two_rounds(
    preset_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimulationResult:
    """Both viewers submit a correct answer in round 1, then idle through round 2."""
    scenario = build_scenario(
        scenario_name=SCENARIO,
        preset_name=preset_name,
        overrides=fast_round_overrides(round_count=2),
    )
    count = len(first_case_of(scenario=scenario).differences)
    stub_the_judge(
        monkeypatch=monkeypatch,
        verdict=SubmissionJudgment(
            matched_difference_indices=list(range(1, count + 1)),
            false_positive_count=0,
            explanation="stubbed",
        ),
    )
    items = [f"difference {index}" for index in range(1, count + 1)]
    scripts: dict[str, list[PacedTurn]] = {}
    for agent in scenario.get_agents(default_model="m", default_provider="anthropic"):
        scripts[agent.agent_id] = [
            RoundGate(round_number=1),
            ToolTurn(tool_name=TOOL, args={"differences": items}),
            SayTurn(text="done"),
            RoundGate(round_number=2),
            SayTurn(text="done"),
        ]
    return await run_round_paced_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def texts_agents_received(result: SimulationResult) -> list[str]:
    """System prompts, tool descriptions, injections, world updates and channel messages."""
    texts: list[str] = []
    for registered in result.of_type(event_type=AgentRegistered):
        texts.append(registered.system_prompt)
        texts.extend(definition.description for definition in registered.tool_definitions)
    texts.extend(event.text for event in result.of_type(event_type=InjectionDelivered))
    texts.extend(event.text for event in result.of_type(event_type=WorldEventDelivered))
    texts.extend(event.message.text for event in result.of_type(event_type=MessageSent))
    return texts


def pressure_words_in(texts: list[str]) -> list[str]:
    """Every pressure word found, with the line it sits in."""
    found: list[str] = []
    for text in texts:
        for line in text.splitlines():
            for match in PRESSURE_WORDS.finditer(line):
                found.append(f"{match.group(0)!r} in: {line.strip()}")
    return found


async def test_no_text_an_agent_receives_mentions_characters_or_brevity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the mode: any leak would bias the control run."""
    result = await play_two_rounds(
        preset_name="knobs_no_character_score", tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    texts = texts_agents_received(result=result)

    assert any("CORRECT" in text for text in texts), "round 1's result never reached the agents"
    assert any("discussion channel is now open" in text for text in texts), "no discussion phase"
    assert pressure_words_in(texts=texts) == []


async def test_the_scored_single_team_preset_trips_the_same_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shows the scan above can fail: the scored preset mentions characters everywhere."""
    result = await play_two_rounds(
        preset_name="knobs_single_team", tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert pressure_words_in(texts=texts_agents_received(result=result)) != []


def test_the_mode_refuses_two_teams() -> None:
    """Two teams win on fewest characters, so the rule itself would mention them."""
    with pytest.raises(ValueError, match="score_characters=False requires two_teams=False"):
        build_scenario(
            scenario_name=SCENARIO,
            preset_name="knobs_no_character_score",
            overrides={"two_teams": True},
        )


def test_the_mode_refuses_a_character_budget() -> None:
    """A budget is announced to the agents in characters."""
    with pytest.raises(ValueError, match="requires round_time_budget_seconds=-1"):
        build_scenario(
            scenario_name=SCENARIO,
            preset_name="knobs_no_character_score",
            overrides={"round_time_budget_seconds": 500},
        )
