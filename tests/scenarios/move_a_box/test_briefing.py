"""What a round's briefing and system prompt tell an operator, under each knob."""

import re
from typing import Any, NamedTuple

import pytest

from glossogen.scenarios.move_a_box.events import MoveABoxRoundResolved
from glossogen.scenarios.move_a_box.ids import BAY_LETTERS, BAY_SYMBOLS, OPERATOR_A, OPERATOR_B
from tests.scenarios.move_a_box.move_a_box_play import CRATE_A, CRATE_B, build

TWO_ROUNDS: dict[str, Any] = {"round_count": 2}


def briefing_after(preset_name: str, overrides: dict[str, Any], bays: dict[str, int | None]) -> str:
    """Round 2's briefing for operator_a, after a round 1 that ended on ``bays``."""
    matched = None not in bays.values() and len(set(bays.values())) == 1
    scenario = build(preset_name=preset_name, overrides={**TWO_ROUNDS, **overrides})
    scenario.restore_state_from_events(
        events=[
            MoveABoxRoundResolved(
                round_number=1,
                final_cells={CRATE_A: (2, 3), CRATE_B: (5, 3)},
                final_bays=bays,
                temperatures={CRATE_A: 23, CRATE_B: 23},
                steps_used={OPERATOR_A: 3, OPERATOR_B: 3},
                points={OPERATOR_A: 10, OPERATOR_B: 10},
                matched_slots=(1,) if matched else (),
                matched=matched,
                success=False,
                trigger="all_finished",
            )
        ]
    )
    return scenario.get_injection(round_number=2, agent_id=OPERATOR_A)


def test_a_disclosed_bay_is_named_by_its_square() -> None:
    """A bay has no number an operator could read, so the result gives its square."""
    text = briefing_after(
        preset_name="knobs_default",
        overrides={"partner_bay_disclosed": True},
        bays={CRATE_A: 1, CRATE_B: 4},
    )
    assert "The other crates were left on the bay at 5,4" in text
    assert "bay 4" not in text


def test_an_undisclosed_bay_is_only_somewhere_else() -> None:
    text = briefing_after(
        preset_name="knobs_default",
        overrides={"partner_bay_disclosed": False},
        bays={CRATE_A: 1, CRATE_B: 4},
    )
    assert "The other crates were left in other spots" in text
    assert "5,4" not in text


def test_a_match_is_reported_whether_or_not_bays_are_disclosed() -> None:
    """Both crates on one bay is the score, so it is told either way."""
    for disclosed in (True, False):
        text = briefing_after(
            preset_name="knobs_default",
            overrides={"partner_bay_disclosed": disclosed},
            bays={CRATE_A: 1, CRATE_B: 1},
        )
        assert "left on the same bay" in text


def test_an_undisclosed_miss_does_not_say_the_other_crate_missed_every_bay() -> None:
    """A crate left off the bays reads the same as one left on a different bay."""
    text = briefing_after(
        preset_name="knobs_default",
        overrides={"partner_bay_disclosed": False},
        bays={CRATE_A: 1, CRATE_B: None},
    )
    assert "The other crates were left in other spots" in text
    assert "off any bay" not in text


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
    assert "the only thing that passes between you" in prompt
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


class MarkedPreset(NamedTuple):
    """A preset whose floors hold their own bays, and how its briefing reads."""

    preset_name: str
    word: str
    names: tuple[str, ...]
    entry: str


MARKED_PRESETS = (
    MarkedPreset(
        preset_name="knobs_symbol_bays",
        word="symbol",
        names=tuple(symbol.name for symbol in BAY_SYMBOLS),
        entry=r"\S \w+ at \d+,\d+\.?",
    ),
    MarkedPreset(
        preset_name="knobs_letter_bays",
        word="letter",
        names=BAY_LETTERS,
        entry=r"[A-P] at \d+,\d+\.?",
    ),
)
"""Under symbols a listed bay carries its glyph and its name; under letters the letter is both."""


@pytest.mark.parametrize("marked", MARKED_PRESETS, ids=lambda marked: marked.word)
def test_a_marked_briefing_lists_only_the_operator_s_own_bays_and_their_squares(
    marked: MarkedPreset,
) -> None:
    scenario = build(preset_name=marked.preset_name, overrides=TWO_ROUNDS)
    for agent_id in (OPERATOR_A, OPERATOR_B):
        text = scenario.get_injection(round_number=1, agent_id=agent_id)
        [listing] = [line for line in text.splitlines() if line.startswith("Bays the depot")]
        entries = listing.removeprefix("Bays the depot assigns you this round: ").split(", ")
        assert len(entries) == 3
        for entry in entries:
            assert re.fullmatch(marked.entry, entry) is not None
        assert len({entry.split(" at ")[0] for entry in entries}) == 3


@pytest.mark.parametrize("marked", MARKED_PRESETS, ids=lambda marked: marked.word)
def test_a_marked_result_names_the_other_crate_s_mark_and_not_its_square(
    marked: MarkedPreset,
) -> None:
    """Bay 4 carries the fourth mark, and its square on the other floor means nothing here."""
    text = briefing_after(
        preset_name=marked.preset_name,
        overrides={"partner_bay_disclosed": True},
        bays={CRATE_A: 1, CRATE_B: 4},
    )
    assert f"you left a crate on the {marked.names[0]} bay" in text
    assert f"The other crates were left on the {marked.names[3]} bay" in text
    assert "the bay at" not in text


@pytest.mark.parametrize("marked", MARKED_PRESETS, ids=lambda marked: marked.word)
def test_a_marked_match_is_reported_as_one_mark(marked: MarkedPreset) -> None:
    text = briefing_after(
        preset_name=marked.preset_name,
        overrides={"partner_bay_disclosed": False},
        bays={CRATE_A: 1, CRATE_B: 1},
    )
    assert f"left on a bay with the same {marked.word}" in text


@pytest.mark.parametrize("marked", MARKED_PRESETS, ids=lambda marked: marked.word)
def test_the_marked_system_prompt_says_squares_differ(marked: MarkedPreset) -> None:
    scenario = build(preset_name=marked.preset_name, overrides=TWO_ROUNDS)
    prompt = scenario.get_agents(default_model="m", default_provider="openai")[0].system_prompt
    assert f"a bay is named by its {marked.word}" in prompt
    assert f"what counts is a bay's {marked.word}, not where it stands" in prompt
    assert f"a bay with the same {marked.word}" in prompt
    assert "named by the square it stands on" not in prompt


def test_the_symbol_system_prompt_names_no_symbol() -> None:
    """An operator learns the symbols only from its own floor, one round at a time."""
    scenario = build(preset_name="knobs_symbol_bays", overrides=TWO_ROUNDS)
    prompt = scenario.get_agents(default_model="m", default_provider="openai")[0].system_prompt
    named = [symbol.name for symbol in BAY_SYMBOLS if re.search(rf"\b{symbol.name}\b", prompt)]
    assert named == []


def test_the_letter_system_prompt_draws_the_crate_apart_from_bay_c() -> None:
    scenario = build(preset_name="knobs_letter_bays", overrides=TWO_ROUNDS)
    prompt = scenario.get_agents(default_model="m", default_provider="openai")[0].system_prompt
    assert "@ where the crate starts" in prompt
    assert "C where" not in prompt


SWITCHED = {"round_count": 10}
"""The letters-then-symbols preset at its own length: letters to round 5, symbols from round 6."""


def test_the_round_a_switch_takes_effect_announces_it_and_lists_symbols() -> None:
    scenario = build(preset_name="knobs_letters_then_symbols", overrides=SWITCHED)
    fifth, sixth, seventh = (
        scenario.get_injection(round_number=n, agent_id=OPERATOR_A) for n in (5, 6, 7)
    )
    notice = "From this round on, each bay is marked with a symbol instead of a letter"
    assert notice not in fifth
    assert notice in sixth
    assert notice not in seventh
    assert "the crate's start as C" in sixth
    for text, entry in ((fifth, MARKED_PRESETS[1].entry), (sixth, MARKED_PRESETS[0].entry)):
        [listing] = [line for line in text.splitlines() if line.startswith("Bays the depot")]
        entries = listing.removeprefix("Bays the depot assigns you this round: ").split(", ")
        assert all(re.fullmatch(entry, item) is not None for item in entries)


def test_the_first_symbol_round_reports_the_last_letter_round_in_letters() -> None:
    """Round 5 was played on letters, so its result names letters even in round 6's briefing."""
    scenario = build(preset_name="knobs_letters_then_symbols", overrides=SWITCHED)
    crates = scenario.get_world().crate_ids
    scenario.restore_state_from_events(
        events=[
            MoveABoxRoundResolved(
                round_number=5,
                final_cells={crate: (2, 3) for crate in crates},
                final_bays=dict.fromkeys(crates, 4),
                temperatures=dict.fromkeys(crates, 24),
                steps_used={OPERATOR_A: 3, OPERATOR_B: 3},
                points={OPERATOR_A: 20, OPERATOR_B: 20},
                matched_slots=(1,),
                matched=True,
                success=True,
                trigger="all_finished",
            )
        ]
    )
    text = scenario.get_injection(round_number=6, agent_id=OPERATOR_A)
    assert "you left a crate on the D bay" in text
    assert "left on a bay with the same letter" in text


def test_the_description_names_the_switch() -> None:
    scenario = build(preset_name="knobs_letters_then_symbols", overrides=SWITCHED)
    assert "From round 6 the bays carry symbols instead of letters." in (
        scenario.scenario_description()
    )


def test_the_system_prompt_describes_the_identity_the_run_starts_with() -> None:
    scenario = build(preset_name="knobs_letters_then_symbols", overrides=SWITCHED)
    prompt = scenario.get_agents(default_model="m", default_provider="openai")[0].system_prompt
    assert "a bay is named by its letter" in prompt
    assert "@ where the crate starts" in prompt
