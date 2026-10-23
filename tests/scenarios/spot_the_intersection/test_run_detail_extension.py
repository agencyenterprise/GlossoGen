"""The run-detail extras show each viewer's board as it was sent, and every submission.

One scripted two-team round is played with Team A submitting the answer, and its
extras are checked against the events it recorded: each seat's board lists the
lines that seat read, both teams' viewers of a seat share it, and the answer is
the one object every board holds.
"""

from pathlib import Path
from typing import NamedTuple

import pytest

from glossogen.models.event import AgentRegistered, SimulationEvent
from glossogen.run_detail_types import AgentDetail
from glossogen.scenarios.spot_the_intersection.board_certification import ObjectKind
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject, cell_label
from glossogen.scenarios.spot_the_intersection.board_rendering import render_board_line
from glossogen.scenarios.spot_the_intersection.events import (
    IntersectionSubmissionRecorded,
    SpotTheIntersectionRoundStarted,
)
from glossogen.scenarios.spot_the_intersection.run_detail_extension import (
    SpotTheIntersectionRunDetailExtension,
    SpotTheIntersectionRunExtras,
)
from glossogen.testing.scripted_agent import ScriptedTurn
from tests.scenarios.spot_the_intersection.conftest import (
    SCENARIO,
    TEAM_A,
    answer_of,
    one_round_scenario,
    play,
    submit,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)


class PlayedRound(NamedTuple):
    """A played round's events and the extras built from them."""

    events: list[SimulationEvent]
    extras: SpotTheIntersectionRunExtras


def agents_from(events: list[SimulationEvent]) -> dict[str, AgentDetail]:
    """The registered agents, as the run-detail reader passes them."""
    return {
        event.agent_id: AgentDetail(
            agent_id=event.agent_id,
            role_name=event.role_name,
            channel_ids=event.channel_ids,
            tool_names=event.tool_names,
            model=event.model,
            provider=event.provider,
            thinking=event.thinking,
            system_prompt=event.system_prompt,
        )
        for event in events
        if isinstance(event, AgentRegistered)
    }


async def played_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PlayedRound:
    """One two-team round in which every Team A viewer submits the answer."""
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {agent_id: [submit(obj=answer)] for agent_id in TEAM_A}
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    extras = SpotTheIntersectionRunDetailExtension().build_extras(
        events=result.events, agents_by_id=agents_from(events=result.events), messages=[]
    )
    return PlayedRound(events=result.events, extras=extras)


async def test_each_seat_shows_the_lines_its_viewers_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    played = await played_round(tmp_path=tmp_path, monkeypatch=monkeypatch)
    started = next(
        event for event in played.events if isinstance(event, SpotTheIntersectionRoundStarted)
    )

    (case,) = played.extras.cases
    assert case.round_number == 1
    assert [board.seat_number for board in case.boards] == list(range(1, started.team_size + 1))
    for board, lines in zip(case.boards, started.boards, strict=True):
        assert board.agent_ids == [f"viewer_a_{board.seat_number}", f"viewer_b_{board.seat_number}"]
        shown = [
            render_board_line(
                obj=BoardObject(shape=obj.shape, color=obj.color, column=obj.column, row=obj.row)
            )
            for obj in board.objects
        ]
        assert shown == lines
        assert all(obj.cell == cell_label(column=obj.column, row=obj.row) for obj in board.objects)


async def test_the_answer_is_the_only_object_on_every_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    played = await played_round(tmp_path=tmp_path, monkeypatch=monkeypatch)

    (case,) = played.extras.cases
    every_object = [obj for board in case.boards for obj in board.objects]
    on_every_board = {
        f"{obj.color} {obj.shape} at {obj.cell}"
        for obj in every_object
        if obj.boards_holding == case.team_size
    }
    answers = {
        f"{obj.color} {obj.shape} at {obj.cell}"
        for obj in every_object
        if obj.kind is ObjectKind.ANSWER
    }
    assert on_every_board == answers == {case.answer_line}


async def test_every_recorded_submission_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    played = await played_round(tmp_path=tmp_path, monkeypatch=monkeypatch)
    recorded = [
        event for event in played.events if isinstance(event, IntersectionSubmissionRecorded)
    ]

    assert sorted(submission.agent_id for submission in played.extras.submissions) == list(TEAM_A)
    assert all(submission.correct for submission in played.extras.submissions)
    assert [(s.agent_id, s.cell, s.team_characters) for s in played.extras.submissions] == [
        (event.agent_id, event.cell, event.team_characters) for event in recorded
    ]
