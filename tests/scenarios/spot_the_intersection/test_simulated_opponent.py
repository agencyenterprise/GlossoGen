"""A simulated Team B: Team A plays alone and is told what a real Team B would produce.

Team A's viewers must hold the same names, channels and system prompts as in a
real two-team run. Scoring ranks Team A against a Team B that is always right in
a share of Team A's characters, drawn each round within a range from the seed and
the round number, rounded down; only Team A's verdict is recorded, and its reason
names the opponent as simulated.
"""

import math
from fractions import Fraction
from pathlib import Path

import pytest
from pydantic import ValidationError

from glossogen.models.event import RoundResultRecorded, WorldEventDelivered
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.spot_the_intersection.ids import ROUND_LOST_MARKER
from glossogen.scenarios.spot_the_intersection.knobs import SpotTheIntersectionKnobs
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario
from glossogen.scenarios.spot_the_intersection.world_state import (
    SimulatedOpponent,
    TeamSnapshot,
    outcome_reason,
    score_round,
    simulated_opponent_for,
)
from glossogen.testing.scenario_runtime import ROUND_SECONDS, build_scenario
from glossogen.testing.scripted_agent import ScriptedTurn
from tests.scenarios.spot_the_intersection.conftest import (
    SCENARIO,
    TEAM_A,
    answer_of,
    play,
    say_on,
    submit,
    world_of,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)


def scenario_from(preset_name: str) -> SimulationScenario:
    """A shipped preset, cut to one round with no debrief."""
    return build_scenario(
        scenario_name=SCENARIO,
        preset_name=preset_name,
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
        },
    )


def team_a(characters: int, members_correct: int) -> TeamSnapshot:
    """Team A's end of round: four members submitted, ``members_correct`` of them right."""
    return TeamSnapshot(
        team_id="team_a",
        members_required=4,
        members_submitted=4,
        members_correct=members_correct,
        agreed=members_correct in (0, 4),
        budget_exceeded=False,
        characters=characters,
    )


def fixed(share: float) -> SimulatedOpponent | None:
    """A simulated Team B whose range has equal ends, so every round has ``share``."""
    return simulated_opponent_for(seed=42, share=share)


def test_team_a_is_briefed_as_in_a_two_team_run() -> None:
    def prompts(preset_name: str) -> dict[str, str]:
        scenario = scenario_from(preset_name=preset_name)
        agents = scenario.get_agents(default_model="m", default_provider="anthropic")
        return {agent.agent_id: agent.system_prompt for agent in agents}

    real = prompts(preset_name="knobs_default")
    simulated = prompts(preset_name="knobs_simulated_opponent")

    assert sorted(simulated) == sorted(TEAM_A)
    assert simulated == {agent_id: real[agent_id] for agent_id in TEAM_A}


def test_a_correct_team_loses_to_a_smaller_share_of_its_own_characters() -> None:
    (outcome,) = score_round(
        round_number=1,
        snapshots=[team_a(characters=203, members_correct=4)],
        competitive=True,
        simulated_opponent=fixed(share=0.8),
    )

    assert outcome.correct
    assert not outcome.won
    assert outcome.opponent_correct is True
    assert outcome.opponent_characters == 162
    assert outcome.opponent_simulated
    assert "simulated opponent 162 chars" in outcome_reason(outcome=outcome)


def test_a_share_above_one_lets_a_correct_team_win() -> None:
    (outcome,) = score_round(
        round_number=1,
        snapshots=[team_a(characters=100, members_correct=4)],
        competitive=True,
        simulated_opponent=fixed(share=1.25),
    )

    assert outcome.won
    assert outcome.opponent_characters == 125


def test_the_share_is_of_the_decimal_not_its_binary_approximation() -> None:
    """0.29 * 100 is 28.999... in binary floating point; the opponent still gets 29."""
    (outcome,) = score_round(
        round_number=1,
        snapshots=[team_a(characters=100, members_correct=4)],
        competitive=True,
        simulated_opponent=fixed(share=0.29),
    )

    assert outcome.opponent_characters == 29


def test_a_wrong_team_loses_to_an_opponent_that_is_always_right() -> None:
    (outcome,) = score_round(
        round_number=1,
        snapshots=[team_a(characters=50, members_correct=0)],
        competitive=True,
        simulated_opponent=fixed(share=0.8),
    )

    assert not outcome.correct
    assert not outcome.won
    assert outcome.opponent_correct is True


def test_a_simulated_opponent_plays_against_one_team_only() -> None:
    with pytest.raises(ValueError, match="one team"):
        score_round(
            round_number=1,
            snapshots=[
                team_a(characters=10, members_correct=4),
                team_a(characters=20, members_correct=4)._replace(team_id="team_b"),
            ],
            competitive=True,
            simulated_opponent=fixed(share=0.8),
        )


def test_each_rounds_share_lies_in_the_range_and_varies_between_rounds() -> None:
    opponent = simulated_opponent_for(seed=42, share=(0.75, 0.85))
    assert opponent is not None

    shares = [opponent.share(round_number=round_number) for round_number in range(1, 201)]

    assert all(Fraction("0.75") <= share <= Fraction("0.85") for share in shares)
    assert min(shares) < Fraction("0.77")
    assert max(shares) > Fraction("0.83")


def test_a_rounds_share_depends_only_on_the_seed_and_the_round() -> None:
    first = simulated_opponent_for(seed=42, share=(0.75, 0.85))
    again = simulated_opponent_for(seed=42, share=(0.75, 0.85))
    other_seed = simulated_opponent_for(seed=7, share=(0.75, 0.85))
    assert first is not None and again is not None and other_seed is not None

    forward = [first.share(round_number=round_number) for round_number in range(1, 11)]
    backward = [again.share(round_number=round_number) for round_number in range(10, 0, -1)]

    assert forward == list(reversed(backward))
    assert forward != [other_seed.share(round_number=round_number) for round_number in range(1, 11)]


def test_the_share_is_a_number_or_a_range_and_needs_two_teams() -> None:
    preset = SpotTheIntersectionScenario.load_knobs_preset(preset_name="knobs_simulated_opponent")

    assert SpotTheIntersectionKnobs.model_validate(preset).simulated_opponent_ratio == (0.75, 0.85)
    fixed_share = {**preset, "simulated_opponent_ratio": 0.8}
    assert SpotTheIntersectionKnobs.model_validate(fixed_share).simulated_opponent_ratio == 0.8
    with pytest.raises(ValidationError, match="needs two_teams=True"):
        SpotTheIntersectionKnobs.model_validate({**preset, "two_teams": False})
    with pytest.raises(ValidationError, match="greater than 0"):
        SpotTheIntersectionKnobs.model_validate({**preset, "simulated_opponent_ratio": 0})
    with pytest.raises(ValidationError, match="greater than 0"):
        SpotTheIntersectionKnobs.model_validate({**preset, "simulated_opponent_ratio": [0, 0.5]})
    with pytest.raises(ValidationError, match="low <= high"):
        SpotTheIntersectionKnobs.model_validate(
            {**preset, "simulated_opponent_ratio": [0.85, 0.75]}
        )


async def test_a_played_round_tells_team_a_it_lost_to_the_other_team(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = scenario_from(preset_name="knobs_simulated_opponent")
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {agent: [submit(obj=answer)] for agent in TEAM_A}
    scripts[TEAM_A[0]] = [
        say_on(scenario=scenario, channel_id="link_a", text="abcde"),
        submit(obj=answer),
    ]

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    (verdict,) = result.of_type(event_type=RoundResultRecorded)
    assert verdict.team_id == "team_a"
    assert verdict.success is True
    assert verdict.reason.startswith("correct but the other team used fewer characters")
    knobs = scenario.get_knobs()
    assert isinstance(knobs, SpotTheIntersectionKnobs)
    opponent = simulated_opponent_for(seed=knobs.seed, share=knobs.simulated_opponent_ratio)
    assert opponent is not None
    expected = math.floor(opponent.share(round_number=1) * len("abcde"))
    assert f"simulated opponent {expected} chars" in verdict.reason
    notices = [
        event.text
        for event in result.of_type(event_type=WorldEventDelivered)
        if event.agent_id == TEAM_A[1]
    ]
    assert any(
        text.startswith(ROUND_LOST_MARKER) and "the other team used fewer" in text
        for text in notices
    )
    assert not any("simulated" in text for text in notices)

    rebuilt = SpotTheIntersectionScenario.create_from_config(
        config=scenario.get_knobs().model_dump(mode="json")
    )
    rebuilt.restore_state_from_events(events=result.events)
    assert world_of(scenario=rebuilt).outcome_for(team_id="team_a", round_number=1) == world_of(
        scenario=result.scenario
    ).outcome_for(team_id="team_a", round_number=1)
