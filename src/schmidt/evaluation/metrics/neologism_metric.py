"""Metric that detects whether agents invented new words during communication."""

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from schmidt.evaluation.metric_core.measurement import Measurement, RoundNote, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.round_transcript_builder import build_round_transcripts
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class NeologismOutput(BaseModel):
    """LLM judge output for the neologism evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per round where genuinely invented words appeared. Each "
            "note should describe the specific neologisms seen that round, with "
            "the term and what it appears to mean. Include every round with "
            "observable evidence. Empty when no neologisms appeared."
        ),
    )
    semantically_stable: bool = Field(
        description="Whether invented terms retained consistent meanings across rounds.",
    )
    mutually_adopted: bool = Field(
        description="Whether multiple agents used the invented terms.",
    )
    explanation: str = Field(
        description="Overall reasoning, citing specific examples from the transcripts.",
    )


class NeologismMetric(Metric):
    """Detects whether agents invented new words or terms during communication."""

    name = "neologism"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Evaluate whether agents invented new vocabulary."""
        _ = run_dir, options
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.info("%s: skipping — no messages found", self.name)
            return []

        agent_prompts = [
            {"role_name": config.role_name, "system_prompt": config.system_prompt}
            for config in agent_configs
        ]

        judge_prompt = render_evaluator_prompt(
            template_name="neologism_user.jinja",
            template_variables={
                "rounds": round_transcripts,
                "agent_prompts": agent_prompts,
            },
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=NeologismOutput,
        )

        per_round = [
            RoundObservation(round_number=note.round_number, value=1.0, note=note.note)
            for note in result.per_round_notes
        ]
        flags: list[str] = []
        if result.semantically_stable:
            flags.append("semantically stable")
        if result.mutually_adopted:
            flags.append("mutually adopted")
        flag_text = f" ({'; '.join(flags)})" if flags else ""
        summary = (
            f"{len(per_round)}/{len(round_transcripts)} rounds contained "
            f"detected neologisms{flag_text}. {result.explanation}"
        )

        return [
            Measurement(
                metric_name=self.name,
                score=float(len(per_round)),
                score_unit=f"rounds with detected neologisms (out of {len(round_transcripts)})",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]
