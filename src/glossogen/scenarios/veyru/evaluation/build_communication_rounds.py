"""Veyru's implementation of ``SimulationScenario.build_communication_rounds``.

Joins each round's link-channel messages with the ``VeyruCaseStarted``
event's motif/treatment mapping and renders the per-round ground
truth into the ``CommunicationRoundView.ground_truth_block`` text the
generic communication-feature prompts consume.

The observer/engineer information asymmetry is rendered verbatim into
the block (what each agent saw at round start), so the judge can
decide which protocol moves are sensible for each agent.
"""

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationRoundView,
    round_views_with_case,
)
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.veyru.events import VeyruCaseStarted

_LINK_CHANNEL_IDS = frozenset({"link", "link_a", "link_b"})


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group link-channel messages by round and attach the motif/treatment ground truth.

    Two-team mode emits one ``VeyruCaseStarted`` per team per round; both teams
    see the same case definition (only the team_id label differs), so the round's
    last one is the case the judge reads.
    """
    return round_views_with_case(
        events=events,
        case_event_cls=VeyruCaseStarted,
        channel_ids=_LINK_CHANNEL_IDS,
        render_header=_render_header,
        render_ground_truth_block=_render_ground_truth_block,
        missing_case_header="(unknown)",
        missing_case_ground_truth_block="(no case data for this round)",
    )


def _render_header(case: VeyruCaseStarted) -> str:
    """One-line round anchor: the case's failure name."""
    return case.failure_name


def _render_ground_truth_block(case: VeyruCaseStarted) -> str:
    """Render the observer/engineer asymmetry for one round into a single text block."""
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
