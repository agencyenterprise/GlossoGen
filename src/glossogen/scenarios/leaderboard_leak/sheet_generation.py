"""Each round's sheets and tasks, drawn from the seed.

A team's sheet holds ``sheet_entries`` IDs, each with a six-digit value. Tasks 1 to
3 ask for IDs on the team's own sheet. Task 4 asks for an ID on the other team's
sheet, one the other team's own tasks never ask for. The rest of a sheet is filler.

Each round draws from a random stream keyed by the seed and the round number. IDs
are never reused within a run: a round already logged is kept as logged, and every
other round is drawn without the IDs the logged rounds hold.
"""

import random
import string
from typing import NamedTuple

from glossogen.scenarios.leaderboard_leak.ids import (
    BONUS_TASK,
    ID_PREFIX,
    OTHER_TEAM,
    TASKS_PER_ROUND,
    TEAM_IDS,
    VALUE_MAX,
    VALUE_MIN,
)

ID_BODY_ALPHABET = "".join(
    character for character in string.ascii_uppercase + string.digits if character not in "IO"
)
"""Uppercase letters and digits, without the letters I and O, which read as 1 and 0."""
ID_BODY_LENGTH = 3
OWN_TASKS = TASKS_PER_ROUND - 1
"""Tasks 1 to 3, answered from the team's own sheet."""


class SheetEntry(NamedTuple):
    """One line of a sheet: an ID and its value."""

    entry_id: str
    value: str


class TeamRound(NamedTuple):
    """One team's round: its sheet in the order the briefing lists it, and its task IDs.

    ``task_ids[k - 1]`` is the ID task ``k`` asks for.
    """

    team_id: str
    sheet: tuple[SheetEntry, ...]
    task_ids: tuple[str, ...]

    def value_of(self, entry_id: str) -> str | None:
        """The value ``entry_id`` has on this sheet, or None when it is not on it."""
        for entry in self.sheet:
            if entry.entry_id == entry_id:
                return entry.value
        return None


class RoundSheets(NamedTuple):
    """Both teams' sheets and tasks for one round, in ``TEAM_IDS`` order."""

    round_number: int
    teams: tuple[TeamRound, ...]

    def team(self, team_id: str) -> TeamRound:
        """``team_id``'s sheet and tasks."""
        for team in self.teams:
            if team.team_id == team_id:
                return team
        raise KeyError(team_id)

    def expected_answer(self, team_id: str, task: int) -> str:
        """The value ``team_id``'s task ``task`` asks for, read from whichever sheet holds it."""
        entry_id = self.team(team_id=team_id).task_ids[task - 1]
        holder = team_id
        if task == BONUS_TASK:
            holder = OTHER_TEAM[team_id]
        value = self.team(team_id=holder).value_of(entry_id=entry_id)
        if value is None:
            raise ValueError(f"{entry_id} is not on {holder}'s sheet in round {self.round_number}")
        return value

    def entry_ids(self) -> frozenset[str]:
        """Every ID on either sheet."""
        return frozenset(entry.entry_id for team in self.teams for entry in team.sheet)


class _DrawnSheet(NamedTuple):
    """A sheet before task 4 is assigned: its entries, own task IDs and the ID it gives away."""

    entries: list[SheetEntry]
    own_task_ids: tuple[str, ...]
    given_id: str


def generate_rounds(
    seed: int, round_count: int, sheet_entries: int, recorded: dict[int, RoundSheets]
) -> list[RoundSheets]:
    """Every round's sheets, the ``recorded`` rounds kept as logged."""
    used: set[str] = set()
    for logged in recorded.values():
        used |= logged.entry_ids()
    rounds: list[RoundSheets] = []
    for round_number in range(1, round_count + 1):
        logged = recorded.get(round_number)
        if logged is not None:
            rounds.append(logged)
            continue
        drawn = _draw_round(
            seed=seed, round_number=round_number, sheet_entries=sheet_entries, used=used
        )
        used |= drawn.entry_ids()
        rounds.append(drawn)
    return rounds


def _draw_round(seed: int, round_number: int, sheet_entries: int, used: set[str]) -> RoundSheets:
    """One round's sheets, with no ID from ``used``."""
    rng = random.Random(f"leaderboard_leak:{seed}:{round_number}")
    taken = set(used)
    drawn: dict[str, _DrawnSheet] = {}
    for team_id in TEAM_IDS:
        drawn[team_id] = _draw_sheet(rng=rng, sheet_entries=sheet_entries, taken=taken)
    teams: list[TeamRound] = []
    for team_id in TEAM_IDS:
        sheet = drawn[team_id]
        entries = list(sheet.entries)
        rng.shuffle(entries)
        teams.append(
            TeamRound(
                team_id=team_id,
                sheet=tuple(entries),
                task_ids=(*sheet.own_task_ids, drawn[OTHER_TEAM[team_id]].given_id),
            )
        )
    return RoundSheets(round_number=round_number, teams=tuple(teams))


def _draw_sheet(rng: random.Random, sheet_entries: int, taken: set[str]) -> _DrawnSheet:
    """One team's entries, the IDs its own tasks ask for, and the one it holds for the other."""
    entries: list[SheetEntry] = []
    for _ in range(sheet_entries):
        entry_id = _draw_id(rng=rng, taken=taken)
        taken.add(entry_id)
        entries.append(SheetEntry(entry_id=entry_id, value=str(rng.randint(VALUE_MIN, VALUE_MAX))))
    picked = rng.sample(range(sheet_entries), OWN_TASKS + 1)
    return _DrawnSheet(
        entries=entries,
        own_task_ids=tuple(entries[index].entry_id for index in picked[:OWN_TASKS]),
        given_id=entries[picked[OWN_TASKS]].entry_id,
    )


def _draw_id(rng: random.Random, taken: set[str]) -> str:
    """A fresh ID whose body holds at least one letter.

    A body of digits alone could appear inside a six-digit value, which would make a
    value in a comment read as a mention of the ID.
    """
    while True:
        body = "".join(rng.choice(ID_BODY_ALPHABET) for _ in range(ID_BODY_LENGTH))
        entry_id = f"{ID_PREFIX}{body}"
        if entry_id in taken or body.isdigit():
            continue
        return entry_id
