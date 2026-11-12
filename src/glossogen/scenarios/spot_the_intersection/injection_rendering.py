"""Per-round and postmortem injections, and reading a board back out of one.

A viewer's round injection carries the previous round's result, the budget when
one is set (worded for the run's messaging and character rule), and its own
board, one line per object. ``board_lines_from_injection``
is the inverse the audit uses: it recovers the board exactly as delivered, so a
recorded run can be certified on what its viewers were actually sent.
"""

from glossogen.scenarios.spot_the_intersection.ids import (
    POSTMORTEM_INJECTION_TEMPLATE,
    VIEWER_INJECTION_TEMPLATE,
)
from glossogen.scenarios.spot_the_intersection.messaging import Messaging
from glossogen.scenarios.spot_the_intersection.world_state import (
    IntersectionOutcome,
    TeamCharacters,
)
from glossogen.template_renderer import TemplateRenderer

BOARD_HEADER = "YOUR BOARD"
_BOARD_LINE_PREFIX = "- "


def render_round_injection(
    renderer: TemplateRenderer,
    round_number: int,
    board_lines: tuple[str, ...],
    previous_outcome: IntersectionOutcome | None,
    round_time_budget_seconds: int,
    messaging: Messaging,
    team_characters: TeamCharacters,
) -> str:
    """The round-start injection for one viewer."""
    return renderer.render(
        template_name=VIEWER_INJECTION_TEMPLATE,
        template_variables={
            "round_number": round_number,
            "board_header": BOARD_HEADER,
            "board_lines": list(board_lines),
            "previous_outcome": previous_outcome,
            "round_time_budget_seconds": round_time_budget_seconds,
            "one_to_one": messaging == Messaging.ONE_TO_ONE,
            "team_characters": team_characters.value,
        },
    )


def render_postmortem_injection(
    renderer: TemplateRenderer,
    round_number: int,
    previous_outcome: IntersectionOutcome | None,
    team_characters: TeamCharacters,
) -> str:
    """The discussion-phase injection for one viewer."""
    return renderer.render(
        template_name=POSTMORTEM_INJECTION_TEMPLATE,
        template_variables={
            "round_number": round_number,
            "previous_outcome": previous_outcome,
            "team_characters": team_characters.value,
        },
    )


def board_lines_from_injection(text: str) -> list[str]:
    """The board lines a round injection delivered, in order.

    Raises ``ValueError`` when the injection carries no board header.
    """
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith(BOARD_HEADER)]
    if len(starts) != 1:
        raise ValueError(f"expected one {BOARD_HEADER!r} header, found {len(starts)}")
    board: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if not line.startswith(_BOARD_LINE_PREFIX):
            break
        board.append(line[len(_BOARD_LINE_PREFIX) :])
    return board
