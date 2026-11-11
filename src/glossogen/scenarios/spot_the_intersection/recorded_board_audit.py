"""Certify a recorded run on the boards its viewers were actually sent.

Board generation certifies every round before it is played. This checks the
run afterwards, from its event log alone. For every round it requires:

- each viewer's round injection carries the board the round recorded for its
  seat, line for line;
- seat ``i`` of each team was sent the same board;
- the boards as sent certify against the round's recorded declaration.

A team with a viewer who was sent no board is not certified, since the missing
board is already reported and certifying the rest would report what follows
from it.

It also lists the rounds whose recorded boards differ from what this checkout
generates for the run's seed and knobs, and the rounds this checkout cannot
generate at all. Those rounds were certified when they were played, but a cohort
mixing runs from before and after a change to generation did not play identical
boards under the same seed.
"""

from collections.abc import Sequence
from typing import NamedTuple

from glossogen.models.event import InjectionDelivered, SimulationEvent
from glossogen.run_storage.event_log_reader import extract_scenario_config
from glossogen.scenarios.spot_the_intersection.board_certification import certify_boards
from glossogen.scenarios.spot_the_intersection.board_generation import (
    BoardGenerationError,
    generate_round,
)
from glossogen.scenarios.spot_the_intersection.events import SpotTheIntersectionRoundStarted
from glossogen.scenarios.spot_the_intersection.injection_rendering import (
    BOARD_HEADER,
    board_lines_from_injection,
)
from glossogen.scenarios.spot_the_intersection.knobs import SpotTheIntersectionKnobs
from glossogen.scenarios.spot_the_intersection.round_event_conversion import declared_from_event
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario
from glossogen.scenarios.spot_the_intersection.seats import Seat, seats_by_agent_id
from glossogen.scenarios.spot_the_intersection.team_declaration import intersection_teams


class AuditFinding(NamedTuple):
    """One problem found in one round."""

    round_number: int
    problem: str


class RunAudit(NamedTuple):
    """What auditing one run found.

    ``findings`` fail the audit. ``regenerated_differently`` and
    ``not_regenerated`` are notes about this checkout's generator, not about the
    run.
    """

    rounds_audited: int
    findings: tuple[AuditFinding, ...]
    regenerated_differently: tuple[int, ...]
    not_regenerated: tuple[AuditFinding, ...]


def audit_events(events: Sequence[SimulationEvent]) -> RunAudit:
    """Audit every round a run's events record."""
    config = SpotTheIntersectionScenario.strip_unknown_knobs(
        config=extract_scenario_config(events=list(events))
    )
    knobs = SpotTheIntersectionKnobs.model_validate(config)
    seats = seats_by_agent_id(teams=intersection_teams(knobs=knobs))
    started = {
        event.round_number: event
        for event in events
        if isinstance(event, SpotTheIntersectionRoundStarted)
    }
    delivered = _delivered_boards(events=events)
    findings: list[AuditFinding] = []
    regenerated_differently: list[int] = []
    not_regenerated: list[AuditFinding] = []
    for round_number, round_started in sorted(started.items()):
        findings.extend(
            _round_findings(
                round_started=round_started,
                delivered=delivered.get(round_number, {}),
                seats=seats,
                near_misses=knobs.near_misses,
            )
        )
        try:
            regenerated = generate_round(
                seed=knobs.seed, round_number=round_number, settings=knobs.board_settings()
            )
        except BoardGenerationError as error:
            not_regenerated.append(AuditFinding(round_number=round_number, problem=str(error)))
            continue
        if [list(lines) for lines in regenerated.board_lines] != round_started.boards:
            regenerated_differently.append(round_number)
    return RunAudit(
        rounds_audited=len(started),
        findings=tuple(findings),
        regenerated_differently=tuple(regenerated_differently),
        not_regenerated=tuple(not_regenerated),
    )


def _delivered_boards(events: Sequence[SimulationEvent]) -> dict[int, dict[str, list[list[str]]]]:
    """Every board each agent was sent, by round; a resume can deliver one twice."""
    boards: dict[int, dict[str, list[list[str]]]] = {}
    for event in events:
        if not isinstance(event, InjectionDelivered) or BOARD_HEADER not in event.text:
            continue
        by_agent = boards.setdefault(event.round_number, {})
        by_agent.setdefault(event.agent_id, []).append(board_lines_from_injection(text=event.text))
    return boards


def _round_findings(
    round_started: SpotTheIntersectionRoundStarted,
    delivered: dict[str, list[list[str]]],
    seats: dict[str, Seat],
    near_misses: bool,
) -> list[AuditFinding]:
    """Check one round's deliveries against its record, then certify what was sent."""
    round_number = round_started.round_number
    findings: list[AuditFinding] = []
    sent_by_team: dict[str, list[list[str] | None]] = {}
    for agent_id, seat in sorted(
        seats.items(), key=lambda item: (item[1].team_id, item[1].board_index)
    ):
        sent = sent_by_team.setdefault(seat.team_id, [None] * len(round_started.boards))
        copies = delivered.get(agent_id, [])
        recorded = round_started.boards[seat.board_index]
        if not copies:
            findings.append(
                AuditFinding(round_number=round_number, problem=f"{agent_id} got no board")
            )
            continue
        if any(copy != recorded for copy in copies):
            findings.append(
                AuditFinding(
                    round_number=round_number,
                    problem=f"{agent_id} was sent a board other than seat {seat.board_index + 1}'s",
                )
            )
        sent[seat.board_index] = copies[0]
    complete = _fully_delivered(sent_by_team=sent_by_team)
    teams = list(complete.values())
    if any(team != teams[0] for team in teams[1:]):
        findings.append(
            AuditFinding(round_number=round_number, problem="the teams were sent different boards")
        )
    declared = declared_from_event(event=round_started)
    for team_id, boards in complete.items():
        result = certify_boards(
            board_lines=boards,
            grid_size=round_started.grid_size,
            declared=declared,
            require_every_board=near_misses,
        )
        findings.extend(
            AuditFinding(
                round_number=round_number,
                problem=f"{team_id} boards as sent: {failure.reason.value}: {failure.detail}",
            )
            for failure in result.failures
        )
    return findings


def _fully_delivered(
    sent_by_team: dict[str, list[list[str] | None]],
) -> dict[str, list[list[str]]]:
    """The teams every one of whose viewers was sent a board, boards in seat order."""
    complete: dict[str, list[list[str]]] = {}
    for team_id, sent in sent_by_team.items():
        boards = [board for board in sent if board is not None]
        if len(boards) == len(sent):
            complete[team_id] = boards
    return complete
