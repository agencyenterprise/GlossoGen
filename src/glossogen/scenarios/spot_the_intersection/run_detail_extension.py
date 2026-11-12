"""spot_the_intersection extension to the platform run-detail API.

Gives the round-detail panel each round's boards as the viewers read them, every
object tagged with what it was placed for and how many boards hold it, and every
accepted ``submit_object`` call. Each team's outcome is the platform's own
``round_results``, so it is not repeated here.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
    mirror_events,
)
from glossogen.scenario_contract.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenarios.spot_the_intersection.board_certification import ObjectKind
from glossogen.scenarios.spot_the_intersection.board_model import cell_label
from glossogen.scenarios.spot_the_intersection.board_rendering import parse_board_line
from glossogen.scenarios.spot_the_intersection.events import (
    IntersectionObjectRecord,
    IntersectionSubmissionRecorded,
    SpotTheIntersectionRoundStarted,
)
from glossogen.scenarios.spot_the_intersection.ids import TEAM_A_ID, TEAM_B_ID, TEAM_SOLO_ID
from glossogen.scenarios.spot_the_intersection.seats import viewer_id

_TEAM_IDS = (TEAM_SOLO_ID, TEAM_A_ID, TEAM_B_ID)


class IntersectionBoardObject(BaseModel):
    """One object on one viewer's board.

    ``column`` and ``row`` count from 0, with ``A1`` at the top left. ``kind`` is
    what the generator placed the object for, and ``boards_holding`` is how many
    of the round's boards hold the same object in the same cell.
    """

    shape: str
    color: str
    cell: str
    column: int
    row: int
    kind: ObjectKind
    boards_holding: int


class IntersectionSeatBoard(BaseModel):
    """The board of seat ``seat_number`` and the viewers who read it, one per team."""

    seat_number: int
    agent_ids: list[str]
    objects: list[IntersectionBoardObject]


class IntersectionRoundCase(BaseModel):
    """One round's boards, seat by seat, and the object every board holds.

    ``decoy_count`` is how many decoy objects the round planted, each on more
    than one board and fewer than all.
    """

    round_number: int
    grid_size: int
    team_size: int
    board_size: int
    decoy_count: int
    answer_line: str
    boards: list[IntersectionSeatBoard]


class IntersectionSubmission(BaseModel):
    """One accepted ``submit_object`` call.

    ``team_characters`` is the team's charge under the run's ``team_characters``
    knob when the viewer submitted.
    """

    round_number: int
    agent_id: str
    team_id: str
    seat_number: int
    shape: str
    color: str
    cell: str
    correct: bool
    team_characters: int


class SpotTheIntersectionRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for spot_the_intersection runs."""

    scenario_name: Literal["spot_the_intersection"] = "spot_the_intersection"
    cases: list[IntersectionRoundCase]
    submissions: list[IntersectionSubmission]


def _seat_holders(seat_index: int, agent_ids: set[str]) -> list[str]:
    """The registered viewers holding seat ``seat_index`` (from 0), team by team."""
    holders: list[str] = []
    for team_id in _TEAM_IDS:
        agent_id = viewer_id(team_id=team_id, index=seat_index)
        if agent_id in agent_ids:
            holders.append(agent_id)
    return holders


def _board_objects(
    lines: list[str],
    grid_size: int,
    records_by_key: dict[tuple[str, str, str], IntersectionObjectRecord],
) -> list[IntersectionBoardObject]:
    """Read a board's lines back and tag each object with its declared record.

    Raises ``ValueError`` for a line naming an object the round never declared,
    which certification rules out for any round that was played.
    """
    objects: list[IntersectionBoardObject] = []
    for line in lines:
        obj = parse_board_line(line=line, grid_size=grid_size)
        cell = cell_label(column=obj.column, row=obj.row)
        record = records_by_key.get((obj.shape, obj.color, cell))
        if record is None:
            raise ValueError(f"board line {line!r} names an object the round did not declare")
        objects.append(
            IntersectionBoardObject(
                shape=obj.shape,
                color=obj.color,
                cell=cell,
                column=obj.column,
                row=obj.row,
                kind=record.kind,
                boards_holding=len(record.seat_numbers),
            )
        )
    return objects


def _build_case(
    event: SpotTheIntersectionRoundStarted, agent_ids: set[str]
) -> IntersectionRoundCase:
    records_by_key = {(record.shape, record.color, record.cell): record for record in event.objects}
    boards = [
        IntersectionSeatBoard(
            seat_number=seat_index + 1,
            agent_ids=_seat_holders(seat_index=seat_index, agent_ids=agent_ids),
            objects=_board_objects(
                lines=lines, grid_size=event.grid_size, records_by_key=records_by_key
            ),
        )
        for seat_index, lines in enumerate(event.boards)
    ]
    return IntersectionRoundCase(
        round_number=event.round_number,
        grid_size=event.grid_size,
        team_size=event.team_size,
        board_size=event.board_size,
        decoy_count=event.decoy_count,
        answer_line=event.answer_line,
        boards=boards,
    )


class SpotTheIntersectionRunDetailExtension(ScenarioRunDetailExtension):
    """spot_the_intersection hook into :class:`RunDetailResponse.scenario_extras`."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = SpotTheIntersectionRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],  # noqa: ARG002 — protocol-required
    ) -> SpotTheIntersectionRunExtras:
        agent_ids = set(agents_by_id)
        return SpotTheIntersectionRunExtras(
            cases=[
                _build_case(event=event, agent_ids=agent_ids)
                for event in events
                if isinstance(event, SpotTheIntersectionRoundStarted)
            ],
            submissions=mirror_events(
                events=events,
                event_cls=IntersectionSubmissionRecorded,
                mirror_cls=IntersectionSubmission,
            ),
        )
