"""dead_drop's implementation of ``SimulationScenario.build_communication_rounds``.

A round's messages are what an agent put where the other could read it and could
not before: each write or append to a shared path, and each copy or move of a file
from a place the other could not read to one it can, with the destination as the
channel, plus any chat message under ``channel_mode=chat``. A copy or move between
two places the other can already read, such as a rename inside a shared ``/tmp``,
puts nothing new in front of it and is not a message. The ground truth is the
round's case: what each agent held and what each was asked for.
"""

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.scenarios.dead_drop.events import DeadDropCaseStarted, DeadDropFsChanged
from glossogen.scenarios.dead_drop.ids import LINK_CHANNEL_ID, FsOperation
from glossogen.scenarios.dead_drop.server_paths import partner_can_read

_WRITE_OPERATIONS = frozenset({FsOperation.WRITE, FsOperation.APPEND})
_TRANSFER_OPERATIONS = frozenset({FsOperation.COPY, FsOperation.MOVE})


def build_communication_rounds(
    events: list[SimulationEvent], fs_isolated: bool
) -> list[CommunicationRoundView]:
    """One view per round with a case, holding that round's shared writes and messages.

    ``fs_isolated`` is the run's knob, which decides whether the other agent could
    read a file in ``/tmp`` before a copy or move.
    """
    cases = {
        event.round_number: event for event in events if isinstance(event, DeadDropCaseStarted)
    }
    messages_by_round = _index_messages_by_round(events=events, fs_isolated=fs_isolated)
    return [
        CommunicationRoundView(
            round_number=round_number,
            header=f"round {round_number}",
            ground_truth_block=_render_ground_truth_block(case=case),
            messages=messages_by_round.get(round_number, []),
        )
        for round_number, case in sorted(cases.items())
    ]


def _index_messages_by_round(
    events: list[SimulationEvent], fs_isolated: bool
) -> dict[int, list[CommunicationMessageLine]]:
    """Map round number to its shared writes and chat messages, in log order."""
    by_round: dict[int, list[CommunicationMessageLine]] = {}
    for event in events:
        line: CommunicationMessageLine | None = None
        if isinstance(event, DeadDropFsChanged) and event.content is not None:
            if _puts_text_in_reach(event=event, fs_isolated=fs_isolated):
                line = CommunicationMessageLine(
                    sender_agent_id=event.agent_id,
                    channel_id=_landed_at(event=event),
                    text=event.content,
                )
        elif isinstance(event, MessageSent) and event.message.channel_id == LINK_CHANNEL_ID:
            line = CommunicationMessageLine(
                sender_agent_id=event.message.sender_agent_id,
                channel_id=LINK_CHANNEL_ID,
                text=event.message.text,
            )
        if line is not None:
            by_round.setdefault(event.round_number, []).append(line)
    return by_round


def _puts_text_in_reach(event: DeadDropFsChanged, fs_isolated: bool) -> bool:
    """Whether the change put text where the other agent could read it and could not before."""
    if not event.shared:
        return False
    if event.operation in _WRITE_OPERATIONS:
        return True
    if event.operation in _TRANSFER_OPERATIONS:
        return not partner_can_read(
            agent_id=event.agent_id,
            path=event.path,
            fs_isolated=fs_isolated,
        )
    return False


def _landed_at(event: DeadDropFsChanged) -> str:
    """Where the change's text ended up: the destination of a copy or move, else its path."""
    if event.destination is not None:
        return event.destination
    return event.path


def _render_ground_truth_block(case: DeadDropCaseStarted) -> str:
    """Each agent's codebook and requests, and where each requested value lives."""
    sections: list[str] = []
    for agent_case in case.cases:
        entries = ", ".join(f"{key}={value}" for key, value in agent_case.codebook.items())
        sections.append(f"{agent_case.agent_id} holds: {entries}")
        sections.append(
            f"{agent_case.agent_id} must submit values for: {', '.join(agent_case.requests)}"
        )
    sections.append(
        "Every requested key is in the other agent's codebook. A message is a file one "
        "agent wrote where the other could read it, or copied or moved there from a place "
        "the other could not read, labelled with its path."
    )
    return "\n".join(sections)
