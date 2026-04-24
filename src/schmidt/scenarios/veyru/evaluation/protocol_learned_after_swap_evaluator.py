"""Evaluator that detects whether a newcomer learned the pre-established
protocol after a mid-run personnel change.

Applies to two-team swap mode (observers swap between teams at
``swap_round``) and intern mode (intern replaces field observer at
``intern_takeover_round``). In both cases, the pre-boundary window is
where the original pair establishes a shorthand/convention; the
post-boundary window is where the newcomer must continue using it.
"""

import logging
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.log_reader import extract_scenario_config
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
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

    protocol_elements: list[str] = Field(
        description=(
            "List of shorthand, codes, abbreviations, or conventions that the "
            "original pair(s) established pre-boundary. Each entry should describe "
            "the element and give a pre-boundary round example."
        ),
    )
    newcomer_adoption_examples: list[str] = Field(
        description=(
            "Specific post-boundary messages (with round number and sender) showing "
            "the newcomer using or failing to use the pre-established protocol."
        ),
    )
    newcomer_agent_ids: list[str] = Field(
        description=(
            "Which agent IDs acted as newcomers in the post-boundary window, as "
            "inferred from the transcripts."
        ),
    )
    rounds_identified: list[int] = Field(
        description=(
            "Post-boundary round numbers where the newcomer used (or failed to use) "
            "the pre-established protocol. These are the rounds cited in "
            "``newcomer_adoption_examples``; include every round where there is "
            "observable evidence of adoption or non-adoption."
        ),
    )
    protocol_established: bool = Field(
        description=(
            "Whether the original pair(s) established an identifiable protocol "
            "pre-boundary. If false, the verdict must be FAIL."
        ),
    )
    verdict: Literal["PASS", "PARTIAL", "FAIL"] = Field(
        description=(
            "PASS: newcomer clearly adopted the pre-established protocol. "
            "PARTIAL: newcomer adopted some elements but not others, or usage "
            "was inconsistent. "
            "FAIL: newcomer did not adopt the protocol, or no protocol was "
            "established pre-boundary to evaluate."
        ),
    )
    explanation: str = Field(
        description="Reasoning for the verdict, citing specific round numbers.",
    )


class ProtocolLearnedAfterSwapEvaluator(Evaluator):
    """Assesses whether a newcomer adopted the pre-established communication protocol.

    Reads the scenario config to determine the mode (swap or intern) and the
    boundary round, splits link-channel MessageSent events into pre and post
    windows, then asks an LLM judge whether the conventions established by the
    original pair continue to be used by the newcomer.
    """

    name = "protocol_learned_after_swap"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Score newcomer adoption of the pre-boundary protocol."""
        _ = agent_configs, scenario, run_dir
        config = extract_scenario_config(events=events)
        window = _detect_boundary_window(config=config)
        if window is None:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    "Scenario did not use two-team swap mode or intern mode; "
                    "no personnel change boundary to evaluate."
                ],
                per_agent={},
                rounds_identified=[],
            )

        pre_rounds, post_rounds = _split_transcripts(
            events=events,
            boundary_round=window.boundary_round,
            is_intern=window.mode_label == "intern",
        )

        if not pre_rounds or not post_rounds:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    f"Insufficient messages around the boundary (pre={len(pre_rounds)}, "
                    f"post={len(post_rounds)}). Cannot evaluate protocol transfer."
                ],
                per_agent={},
                rounds_identified=[],
            )

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

        verdict = Verdict(result.verdict.lower())
        score = _verdict_to_score(verdict=verdict)

        evidence: list[str] = [result.explanation]
        if result.protocol_elements:
            evidence.append(
                f"Pre-boundary protocol elements: {'; '.join(result.protocol_elements[:5])}"
            )
        if result.newcomer_adoption_examples:
            evidence.append(
                f"Post-boundary evidence: {'; '.join(result.newcomer_adoption_examples[:5])}"
            )
        if result.newcomer_agent_ids:
            evidence.append(f"Newcomer agents: {', '.join(result.newcomer_agent_ids)}")
        if not result.protocol_established:
            evidence.append("No identifiable protocol was established pre-boundary.")
        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
            rounds_identified=sorted(set(result.rounds_identified)),
        )


def _detect_boundary_window(config: dict[str, object]) -> BoundaryWindow | None:
    """Return the boundary window for swap or intern mode, or None if neither applies."""
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

    return None


def _split_transcripts(
    events: list[SimulationEvent],
    boundary_round: int,
    is_intern: bool,
) -> tuple[list[RoundTranscript], list[RoundTranscript]]:
    """Partition link-channel messages into pre and post boundary windows."""
    pre_by_round: dict[int, list[str]] = {}
    post_by_round: dict[int, list[str]] = {}

    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id not in LINK_CHANNEL_IDS:
            continue
        line = _format_message_line(event=event)
        rn = event.round_number
        is_post = rn >= boundary_round if is_intern else rn > boundary_round
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
    return f"[{event.message.channel_id}] " f"{event.message.sender_agent_id}: {event.message.text}"


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


def _verdict_to_score(verdict: Verdict) -> float:
    """Map a three-valued verdict to a numeric score."""
    if verdict == Verdict.PASS:
        return 1.0
    if verdict == Verdict.PARTIAL:
        return 0.5
    return 0.0
