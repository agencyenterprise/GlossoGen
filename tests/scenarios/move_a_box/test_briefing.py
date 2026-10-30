"""What a round's briefing and system prompt tell an operator, under each knob."""

from typing import Any

from glossogen.scenarios.move_a_box.events import MoveABoxRoundResolved
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from tests.scenarios.move_a_box.move_a_box_play import build

TWO_ROUNDS: dict[str, Any] = {"round_count": 2}


def briefing_after(overrides: dict[str, Any], bays: dict[str, int | None]) -> str:
    """Round 2's briefing for operator_a, after a round 1 that ended on ``bays``."""
    scenario = build(preset_name="knobs_default", overrides={**TWO_ROUNDS, **overrides})
    scenario.restore_state_from_events(
        events=[
            MoveABoxRoundResolved(
                round_number=1,
                final_cells={OPERATOR_A: (2, 3), OPERATOR_B: (5, 3)},
                final_bays=bays,
                temperatures={OPERATOR_A: 23, OPERATOR_B: 23},
                steps_used={OPERATOR_A: 3, OPERATOR_B: 3},
                points={OPERATOR_A: 10, OPERATOR_B: 10},
                matched=len({bay for bay in bays.values() if bay is not None}) == 1
                and None not in bays.values(),
                success=False,
                trigger="both_finished",
            )
        ]
    )
    return scenario.get_injection(round_number=2, agent_id=OPERATOR_A)


def test_a_disclosed_bay_is_named_by_its_square() -> None:
    """A bay has no number an operator could read, so the result gives its square."""
    text = briefing_after(
        overrides={"partner_bay_disclosed": True}, bays={OPERATOR_A: 1, OPERATOR_B: 4}
    )
    assert "The other crate was left on the bay at 5,4" in text
    assert "bay 4" not in text


def test_an_undisclosed_bay_is_only_somewhere_else() -> None:
    text = briefing_after(
        overrides={"partner_bay_disclosed": False}, bays={OPERATOR_A: 1, OPERATOR_B: 4}
    )
    assert "The other crate was left in another spot" in text
    assert "5,4" not in text


def test_a_match_is_reported_whether_or_not_bays_are_disclosed() -> None:
    """Both crates on one bay is the score, so it is told either way."""
    for disclosed in (True, False):
        text = briefing_after(
            overrides={"partner_bay_disclosed": disclosed},
            bays={OPERATOR_A: 1, OPERATOR_B: 1},
        )
        assert "left on the same bay" in text


def test_an_undisclosed_miss_does_not_say_the_other_crate_missed_every_bay() -> None:
    """A crate left off the bays reads the same as one left on a different bay."""
    text = briefing_after(
        overrides={"partner_bay_disclosed": False}, bays={OPERATOR_A: 1, OPERATOR_B: None}
    )
    assert "The other crate was left in another spot" in text
    assert "did not reach a bay" not in text


def test_a_corner_start_briefs_both_operators_on_the_same_square() -> None:
    scenario = build(preset_name="knobs_default", overrides={**TWO_ROUNDS, "crate_start": "corner"})
    texts = [scenario.get_injection(round_number=1, agent_id=a) for a in (OPERATOR_A, OPERATOR_B)]
    for text in texts:
        assert "The crate starts at 1,1." in text


def test_separate_random_starts_brief_each_operator_on_its_own_square() -> None:
    scenario = build(
        preset_name="knobs_default", overrides={**TWO_ROUNDS, "crate_start": "separate_random"}
    )
    starts = [
        line
        for agent_id in (OPERATOR_A, OPERATOR_B)
        for line in scenario.get_injection(round_number=1, agent_id=agent_id).splitlines()
        if line.startswith("The crate starts at")
    ]
    assert len(starts) == 2
    assert starts[0] != starts[1]


def test_an_undisclosed_channel_never_points_at_the_temperature() -> None:
    """The default condition leaves the readout unexplained, which is the whole task."""
    scenario = build(preset_name="knobs_default", overrides=TWO_ROUNDS)
    prompt = scenario.get_agents(default_model="m", default_provider="openai")[0].system_prompt
    assert "temperature" in prompt
    assert "Use it" not in prompt
    assert "tells the other operator" not in prompt


def test_a_disclosed_channel_names_the_temperature_and_what_to_do_with_it() -> None:
    scenario = build(preset_name="knobs_channel_disclosed", overrides=TWO_ROUNDS)
    prompt = scenario.get_agents(default_model="m", default_provider="openai")[0].system_prompt
    assert "the only thing that passes between the two of you" in prompt
    assert "which bays you were assigned" in prompt
    assert "agree on what a reading means" in prompt


def test_a_disclosed_channel_states_what_each_action_does_to_the_reading() -> None:
    """The preset hands over the alphabet too, so only the protocol is left to invent."""
    scenario = build(preset_name="knobs_channel_disclosed", overrides=TWO_ROUNDS)
    prompt = scenario.get_agents(default_model="m", default_provider="openai")[0].system_prompt
    for line in ("drag: +3", "sled: +2", "cart: +1", "stand_by: -1", "pack_ice: -2"):
        assert line in prompt


def test_a_shared_random_start_briefs_both_operators_on_one_drawn_square() -> None:
    """Both are told the same square, and it is not the corner every round."""
    scenario = build(
        preset_name="knobs_default", overrides={**TWO_ROUNDS, "crate_start": "shared_random"}
    )
    lines = [
        line
        for round_number in (1, 2)
        for agent_id in (OPERATOR_A, OPERATOR_B)
        for line in scenario.get_injection(
            round_number=round_number, agent_id=agent_id
        ).splitlines()
        if line.startswith("The crate starts at")
    ]
    assert lines[0] == lines[1]
    assert lines[2] == lines[3]
    assert "The crate starts at 1,1." not in lines
