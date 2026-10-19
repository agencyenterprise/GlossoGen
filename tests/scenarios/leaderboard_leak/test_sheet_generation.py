"""Sheets and tasks drawn from the seed: where each task's ID is, and that IDs never repeat."""

from glossogen.scenarios.leaderboard_leak.ids import (
    ID_PREFIX,
    OTHER_TEAM,
    TEAM_IDS,
    VALUE_MAX,
    VALUE_MIN,
)
from glossogen.scenarios.leaderboard_leak.sheet_generation import RoundSheets, generate_rounds

ROUNDS = 20
SHEET_ENTRIES = 8


def drawn() -> list[RoundSheets]:
    return generate_rounds(seed=42, round_count=ROUNDS, sheet_entries=SHEET_ENTRIES, recorded={})


def test_the_same_seed_draws_the_same_rounds() -> None:
    assert drawn() == drawn()
    other = generate_rounds(seed=7, round_count=ROUNDS, sheet_entries=SHEET_ENTRIES, recorded={})
    assert other != drawn()


def test_tasks_1_to_3_are_on_the_own_sheet_and_task_4_only_on_the_other() -> None:
    for sheets in drawn():
        for team_id in TEAM_IDS:
            team = sheets.team(team_id=team_id)
            other = sheets.team(team_id=OTHER_TEAM[team_id])
            assert len(team.sheet) == SHEET_ENTRIES
            assert len(set(team.task_ids)) == 4
            for entry_id in team.task_ids[:3]:
                assert team.value_of(entry_id=entry_id) is not None
            bonus_id = team.task_ids[3]
            assert team.value_of(entry_id=bonus_id) is None
            assert other.value_of(entry_id=bonus_id) is not None
            assert bonus_id not in other.task_ids


def test_no_id_repeats_within_a_run_and_every_id_is_readable() -> None:
    seen: list[str] = []
    for sheets in drawn():
        for team in sheets.teams:
            for entry in team.sheet:
                seen.append(entry.entry_id)
                body = entry.entry_id.removeprefix(ID_PREFIX)
                assert entry.entry_id.startswith(ID_PREFIX)
                assert len(body) == 3
                assert not body.isdigit()
                assert "I" not in body and "O" not in body
                assert VALUE_MIN <= int(entry.value) <= VALUE_MAX
    assert len(seen) == len(set(seen)) == ROUNDS * len(TEAM_IDS) * SHEET_ENTRIES


def test_a_recorded_round_is_kept_and_the_rest_avoid_its_ids() -> None:
    fresh = generate_rounds(seed=42, round_count=3, sheet_entries=SHEET_ENTRIES, recorded={})
    recorded = generate_rounds(seed=99, round_count=1, sheet_entries=SHEET_ENTRIES, recorded={})[0]

    kept = generate_rounds(
        seed=42, round_count=3, sheet_entries=SHEET_ENTRIES, recorded={1: recorded}
    )

    assert kept[0] == recorded
    later_ids = kept[1].entry_ids() | kept[2].entry_ids()
    assert not later_ids & recorded.entry_ids()
    same_prefix = generate_rounds(
        seed=42, round_count=3, sheet_entries=SHEET_ENTRIES, recorded={1: fresh[0]}
    )
    assert same_prefix == fresh
