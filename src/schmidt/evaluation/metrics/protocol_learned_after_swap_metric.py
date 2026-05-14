"""Metric that detects whether a newcomer learned the pre-established protocol.

Generic platform metric. Delegates boundary detection to the scenario via
``SimulationScenario.detect_protocol_boundary_window`` (which covers
intern takeover, two-team observer swap, and the generic scheduled-swap
default) and pulls per-round transcripts from
``SimulationScenario.build_communication_rounds`` so the prompt sees the
exact rows the open-coding / feature-presence pipeline uses.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from schmidt.evaluation.metric_core.measurement import Measurement, RoundNote, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.metric_core.protocol_boundary import ProtocolBoundaryWindow
from schmidt.evaluation.metrics.communication.round_view import CommunicationRoundView
from schmidt.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class _RoundTranscript(BaseModel):
    """One round's primary-channel transcript as rendered for the judge prompt."""

    round_number: int
    transcript: str
    message_count: int


class ProtocolLearnedOutput(BaseModel):
    """LLM judge output for protocol-learning evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per post-boundary round where there is observable evidence "
            "of the newcomer using or failing to use the pre-established protocol. "
            "Each note should describe the specific message(s) (with sender) and "
            "whether they extended, reverted from, or ignored the protocol. Include "
            "every round with observable evidence."
        ),
    )
    protocol_elements: list[str] = Field(
        description=(
            "Shorthand, codes, abbreviations, or conventions that the original "
            "pair(s) established pre-boundary. Each entry should describe the "
            "element and give a pre-boundary round example."
        ),
    )
    newcomer_agent_ids: list[str] = Field(
        description=(
            "Which agent IDs acted as newcomers in the post-boundary window, as "
            "inferred from the transcripts."
        ),
    )
    protocol_established: bool = Field(
        description=(
            "Whether the original pair(s) established an identifiable protocol "
            "pre-boundary. If false, the metric reports zero adoption."
        ),
    )
    explanation: str = Field(
        description="Overall reasoning, citing specific examples from the transcripts.",
    )


class ProtocolLearnedAfterSwapMetric(Metric):
    """Counts post-boundary rounds where the newcomer used the established protocol."""

    name = "protocol_learned_after_swap"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score newcomer adoption of the pre-boundary protocol."""
        _ = run_dir, options
        window = scenario.detect_protocol_boundary_window(
            events=events,
            agent_configs=agent_configs,
        )
        if window is None:
            logger.info("%s: skipping — scenario reported no boundary window", self.name)
            return []

        round_views = scenario.build_communication_rounds(events=events)
        if not round_views:
            logger.info("%s: skipping — scenario has no communication rounds wired up", self.name)
            return []

        pre_rounds, post_rounds = _split_round_views(
            round_views=round_views,
            window=window,
        )
        if not pre_rounds or not post_rounds:
            logger.info(
                "%s: skipping — insufficient messages around boundary (pre=%d, post=%d)",
                self.name,
                len(pre_rounds),
                len(post_rounds),
            )
            return []

        judge_prompt = render_evaluator_prompt(
            template_name="protocol_learned_after_swap_user.jinja",
            template_variables={
                "mode_label": window.mode_label,
                "boundary_round": window.boundary_round,
                "pre_boundary_last_round": window.pre_boundary_last_round,
                "post_boundary_first_round": window.post_boundary_first_round,
                "newcomer_label": window.newcomer_label,
                "pre_rounds": pre_rounds,
                "post_rounds": post_rounds,
            },
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=ProtocolLearnedOutput,
        )

        per_round = [
            RoundObservation(round_number=note.round_number, value=1.0, note=note.note)
            for note in result.per_round_notes
        ]
        post_round_count = len(post_rounds)
        summary_parts = [
            f"{len(per_round)}/{post_round_count} post-boundary rounds had observable "
            f"newcomer protocol evidence.",
            result.explanation,
        ]
        if result.protocol_elements:
            summary_parts.append(
                f"Pre-boundary protocol elements: {'; '.join(result.protocol_elements[:5])}"
            )
        if result.newcomer_agent_ids:
            summary_parts.append(f"Newcomer agents: {', '.join(result.newcomer_agent_ids)}")
        if not result.protocol_established:
            summary_parts.append("No identifiable protocol was established pre-boundary.")
        summary = " ".join(summary_parts)

        return [
            Measurement(
                metric_name=self.name,
                score=float(len(per_round)),
                score_unit=(
                    f"post-boundary rounds with newcomer protocol evidence "
                    f"(out of {post_round_count})"
                ),
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]


def _split_round_views(
    round_views: list[CommunicationRoundView],
    window: ProtocolBoundaryWindow,
) -> tuple[list[_RoundTranscript], list[_RoundTranscript]]:
    """Partition ``round_views`` into pre and post boundary transcripts."""
    pre: list[_RoundTranscript] = []
    post: list[_RoundTranscript] = []
    for view in round_views:
        rn = view.round_number
        is_post = (
            rn >= window.boundary_round
            if window.boundary_includes_round
            else rn > window.boundary_round
        )
        target = post if is_post else pre
        transcript_lines = [
            f"[{message.channel_id}] {message.sender_agent_id}: {message.text}"
            for message in view.messages
        ]
        target.append(
            _RoundTranscript(
                round_number=rn,
                transcript="\n".join(transcript_lines),
                message_count=len(view.messages),
            )
        )
    pre.sort(key=lambda r: r.round_number)
    post.sort(key=lambda r: r.round_number)
    return pre, post
