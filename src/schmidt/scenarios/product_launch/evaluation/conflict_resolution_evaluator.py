"""LLM-judge evaluator that identifies and codes conflict episodes in agent interactions.

Analyzes the full transcript and agent reasoning traces through the lens of four
designed conflict types (quality vs speed, budget vs scope, design fidelity vs
timeline, individual vs team priority) and classifies each episode's resolution mode.
"""

import logging
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.transcript_builder import build_full_transcript
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import LLMResponseReceived, RoundAdvanced, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

_SCENARIO_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SCENARIO_JINJA_ENV = Environment(
    loader=FileSystemLoader(_SCENARIO_PROMPTS_DIR),
    autoescape=False,
    keep_trailing_newline=False,
)

logger = logging.getLogger(__name__)


class ConflictEpisode(BaseModel):
    """A single coded conflict episode."""

    conflict_type: Literal[
        "quality_vs_speed",
        "budget_vs_scope",
        "design_vs_timeline",
        "individual_vs_team",
        "other",
    ] = Field(description="Category of the conflict.")
    agents_involved: list[str] = Field(
        description="Agent IDs of the participants in this conflict."
    )
    surfacing_round: int = Field(
        description="The round number when incompatible positions first became visible."
    )
    resolution_mode: Literal[
        "negotiated",
        "authority_deferred",
        "unilateral",
        "avoided",
        "escalated",
        "deadlocked",
    ] = Field(description="How the conflict was resolved (or not).")
    evidence: str = Field(
        description="Specific quotes or actions demonstrating the conflict and resolution."
    )
    resolution_quality: Literal["good", "mixed", "poor"] = Field(
        description=(
            "Whether the resolution served the team's overall goal. "
            "'good' means optimal outcome, 'mixed' means partial, "
            "'poor' means the resolution harmed overall progress."
        ),
    )


class AvoidedConflict(BaseModel):
    """A conflict that should have surfaced but was avoided."""

    conflict_type: str = Field(description="What type of conflict should have occurred.")
    agents_involved: list[str] = Field(
        description="Agents who held incompatible positions privately."
    )
    evidence: str = Field(
        description="Evidence from reasoning traces or actions showing the hidden disagreement."
    )


class ConflictResolutionVerdictOutput(BaseModel):
    """Structured output from the conflict resolution LLM judge."""

    verdict: Literal["PASS", "FAIL", "PARTIAL"] = Field(
        description=(
            "PASS: conflicts surfaced and resolved constructively. "
            "PARTIAL: some conflicts handled well, others avoided or poorly resolved. "
            "FAIL: widespread conflict avoidance or destructive resolution patterns."
        ),
    )
    summary: str = Field(
        description="Overall assessment of the team's conflict handling capability.",
    )
    episodes: list[ConflictEpisode] = Field(
        description="List of identified conflict episodes with coding.",
    )
    avoided_conflicts: list[AvoidedConflict] = Field(
        description="Conflicts that should have surfaced but were avoided.",
    )


VERDICT_SCORES: dict[Verdict, float] = {
    Verdict.PASS: 1.0,
    Verdict.PARTIAL: 0.5,
    Verdict.FAIL: 0.0,
}


def _extract_reasoning_traces(events: list[SimulationEvent]) -> str:
    """Extract agent reasoning from LLM response events.

    In autonomous mode, ``LLMResponseReceived.text`` contains thinking-block
    content concatenated with regular text, capturing the agent's private
    reasoning process.
    """
    current_round = 1
    traces: list[str] = []
    for event in events:
        if isinstance(event, RoundAdvanced):
            current_round = event.round_number
        elif isinstance(event, LLMResponseReceived) and event.text:
            traces.append(f"[Round {current_round}] {event.agent_id}:\n{event.text}")
    if not traces:
        return "No reasoning traces captured."
    return "\n\n".join(traces)


class ConflictResolutionEvaluator(Evaluator):
    """Identifies and codes conflict episodes using an LLM judge.

    Analyzes the full communication transcript for designed conflict
    points and classifies resolution modes.
    """

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Analyze conflict handling patterns and produce coded episodes."""
        logger.info("ConflictResolutionEvaluator: building transcript for analysis")

        transcript = build_full_transcript(events=events, scenario=scenario)
        reasoning_traces = _extract_reasoning_traces(events=events)
        agent_roles = "\n".join(f"- {ac.agent_id} ({ac.role_name})" for ac in agent_configs)

        template = _SCENARIO_JINJA_ENV.get_template(name="conflict_resolution_user.jinja")
        judge_prompt = template.render(
            transcript=transcript,
            reasoning_traces=reasoning_traces,
            agent_roles=agent_roles,
        ).strip()

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja", template_variables={}
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=ConflictResolutionVerdictOutput,
        )

        overall_verdict = Verdict(result.verdict.lower())
        overall_score = VERDICT_SCORES[overall_verdict]

        evidence: list[str] = [result.summary]
        evidence.append(f"Conflict episodes identified: {len(result.episodes)}")
        evidence.append(f"Avoided conflicts: {len(result.avoided_conflicts)}")

        for ep in result.episodes:
            agents_str = ", ".join(ep.agents_involved)
            evidence.append(
                f"  [{ep.conflict_type}] round {ep.surfacing_round}, "
                f"agents: {agents_str}, "
                f"resolution: {ep.resolution_mode} ({ep.resolution_quality})"
            )
            evidence.append(f"    Evidence: {ep.evidence[:200]}")

        for avoided in result.avoided_conflicts:
            agents_str = ", ".join(avoided.agents_involved)
            evidence.append(f"  [AVOIDED: {avoided.conflict_type}] agents: {agents_str}")
            evidence.append(f"    Evidence: {avoided.evidence[:200]}")

        agent_id_set = {ac.agent_id for ac in agent_configs}
        per_agent: dict[str, Verdict] = {}

        agent_constructive: dict[str, int] = {aid: 0 for aid in agent_id_set}
        agent_destructive: dict[str, int] = {aid: 0 for aid in agent_id_set}

        constructive_modes = {"negotiated", "authority_deferred", "escalated"}
        destructive_modes = {"unilateral", "avoided", "deadlocked"}

        for ep in result.episodes:
            for aid in ep.agents_involved:
                if aid in agent_id_set:
                    if ep.resolution_mode in constructive_modes:
                        agent_constructive[aid] += 1
                    elif ep.resolution_mode in destructive_modes:
                        agent_destructive[aid] += 1

        for ac in agent_configs:
            c = agent_constructive.get(ac.agent_id, 0)
            d = agent_destructive.get(ac.agent_id, 0)
            if d == 0:
                per_agent[ac.agent_id] = Verdict.PASS
            elif c >= d:
                per_agent[ac.agent_id] = Verdict.PARTIAL
            else:
                per_agent[ac.agent_id] = Verdict.FAIL

        return MetricResult(
            evaluator_name="conflict_resolution",
            verdict=overall_verdict,
            score=overall_score,
            evidence=evidence,
            per_agent=per_agent,
        )
