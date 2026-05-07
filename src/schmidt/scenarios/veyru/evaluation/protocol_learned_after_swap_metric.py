"""Metric that detects whether a newcomer learned the pre-established protocol.

Applies to two-team swap mode (observers swap between teams at
``swap_round``) and intern mode (intern replaces field observer at
``intern_takeover_round``). In both cases, the pre-boundary window is
where the original pair establishes a shorthand/convention; the
post-boundary window is where the newcomer must continue using it.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.log_reader import extract_scenario_config
from schmidt.evaluation.measurement import Measurement, RoundNote, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentSwappedMidRun, MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.prompt_renderer import render_veyru_prompt

logger = logging.getLogger(__name__)

LINK_CHANNEL_IDS = frozenset({"link", "link_a", "link_b"})


class RoundTranscript(NamedTuple):
    """Link-channel transcript for a single round."""

    round_number: int
    transcript: str
    message_count: int


class BoundaryWindow(NamedTuple):
    """Split of the simulation around a personnel-change boundary."""

    mode_label: str
    boundary_round: int
    pre_boundary_last_round: int
    post_boundary_first_round: int
    newcomer_label: str


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
    ) -> list[Measurement]:
        """Score newcomer adoption of the pre-boundary protocol."""
        _ = agent_configs, scenario, run_dir
        config = extract_scenario_config(events=events)
        window = _detect_boundary_window(config=config, events=events)
        if window is None:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="post-boundary rounds with protocol use",
                    summary=(
                        "Scenario did not use two-team swap mode, intern mode, or in-run "
                        "scheduled swaps; no personnel change boundary to evaluate."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        # ``intern`` and ``scheduled_swap`` both place the boundary AT the
        # newcomer's first round (post = round >= boundary). Two-team
        # ``swap`` mode keeps the swap round in the pre-boundary window.
        boundary_includes_round = window.mode_label in ("intern", "scheduled_swap")
        pre_rounds, post_rounds = _split_transcripts(
            events=events,
            boundary_round=window.boundary_round,
            boundary_includes_round=boundary_includes_round,
        )

        if not pre_rounds or not post_rounds:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="post-boundary rounds with protocol use",
                    summary=(
                        f"Insufficient messages around the boundary (pre={len(pre_rounds)}, "
                        f"post={len(post_rounds)}). Cannot evaluate protocol transfer."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        judge_prompt = render_veyru_prompt(
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


def _detect_boundary_window(
    config: dict[str, object],
    events: list[SimulationEvent],
) -> BoundaryWindow | None:
    """Return the boundary window for swap, intern mode, or scheduled swap.

    Detection order (first match wins): intern mode, two-team swap mode,
    in-run scheduled swap (first ``AgentSwappedMidRun`` event in the
    log). Multi-swap runs only report on the first boundary; downstream
    consumers can read the JSONL directly to inspect later swaps.
    """
    intern_enabled = bool(config.get("intern_enabled", False))
    two_teams = bool(config.get("two_teams", False))

    if intern_enabled:
        takeover = config.get("intern_takeover_round")
        if not isinstance(takeover, int):
            return None
        return BoundaryWindow(
            mode_label="intern",
            boundary_round=takeover,
            pre_boundary_last_round=takeover - 1,
            post_boundary_first_round=takeover,
            newcomer_label="intern (now acting as field observer)",
        )

    if two_teams:
        swap_round = config.get("swap_round")
        if not isinstance(swap_round, int):
            return None
        return BoundaryWindow(
            mode_label="swap",
            boundary_round=swap_round,
            pre_boundary_last_round=swap_round,
            post_boundary_first_round=swap_round + 1,
            newcomer_label=(
                "the swapped-in field observer in each team "
                "(observer_a on link_b, observer_b on link_a)"
            ),
        )

    first_swap = next(
        (event for event in events if isinstance(event, AgentSwappedMidRun)),
        None,
    )
    if first_swap is not None:
        return BoundaryWindow(
            mode_label="scheduled_swap",
            boundary_round=first_swap.round_number,
            pre_boundary_last_round=first_swap.round_number - 1,
            post_boundary_first_round=first_swap.round_number,
            newcomer_label=f"swapped-in {first_swap.agent_id}",
        )

    return None


def _split_transcripts(
    events: list[SimulationEvent],
    boundary_round: int,
    boundary_includes_round: bool,
) -> tuple[list[RoundTranscript], list[RoundTranscript]]:
    """Partition link-channel messages into pre and post boundary windows.

    ``boundary_includes_round=True`` puts the boundary round itself
    into the post-boundary window (intern / scheduled-swap modes,
    where the newcomer is already active for that round).
    ``False`` keeps it in the pre-boundary window (two-team swap mode,
    where the swap fires after the round completes).
    """
    pre_by_round: dict[int, list[str]] = {}
    post_by_round: dict[int, list[str]] = {}

    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id not in LINK_CHANNEL_IDS:
            continue
        line = _format_message_line(event=event)
        rn = event.round_number
        is_post = rn >= boundary_round if boundary_includes_round else rn > boundary_round
        target = post_by_round if is_post else pre_by_round
        if rn not in target:
            target[rn] = []
        target[rn].append(line)

    return (
        _build_round_list(messages_by_round=pre_by_round),
        _build_round_list(messages_by_round=post_by_round),
    )


def _format_message_line(event: MessageSent) -> str:
    """Format a MessageSent event as a single transcript line."""
    return f"[{event.message.channel_id}] {event.message.sender_agent_id}: {event.message.text}"


def _build_round_list(messages_by_round: dict[int, list[str]]) -> list[RoundTranscript]:
    """Convert a round-keyed message map into a sorted list of transcripts."""
    transcripts: list[RoundTranscript] = []
    for rn in sorted(messages_by_round.keys()):
        messages = messages_by_round[rn]
        transcripts.append(
            RoundTranscript(
                round_number=rn,
                transcript="\n".join(messages),
                message_count=len(messages),
            )
        )
    return transcripts
