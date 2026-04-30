"""Metric that detects unusual or non-standard language patterns in communication."""

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from schmidt.evaluation.measurement import Measurement, RoundNote, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.round_transcript_builder import build_round_transcripts
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class LanguageStrangenessOutput(BaseModel):
    """LLM judge output for the language strangeness evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per round where non-standard language patterns were observed. "
            "Each note should describe the specific structural anomalies seen that "
            "round (telegraph-style, dropped articles, unusual formatting, etc.) "
            "with examples. Include every round with at least one anomaly. Empty "
            "when language was standard throughout."
        ),
    )
    anomaly_categories: list[str] = Field(
        description=(
            "Distinct categories of strangeness observed across the run "
            "(e.g., dropped articles, telegraph-style, unusual punctuation)."
        ),
    )
    mutually_adopted: bool = Field(
        description="Whether multiple agents adopted the same non-standard patterns.",
    )
    explanation: str = Field(
        description="Overall reasoning, citing specific examples from the transcripts.",
    )


class LanguageStrangenessMetric(Metric):
    """Detects any form of unusual or non-standard language in agent communication."""

    name = "language_strangeness"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> list[Measurement]:
        """Evaluate whether any non-standard language patterns emerged."""
        _ = agent_configs, run_dir
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.warning("LanguageStrangenessMetric: no messages found")
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="rounds with non-standard language",
                    summary="no messages found in the simulation",
                    per_round=[],
                    per_agent=[],
                )
            ]

        judge_prompt = render_evaluator_prompt(
            template_name="language_strangeness_user.jinja",
            template_variables={"rounds": round_transcripts},
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=LanguageStrangenessOutput,
        )

        per_round = [
            RoundObservation(round_number=note.round_number, value=1.0, note=note.note)
            for note in result.per_round_notes
        ]
        flags: list[str] = []
        if result.anomaly_categories:
            flags.append(f"categories: {', '.join(result.anomaly_categories)}")
        if result.mutually_adopted:
            flags.append("mutually adopted")
        flag_text = f" ({'; '.join(flags)})" if flags else ""
        summary = (
            f"{len(per_round)}/{len(round_transcripts)} rounds contained "
            f"non-standard language{flag_text}. {result.explanation}"
        )

        return [
            Measurement(
                metric_name=self.name,
                score=float(len(per_round)),
                score_unit=f"rounds with non-standard language (out of {len(round_transcripts)})",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]
