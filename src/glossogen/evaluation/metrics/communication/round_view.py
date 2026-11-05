"""Per-round transcript + scenario-rendered ground truth shared by the three passes.

The open-coding metric (pass 1) and the feature-presence metric (pass
3) feed the LLM judge the same view of each round so their outputs are
commensurable: a one-line ``header`` identifying the round, a
``ground_truth_block`` rendered by the scenario describing what each
agent saw and what the round wanted, and the ordered list of messages
on the scenario's primary channel.

Scenarios build the per-round view through the
``SimulationScenario.build_communication_rounds`` hook. The hook is
the only scenario-specific surface in this pipeline. The metrics and
prompts read ``CommunicationRoundView`` and never branch on scenario
name. ``message_lines_by_round`` groups a scenario's primary-channel
messages into the lines a view carries, and ``round_views_with_case`` joins
them with the event a scenario logs at each round start to describe its case.
"""

from collections.abc import Callable
from typing import NamedTuple

from glossogen.evaluation.metric_core.primary_channel_messages import group_messages_by_round
from glossogen.models.event import SimulationEvent
from glossogen.models.event_base import EventBase


class CommunicationMessageLine(NamedTuple):
    """One message on the scenario's primary channel rendered for the judge prompt."""

    sender_agent_id: str
    channel_id: str
    text: str


class CommunicationRoundView(NamedTuple):
    """One round's transcript + scenario-rendered ground truth.

    ``header`` is the one-line row anchor the prompts use to tag each
    round (e.g. ``"hard case · target Stack 2 Tier 3"`` for the yard
    scenario, ``"stellar_compass_failure"`` for veyru). Free-form text;
    the prompt simply echoes it.

    ``ground_truth_block`` is a scenario-rendered multiline block that
    describes what each agent could see this round and what the round
    wanted (information asymmetry, target outcome). The scenario owns
    this rendering so the judge sees scenario-appropriate framing
    without the metric code knowing any scenario specifics.

    ``messages`` is the ordered list of messages on the scenario's
    primary channel (or its per-team variants) for this round.
    """

    round_number: int
    header: str
    ground_truth_block: str
    messages: list[CommunicationMessageLine]


def message_lines_by_round(
    events: list[SimulationEvent],
    channel_ids: frozenset[str],
) -> dict[int, list[CommunicationMessageLine]]:
    """Map round number to that round's messages on ``channel_ids``, in log order.

    Each line carries the transmitted text, as the channel delivered it. Rounds with
    no message on ``channel_ids`` have no entry.
    """
    return {
        round_messages.round_number: [
            CommunicationMessageLine(
                sender_agent_id=event.message.sender_agent_id,
                channel_id=event.message.channel_id,
                text=event.message.text,
            )
            for event in round_messages.messages
        ]
        for round_messages in group_messages_by_round(events=events, channel_ids=channel_ids)
    }


def round_views_with_case[Case: EventBase](
    events: list[SimulationEvent],
    case_event_cls: type[Case],
    channel_ids: frozenset[str],
    render_header: Callable[[Case], str],
    render_ground_truth_block: Callable[[Case], str],
    missing_case_header: str,
    missing_case_ground_truth_block: str,
) -> list[CommunicationRoundView]:
    """One view per round that logged a ``case_event_cls`` event or a message on ``channel_ids``.

    Views come in round order. A round's case is the last ``case_event_cls`` event
    logged for it, so a resumed round or a second team's copy of the case replaces
    the first. A round with a case and no messages still gets a view: staying
    silent is part of the transcript. A round with messages and no case gets
    ``missing_case_header`` and ``missing_case_ground_truth_block``.
    """
    cases_by_round: dict[int, Case] = {}
    for event in events:
        if isinstance(event, case_event_cls):
            cases_by_round[event.round_number] = event
    messages_by_round = message_lines_by_round(events=events, channel_ids=channel_ids)
    views: list[CommunicationRoundView] = []
    for round_number in sorted(set(cases_by_round) | set(messages_by_round)):
        case = cases_by_round.get(round_number)
        header = missing_case_header
        ground_truth_block = missing_case_ground_truth_block
        if case is not None:
            header = render_header(case)
            ground_truth_block = render_ground_truth_block(case)
        views.append(
            CommunicationRoundView(
                round_number=round_number,
                header=header,
                ground_truth_block=ground_truth_block,
                messages=messages_by_round.get(round_number, []),
            )
        )
    return views
