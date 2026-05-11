"""Metric that detects shorthand codes and abbreviation systems in communication."""

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


class ShorthandCodesOutput(BaseModel):
    """LLM judge output for the shorthand codes evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per round where shorthand codes or abbreviation systems "
            "were observed. Each note should describe the specific codes seen "
            "that round and what they map to. Include every round with at least "
            "one deliberate symbol-to-meaning mapping. Empty when no codes were used."
        ),
    )
    systematic: bool = Field(
        description=(
            "Whether the codes follow a consistent system "
            "(e.g., always first-letter, always numbered) rather than ad-hoc."
        ),
    )
    messages_shortened: bool = Field(
        description="Whether messages became shorter as codes were adopted.",
    )
    shared_understanding: bool = Field(
        description=(
            "Whether the receiving agent correctly interpreted codes "
            "without asking for clarification."
        ),
    )
    explanation: str = Field(
        description="Overall reasoning, citing specific examples from the transcripts.",
    )


class ShorthandCodesMetric(Metric):
    """Detects whether agents developed shorthand codes or abbreviation systems."""

    name = "shorthand_codes"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Evaluate whether agents developed shorthand codes."""
        _ = agent_configs, run_dir, options
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.info("%s: skipping — no messages found", self.name)
            return []

        judge_prompt = render_evaluator_prompt(
            template_name="shorthand_codes_user.jinja",
            template_variables={"rounds": round_transcripts},
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=ShorthandCodesOutput,
        )

        per_round = [
            RoundObservation(round_number=note.round_number, value=1.0, note=note.note)
            for note in result.per_round_notes
        ]
        flags: list[str] = []
        if result.systematic:
            flags.append("systematic")
        if result.messages_shortened:
            flags.append("messages shortened")
        if result.shared_understanding:
            flags.append("shared understanding")
        flag_text = f" ({'; '.join(flags)})" if flags else ""
        summary = (
            f"{len(per_round)}/{len(round_transcripts)} rounds contained "
            f"shorthand codes{flag_text}. {result.explanation}"
        )

        return [
            Measurement(
                metric_name=self.name,
                score=float(len(per_round)),
                score_unit=f"rounds with shorthand codes (out of {len(round_transcripts)})",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]
