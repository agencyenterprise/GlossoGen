"""dead_drop's implementation of ``SimulationScenario.build_communication_rounds``.

A round's messages are what an agent put where the other can read it: each
write or append to a shared path, and each copy or move of a file there, with the
path as the channel, plus any chat message under ``channel_mode=chat``. The ground
truth is the round's case: what each agent held and what each was asked for.
"""

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.scenarios.dead_drop.events import DeadDropCaseStarted, DeadDropFsChanged
from glossogen.scenarios.dead_drop.ids import LINK_CHANNEL_ID, FsOperation

_CONTENT_OPERATIONS = frozenset(
    {FsOperation.WRITE, FsOperation.APPEND, FsOperation.COPY, FsOperation.MOVE}
)


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """One view per round with a case, holding that round's shared writes and messages."""
    cases = {
        event.round_number: event for event in events if isinstance(event, DeadDropCaseStarted)
    }
    messages_by_round = _index_messages_by_round(events=events)
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
    events: list[SimulationEvent],
) -> dict[int, list[CommunicationMessageLine]]:
    """Map round number to its shared writes and chat messages, in log order."""
    by_round: dict[int, list[CommunicationMessageLine]] = {}
    for event in events:
        line: CommunicationMessageLine | None = None
        if (
            isinstance(event, DeadDropFsChanged)
            and event.shared
            and event.operation in _CONTENT_OPERATIONS
            and event.content is not None
        ):
            landed_at = event.path
            if event.destination is not None:
                landed_at = event.destination
            line = CommunicationMessageLine(
                sender_agent_id=event.agent_id, channel_id=landed_at, text=event.content
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
        "agent wrote, copied or moved where the other could read it, labelled with its path."
    )
    return "\n".join(sections)
