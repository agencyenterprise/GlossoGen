"""leaderboard_leak's implementation of ``build_communication_rounds``.

A round's messages are its team-channel and lobby messages and every comment
submitted, in log order. A comment is listed on the pseudo-channel
``comment:task<N>``, since it reached the other team through the submission log
rather than a channel. The ground truth is both sheets, each team's tasks, and
which sheet holds each team's task 4 ID.
"""

from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.scenarios.leaderboard_leak.evaluation.round_comments import (
    LoggedRound,
    logged_rounds,
)
from glossogen.scenarios.leaderboard_leak.events import (
    LeaderboardLeakAnswerSubmitted,
    SheetEntryRecord,
)
from glossogen.scenarios.leaderboard_leak.ids import (
    LOBBY_CHANNEL_ID,
    OTHER_TEAM,
    TEAM_CHANNEL_IDS,
    TEAM_NAMES,
)
from glossogen.template_renderer import TemplateRenderer

PROMPTS_DIR = Path(__file__).parent / "prompts"
HEADER_TEMPLATE = "communication_header.jinja"
GROUND_TRUTH_TEMPLATE = "communication_ground_truth.jinja"

_CHANNELS = frozenset({*TEAM_CHANNEL_IDS.values(), LOBBY_CHANNEL_ID})


class TeamTruth(NamedTuple):
    """One team's part of a round's ground truth."""

    name: str
    sheet: list[SheetEntryRecord]
    task_ids: list[str]
    bonus_id: str
    bonus_value: str
    holder_name: str


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """One view per started round: its messages and comments, and both sheets."""
    renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])
    views: list[CommunicationRoundView] = []
    for logged in logged_rounds(events=events):
        variables: dict[str, object] = {"teams": _team_truths(logged=logged)}
        views.append(
            CommunicationRoundView(
                round_number=logged.started.round_number,
                header=renderer.render(
                    template_name=HEADER_TEMPLATE, template_variables=variables
                ).strip(),
                ground_truth_block=renderer.render(
                    template_name=GROUND_TRUTH_TEMPLATE, template_variables=variables
                ).strip(),
                messages=_lines_in_round(events=events, round_number=logged.started.round_number),
            )
        )
    return views


def _team_truths(logged: LoggedRound) -> list[TeamTruth]:
    """Each team's sheet and tasks, and where its task 4 ID is held."""
    truths: list[TeamTruth] = []
    for team in logged.started.teams:
        bonus_id = team.task_ids[-1]
        truths.append(
            TeamTruth(
                name=TEAM_NAMES[team.team_id],
                sheet=team.sheet,
                task_ids=team.task_ids,
                bonus_id=bonus_id,
                bonus_value=logged.value_on_sheets(entry_id=bonus_id),
                holder_name=TEAM_NAMES[OTHER_TEAM[team.team_id]],
            )
        )
    return truths


def _lines_in_round(
    events: list[SimulationEvent], round_number: int
) -> list[CommunicationMessageLine]:
    """``round_number``'s channel messages and comments, in log order."""
    lines: list[CommunicationMessageLine] = []
    for event in events:
        if event.round_number != round_number:
            continue
        if isinstance(event, MessageSent) and event.message.channel_id in _CHANNELS:
            lines.append(
                CommunicationMessageLine(
                    sender_agent_id=event.message.sender_agent_id,
                    channel_id=event.message.channel_id,
                    text=event.message.text,
                )
            )
        elif isinstance(event, LeaderboardLeakAnswerSubmitted):
            lines.append(
                CommunicationMessageLine(
                    sender_agent_id=event.agent_id,
                    channel_id=f"comment:task{event.task}",
                    text=event.comment,
                )
            )
    return lines
