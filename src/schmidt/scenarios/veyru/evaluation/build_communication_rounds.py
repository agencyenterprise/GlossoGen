"""Veyru's implementation of ``SimulationScenario.build_communication_rounds``.

Joins each round's link-channel messages with the ``VeyruCaseStarted``
event's motif/treatment mapping and renders the per-round ground
truth into the ``CommunicationRoundView.ground_truth_block`` text the
generic communication-feature prompts consume.

The observer/engineer information asymmetry is rendered verbatim into
the block (what each agent saw at round start), so the judge can
decide which protocol moves are sensible for each agent.
"""

import logging

from schmidt.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenarios.veyru.events import VeyruCaseStarted

logger = logging.getLogger(__name__)

_LINK_CHANNEL_IDS = frozenset({"link", "link_a", "link_b"})


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group link-channel messages by round and attach the motif/treatment ground truth.

    Rounds that have no link messages are still emitted as long as the
    round has a ``VeyruCaseStarted`` event — those rounds are signal
    too (the team chose to stay silent on the link). Rounds with
    neither link messages nor ground truth are skipped.
    """
    cases_by_round = _index_cases_by_round(events=events)
    messages_by_round = _index_messages_by_round(events=events)
    all_rounds = sorted(set(cases_by_round.keys()) | set(messages_by_round.keys()))
    views: list[CommunicationRoundView] = []
    for round_number in all_rounds:
        case = cases_by_round.get(round_number)
        messages = messages_by_round.get(round_number, [])
        if case is None and not messages:
            continue
        header = case.failure_name if case is not None else "(unknown)"
        ground_truth_block = _render_ground_truth_block(case=case)
        views.append(
            CommunicationRoundView(
                round_number=round_number,
                header=header,
                ground_truth_block=ground_truth_block,
                messages=messages,
            )
        )
    return views


def _render_ground_truth_block(case: VeyruCaseStarted | None) -> str:
    """Render the observer/engineer asymmetry for one round into a single text block."""
    if case is None:
        return "(no case data for this round)"
    observer_lines = [
        f"- stage {index}: {stage.observable_symptoms}"
        for index, stage in enumerate(case.stages, start=1)
    ]
    engineer_lines = [
        (
            f"- {stage.motif_name} → treatment motif: {stage.treatment_motif_name}; "
            f"procedure to relay: {stage.judge_expected_actions}"
        )
        for stage in case.stages
    ]
    sections: list[str] = ["OBSERVER sees (raw symptoms, no motif names):"]
    sections.extend(observer_lines if observer_lines else ["(no stage data)"])
    sections.append("")
    sections.append("ENGINEER sees (per-motif stellar table this round):")
    sections.extend(engineer_lines if engineer_lines else ["(no stage data)"])
    return "\n".join(sections)


def _index_cases_by_round(events: list[SimulationEvent]) -> dict[int, VeyruCaseStarted]:
    """Map round number → the round's most recent ``VeyruCaseStarted`` event.

    Two-team mode emits one ``VeyruCaseStarted`` per team per round; both
    teams see the same case definition (only the team_id label differs),
    so keeping the latest one per round is sufficient for the judge.
    """
    cases: dict[int, VeyruCaseStarted] = {}
    for event in events:
        if isinstance(event, VeyruCaseStarted):
            cases[event.round_number] = event
    return cases


def _index_messages_by_round(
    events: list[SimulationEvent],
) -> dict[int, list[CommunicationMessageLine]]:
    """Map round number → ordered list of link-channel messages."""
    by_round: dict[int, list[CommunicationMessageLine]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id not in _LINK_CHANNEL_IDS:
            continue
        by_round.setdefault(event.round_number, []).append(
            CommunicationMessageLine(
                sender_agent_id=event.message.sender_agent_id,
                channel_id=event.message.channel_id,
                text=event.message.text,
            )
        )
    return by_round
