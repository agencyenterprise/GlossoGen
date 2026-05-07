"""Metric that detects whether agents repurposed existing words with new meanings."""

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from schmidt.evaluation.measurement import Measurement, RoundNote, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.evaluation.metric_run_options import MetricRunOptions
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.round_transcript_builder import build_round_transcripts
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class SlangEmergenceOutput(BaseModel):
    """LLM judge output for the slang emergence evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per round where existing words were repurposed with new "
            "meanings created by the agents. Each note should describe the "
            "specific words and their new meanings, not standard slang or "
            "casual register. Empty when no slang emergence was observed."
        ),
    )
    shared_slang: bool = Field(
        description="Whether multiple agents adopted the same repurposed expressions.",
    )
    domain_specific_slang: bool = Field(
        description=(
            "Whether agents developed task-specific jargon "
            "that would not be understood outside this conversation."
        ),
    )
    explanation: str = Field(
        description="Overall reasoning, citing specific examples from the transcripts.",
    )


class SlangEmergenceMetric(Metric):
    """Detects whether agents created new meanings for existing words."""

    name = "slang_emergence"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Evaluate whether new meanings emerged for existing words."""
        _ = agent_configs, run_dir, options
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.warning("SlangEmergenceMetric: no messages found")
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="rounds with slang emergence",
                    summary="no messages found in the simulation",
                    per_round=[],
                    per_agent=[],
                )
            ]

        judge_prompt = render_evaluator_prompt(
            template_name="slang_emergence_user.jinja",
            template_variables={"rounds": round_transcripts},
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=SlangEmergenceOutput,
        )

        per_round = [
            RoundObservation(round_number=note.round_number, value=1.0, note=note.note)
            for note in result.per_round_notes
        ]
        flags: list[str] = []
        if result.shared_slang:
            flags.append("shared")
        if result.domain_specific_slang:
            flags.append("domain-specific")
        flag_text = f" ({'; '.join(flags)})" if flags else ""
        summary = (
            f"{len(per_round)}/{len(round_transcripts)} rounds contained "
            f"slang emergence{flag_text}. {result.explanation}"
        )

        return [
            Measurement(
                metric_name=self.name,
                score=float(len(per_round)),
                score_unit=f"rounds with slang emergence (out of {len(round_transcripts)})",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]
