"""Builds the per-round link-channel + ground-truth view shared by both passes.

The open-coding metric (pass 1) and the feature-presence metric (pass 3)
must feed the LLM judge the same transcript so their outputs are
commensurable — the only difference between the two prompts is the
presence of the ontology category list. This module owns that shared
view: per-round link-channel messages plus the round's ``motif →
treatment_motif`` mapping projected out of the ``VeyruCaseStarted``
event.
"""

from typing import NamedTuple

from schmidt.models.event import MessageSent, SimulationEvent, VeyruCaseStarted

LINK_CHANNEL_IDS = frozenset({"link", "link_a", "link_b"})


class MotifMapping(NamedTuple):
    """One stage of the round's ground-truth motif → treatment mapping."""

    symptom_motif: str
    treatment_motif: str
    observable_symptoms: str
    expected_actions: str


class LinkMessageLine(NamedTuple):
    """One link-channel message rendered for the judge prompt."""

    sender_agent_id: str
    channel_id: str
    text: str


class LinkRoundView(NamedTuple):
    """One round's link-channel transcript plus the round's ground-truth.

    ``failure_name`` is the case's failure label, used as a row header so
    the judge can group observations across rounds with the same failure.
    The stellar offset is intentionally NOT carried here: its only effect
    is to determine the per-stage motif → treatment mapping, which
    ``motif_mappings`` already encodes verbatim; the offset itself is
    engineer-internal state the observer never sees and would only
    invite spurious "observer encodes the offset" labels.
    """

    round_number: int
    failure_name: str
    motif_mappings: list[MotifMapping]
    messages: list[LinkMessageLine]


def build_link_rounds(events: list[SimulationEvent]) -> list[LinkRoundView]:
    """Group link-channel messages by round and attach motif/treatment ground truth.

    Rounds that have no link messages are still emitted as long as the
    round has a ``VeyruCaseStarted`` event — those rounds are signal too
    (the team chose to stay silent on the link). Rounds with neither
    link messages nor ground truth are skipped.
    """
    cases_by_round = _index_cases_by_round(events=events)
    messages_by_round = _index_messages_by_round(events=events)
    all_rounds = sorted(set(cases_by_round.keys()) | set(messages_by_round.keys()))
    views: list[LinkRoundView] = []
    for round_number in all_rounds:
        case = cases_by_round.get(round_number)
        messages = messages_by_round.get(round_number, [])
        if case is None and not messages:
            continue
        if case is None:
            failure_name = "(unknown)"
            motif_mappings: list[MotifMapping] = []
        else:
            failure_name = case.failure_name
            motif_mappings = [
                MotifMapping(
                    symptom_motif=stage.motif_name,
                    treatment_motif=stage.treatment_motif_name,
                    observable_symptoms=stage.observable_symptoms,
                    expected_actions=stage.judge_expected_actions,
                )
                for stage in case.stages
            ]
        views.append(
            LinkRoundView(
                round_number=round_number,
                failure_name=failure_name,
                motif_mappings=motif_mappings,
                messages=messages,
            )
        )
    return views


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


def _index_messages_by_round(events: list[SimulationEvent]) -> dict[int, list[LinkMessageLine]]:
    """Map round number → ordered list of link-channel messages."""
    by_round: dict[int, list[LinkMessageLine]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id not in LINK_CHANNEL_IDS:
            continue
        by_round.setdefault(event.round_number, []).append(
            LinkMessageLine(
                sender_agent_id=event.message.sender_agent_id,
                channel_id=event.message.channel_id,
                text=event.message.text,
            )
        )
    return by_round
