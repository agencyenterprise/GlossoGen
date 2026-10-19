"""Codebooks and requests drawn from the seed."""

from glossogen.scenarios.dead_drop.case_generation import generate_cases
from glossogen.scenarios.dead_drop.ids import AGENT_IDS, PARTNER_OF


def test_every_request_is_a_key_only_the_partner_holds() -> None:
    for case in generate_cases(seed=42, round_count=5, codebook_entries=8, queries_per_agent=3):
        for agent_id in AGENT_IDS:
            own = case.by_agent[agent_id]
            partner = case.by_agent[PARTNER_OF[agent_id]]
            assert len(own.codebook) == 8
            assert len(own.requests) == 3
            assert set(own.requests) <= set(partner.codebook)
            assert not set(own.requests) & set(own.codebook)


def test_no_key_is_drawn_twice_in_a_run() -> None:
    cases = generate_cases(seed=42, round_count=10, codebook_entries=8, queries_per_agent=3)
    keys = [
        key
        for case in cases
        for agent_case in case.by_agent.values()
        for key in agent_case.codebook
    ]
    assert len(keys) == len(set(keys)) == 160


def test_a_longer_run_on_the_same_seed_starts_with_the_same_rounds() -> None:
    short = generate_cases(seed=42, round_count=3, codebook_entries=8, queries_per_agent=3)
    long = generate_cases(seed=42, round_count=6, codebook_entries=8, queries_per_agent=3)
    assert long[:3] == short


def test_expected_answers_come_from_the_partner_codebook() -> None:
    case = generate_cases(seed=7, round_count=1, codebook_entries=4, queries_per_agent=2)[0]
    expected = case.expected_answers(agent_id="ana")
    assert expected == {
        key: case.by_agent["ben"].codebook[key] for key in case.by_agent["ana"].requests
    }
