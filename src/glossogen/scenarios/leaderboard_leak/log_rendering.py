"""The submission log a closed task returns to each agent.

Both teams are listed in ``TEAM_IDS`` order whoever reads the log, each with its
correct count, its points for the task and its total. Each member's comment is
listed under its team, except that under ``comments_visible=false`` a team's log
leaves out the other team's comments. A task closed by the round's end says so.
"""

from typing import NamedTuple

from glossogen.scenarios.leaderboard_leak.ids import SUBMISSION_LOG_TEMPLATE, TEAM_NAMES
from glossogen.scenarios.leaderboard_leak.world import MemberComment, TaskResult
from glossogen.template_renderer import TemplateRenderer


class LogTeamRow(NamedTuple):
    """One team's lines in a submission log. ``comments`` is None when they are withheld."""

    name: str
    correct_count: int
    members: int
    points: int
    total: int
    comments: tuple[MemberComment, ...] | None


def render_submission_log(
    renderer: TemplateRenderer, result: TaskResult, viewer_team_id: str, comments_visible: bool
) -> str:
    """``result`` as ``viewer_team_id``'s members read it."""
    rows: list[LogTeamRow] = []
    for team in result.teams:
        comments: tuple[MemberComment, ...] | None = team.comments
        if not comments_visible and team.team_id != viewer_team_id:
            comments = None
        rows.append(
            LogTeamRow(
                name=TEAM_NAMES[team.team_id],
                correct_count=team.correct_count,
                members=len(team.comments),
                points=team.points,
                total=team.total,
                comments=comments,
            )
        )
    return renderer.render(
        template_name=SUBMISSION_LOG_TEMPLATE,
        template_variables={
            "round_number": result.round_number,
            "task": result.task,
            "teams": rows,
            "round_ended": not result.complete,
        },
    )
