"""Codebooks and requests drawn from the seed."""

from glossogen.scenarios.dead_drop.case_generation import RoundCase, generate_cases
from glossogen.scenarios.dead_drop.ids import AGENT_IDS, PARTNER_OF
from tests.scenarios.dead_drop.dead_drop_wiring import codebook_keys


def default_sized(seed: int, recorded: dict[int, RoundCase]) -> list[RoundCase]:
    """Ten rounds at ``knobs_default``'s sizes."""
    return generate_cases(
        seed=seed, round_count=10, codebook_entries=8, queries_per_agent=3, recorded=recorded
    )


def test_every_request_is_a_key_only_the_partner_holds() -> None:
    cases = generate_cases(
        seed=42, round_count=5, codebook_entries=8, queries_per_agent=3, recorded={}
    )
    for case in cases:
        for agent_id in AGENT_IDS:
            own = case.by_agent[agent_id]
            partner = case.by_agent[PARTNER_OF[agent_id]]
            assert len(own.codebook) == 8
            assert len(own.requests) == 3
            assert set(own.requests) <= set(partner.codebook)
            assert not set(own.requests) & set(own.codebook)


def test_no_key_is_drawn_twice_in_a_run() -> None:
    cases = default_sized(seed=42, recorded={})
    keys = [
        key
        for case in cases
        for agent_case in case.by_agent.values()
        for key in agent_case.codebook
    ]
    assert len(keys) == len(set(keys)) == 160


def test_a_longer_run_on_the_same_seed_starts_with_the_same_rounds() -> None:
    short = generate_cases(
        seed=42, round_count=3, codebook_entries=8, queries_per_agent=3, recorded={}
    )
    long = generate_cases(
        seed=42, round_count=6, codebook_entries=8, queries_per_agent=3, recorded={}
    )
    assert long[:3] == short


def test_expected_answers_come_from_the_partner_codebook() -> None:
    case = generate_cases(
        seed=7, round_count=1, codebook_entries=4, queries_per_agent=2, recorded={}
    )[0]
    expected = case.expected_answers(agent_id="ana")
    assert expected == {
        key: case.by_agent["ben"].codebook[key] for key in case.by_agent["ana"].requests
    }


def test_rounds_drawn_after_recorded_ones_reuse_none_of_their_keys() -> None:
    """A fork onto another seed keeps the rounds it played and draws past their keys."""
    played = default_sized(seed=42, recorded={})[0]
    # Seed 9 draws one of those keys in a later round when nothing is recorded.
    assert codebook_keys(cases=[played]) & codebook_keys(
        cases=default_sized(seed=9, recorded={})[1:]
    )

    forked = default_sized(seed=9, recorded={1: played})

    assert forked[0] == played
    assert not codebook_keys(cases=[played]) & codebook_keys(cases=forked[1:])
    assert len(codebook_keys(cases=forked)) == 160


def test_recording_the_rounds_a_seed_draws_changes_nothing() -> None:
    """A fork that keeps the seed and sizes plays the rounds the source would have."""
    drawn = default_sized(seed=42, recorded={})
    recorded = {case.round_number: case for case in drawn[:4]}

    assert default_sized(seed=42, recorded=recorded) == drawn
