"""signal_game extension to the platform run-detail API.

Gives the round-detail panel both players' grids for each round, with each square's
colour, shape and fill split apart (or its word), every step each player took in the order the two
players' actions happened, the private reasoning on each, and how the round ended.
Both grids come back together, so the panel can show what neither player saw: which
items the two grids shared.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenarios.signal_game.board import item_parts
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGamePlayerFinished,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
)


class SignalGameCell(BaseModel):
    """A square of a grid, counted from 1 at the top left."""

    row: int
    col: int


class SignalGameItem(BaseModel):
    """What a square holds. A word square has only ``word``; any other has ``colour``,
    with ``shape`` None in a run whose squares have a colour only and ``fill`` None in a
    run without fills."""

    colour: str | None
    shape: str | None
    fill: str | None
    word: str | None


class SignalGameStep(BaseModel):
    """One accepted move. ``sequence`` orders both players' actions within the round."""

    sequence: int
    direction: str
    cell: SignalGameCell
    reasoning: str | None


class SignalGamePlayerSide(BaseModel):
    """One player's side of a round: its grid, its path and where it finished.

    ``end_sequence`` is the action number of the player's ``end_round`` and
    ``end_reasoning`` the sentence it gave with it; both are None when the player
    never called it. ``final_cell`` is the resolved square, or, in a round that
    has not resolved, where the player stands after its last move.
    """

    agent_id: str
    grid: list[list[SignalGameItem]]
    start: SignalGameCell
    steps: list[SignalGameStep]
    end_sequence: int | None
    end_reasoning: str | None
    final_cell: SignalGameCell
    final_item: SignalGameItem
    colour_order: list[str]
    shape_order: list[str]
    fill_order: list[str]


class SignalGameRound(BaseModel):
    """One round: both players' sides and the outcome.

    ``shared_items`` are the items on both grids, which no player is shown.
    ``chance`` is the probability that two squares picked at random, one per grid,
    hold the same item. ``success`` and ``trigger`` are None until the round resolves.
    """

    round_number: int
    grid_size: int
    partner_colours_visible: bool
    shared_items: list[SignalGameItem]
    chance: float
    success: bool | None
    trigger: str | None
    players: list[SignalGamePlayerSide]


class SignalGameRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for signal_game runs."""

    scenario_name: Literal["signal_game"] = "signal_game"
    cases: list[SignalGameRound]


def _cell(pair: tuple[int, int]) -> SignalGameCell:
    return SignalGameCell(row=pair[0], col=pair[1])


def _item(item: str) -> SignalGameItem:
    parts = item_parts(item=item)
    return SignalGameItem(colour=parts.colour, shape=parts.shape, fill=parts.fill, word=parts.word)


def _chance(first: list[list[str]], second: list[list[str]]) -> float:
    """The share of square pairs, one from each grid, that hold the same item."""
    first_items = [item for row in first for item in row]
    second_items = [item for row in second for item in row]
    pairs = len(first_items) * len(second_items)
    if pairs == 0:
        return 0.0
    matches = sum(1 for one in first_items for other in second_items if one == other)
    return matches / pairs


def _shared_items(grids: list[list[list[str]]]) -> list[SignalGameItem]:
    """The items on every grid, in the order the first grid lists them."""
    if not grids:
        return []
    others = [{item for row in grid for item in row} for grid in grids[1:]]
    seen: list[str] = []
    for row in grids[0]:
        for item in row:
            if item not in seen and all(item in other for other in others):
                seen.append(item)
    return [_item(item=item) for item in seen]


def _player_side(
    agent_id: str,
    started: SignalGameRoundStarted,
    moves: list[SignalGameMoveMade],
    finish: SignalGamePlayerFinished | None,
    end_sequence: int | None,
    resolved: SignalGameRoundResolved | None,
) -> SignalGamePlayerSide:
    """One player's grid, path and finish, from the events of one round."""
    grid = started.grids[agent_id]
    final_pair = started.start_squares[agent_id]
    if moves:
        final_pair = moves[-1].to_square
    if resolved is not None:
        final_pair = resolved.final_squares[agent_id]
    final_cell = _cell(pair=final_pair)
    end_reasoning: str | None = None
    if finish is not None:
        end_reasoning = finish.reasoning
    colour_order: list[str] = []
    if started.colour_orders is not None:
        colour_order = list(started.colour_orders.get(agent_id, []))
    shape_order: list[str] = []
    if started.shape_orders is not None:
        shape_order = list(started.shape_orders.get(agent_id, []))
    fill_order: list[str] = []
    if started.fill_orders is not None:
        fill_order = list(started.fill_orders.get(agent_id, []))
    return SignalGamePlayerSide(
        agent_id=agent_id,
        grid=[[_item(item=item) for item in row] for row in grid],
        start=_cell(pair=started.start_squares[agent_id]),
        steps=[
            SignalGameStep(
                sequence=move.sequence,
                direction=move.direction,
                cell=_cell(pair=move.to_square),
                reasoning=move.reasoning,
            )
            for move in moves
        ],
        end_sequence=end_sequence,
        end_reasoning=end_reasoning,
        final_cell=final_cell,
        final_item=_item(item=grid[final_cell.row - 1][final_cell.col - 1]),
        colour_order=colour_order,
        shape_order=shape_order,
        fill_order=fill_order,
    )


def _end_sequences(actions: list[SignalGameMoveMade | SignalGamePlayerFinished]) -> dict[str, int]:
    """The action number each player's ``end_round`` took.

    The round numbers moves and ``end_round`` calls in one sequence, but the finish
    event does not log its number, so it is one past the action logged before it.
    """
    numbers: dict[str, int] = {}
    last_sequence = 0
    for action in actions:
        if isinstance(action, SignalGameMoveMade):
            last_sequence = action.sequence
        else:
            last_sequence += 1
            numbers[action.agent_id] = last_sequence
    return numbers


def _build_round(
    started: SignalGameRoundStarted,
    actions: list[SignalGameMoveMade | SignalGamePlayerFinished],
    resolved: SignalGameRoundResolved | None,
) -> SignalGameRound:
    """Both players' sides of one round and its outcome."""
    end_sequences = _end_sequences(actions=actions)
    players = [
        _player_side(
            agent_id=agent_id,
            started=started,
            moves=[
                action
                for action in actions
                if isinstance(action, SignalGameMoveMade) and action.agent_id == agent_id
            ],
            finish=next(
                (
                    action
                    for action in actions
                    if isinstance(action, SignalGamePlayerFinished) and action.agent_id == agent_id
                ),
                None,
            ),
            end_sequence=end_sequences.get(agent_id),
            resolved=resolved,
        )
        for agent_id in sorted(started.grids)
    ]
    grids = [started.grids[agent_id] for agent_id in sorted(started.grids)]
    chance = 0.0
    grid_size = 0
    if grids:
        grid_size = len(grids[0])
    if len(grids) == 2:
        chance = _chance(first=grids[0], second=grids[1])
    success: bool | None = None
    trigger: str | None = None
    if resolved is not None:
        success = resolved.success
        trigger = resolved.trigger
    return SignalGameRound(
        round_number=started.round_number,
        grid_size=grid_size,
        partner_colours_visible=started.partner_colours_visible,
        shared_items=_shared_items(grids=grids),
        chance=chance,
        success=success,
        trigger=trigger,
        players=players,
    )


class SignalGameRunDetailExtension(ScenarioRunDetailExtension):
    """signal_game hook into :class:`RunDetailResponse.scenario_extras`."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = SignalGameRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],  # noqa: ARG002 — protocol-required
        messages: list[ChannelMessage],  # noqa: ARG002 — protocol-required
    ) -> SignalGameRunExtras:
        started_by_round: dict[int, SignalGameRoundStarted] = {}
        actions_by_round: dict[int, list[SignalGameMoveMade | SignalGamePlayerFinished]] = {}
        resolved_by_round: dict[int, SignalGameRoundResolved] = {}
        for event in events:
            if isinstance(event, SignalGameRoundStarted):
                # A resumed run starts an unfinished round again from its start squares,
                # numbering actions from 1: only the actions after the last start count.
                started_by_round[event.round_number] = event
                actions_by_round[event.round_number] = []
            elif isinstance(event, SignalGameMoveMade | SignalGamePlayerFinished):
                actions_by_round.setdefault(event.round_number, []).append(event)
            elif isinstance(event, SignalGameRoundResolved):
                resolved_by_round[event.round_number] = event
        return SignalGameRunExtras(
            cases=[
                _build_round(
                    started=started,
                    actions=actions_by_round.get(round_number, []),
                    resolved=resolved_by_round.get(round_number),
                )
                for round_number, started in sorted(started_by_round.items())
            ]
        )
