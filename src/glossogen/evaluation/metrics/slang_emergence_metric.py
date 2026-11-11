"""Metric that detects whether agents repurposed existing words with new meanings."""

from pathlib import Path

from pydantic import BaseModel, Field

from glossogen.evaluation.metric_core.measurement import Measurement, RoundNote
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metrics.flagged_round_judge import (
    FlaggedRoundVerdict,
    judge_flagged_rounds,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.scenario_base import ScenarioBase


class SlangEmergenceOutput(BaseModel):
    """LLM judge output for the slang emergence evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per repurposed expression. Multiple entries may refer to "
            "the same round. Each note should describe the "
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


def _read_verdict(output: SlangEmergenceOutput) -> FlaggedRoundVerdict:
    """Take the round notes, summary qualifiers and explanation from the judge's answer."""
    qualifiers: list[str] = []
    if output.shared_slang:
        qualifiers.append("shared")
    if output.domain_specific_slang:
        qualifiers.append("domain-specific")
    return FlaggedRoundVerdict(
        per_round_notes=output.per_round_notes,
        qualifiers=qualifiers,
        explanation=output.explanation,
    )


class SlangEmergenceMetric(Metric):
    """Detects whether agents created new meanings for existing words."""

    name = "slang_emergence"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Evaluate whether new meanings emerged for existing words."""
        _ = agent_configs, run_dir, options
        return await judge_flagged_rounds(
            metric_name=self.name,
            finding="slang emergence",
            events=events,
            scenario=scenario,
            llm_provider=llm_provider,
            user_template_name="slang_emergence_user.jinja",
            extra_template_variables={},
            output_schema=SlangEmergenceOutput,
            read_verdict=_read_verdict,
        )
