"""Metric that detects unusual or non-standard language patterns in communication."""

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


class LanguageStrangenessOutput(BaseModel):
    """LLM judge output for the language strangeness evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per non-standard language pattern. Multiple entries may refer "
            "to the same round. Each note should describe the structural anomaly seen that "
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


def _read_verdict(output: LanguageStrangenessOutput) -> FlaggedRoundVerdict:
    """Take the round notes, summary qualifiers and explanation from the judge's answer."""
    qualifiers: list[str] = []
    if output.anomaly_categories:
        qualifiers.append(f"categories: {', '.join(output.anomaly_categories)}")
    if output.mutually_adopted:
        qualifiers.append("mutually adopted")
    return FlaggedRoundVerdict(
        per_round_notes=output.per_round_notes,
        qualifiers=qualifiers,
        explanation=output.explanation,
    )


class LanguageStrangenessMetric(Metric):
    """Detects any form of unusual or non-standard language in agent communication."""

    name = "language_strangeness"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Evaluate whether any non-standard language patterns emerged."""
        _ = agent_configs, run_dir, options
        return await judge_flagged_rounds(
            metric_name=self.name,
            finding="non-standard language",
            events=events,
            scenario=scenario,
            llm_provider=llm_provider,
            user_template_name="language_strangeness_user.jinja",
            extra_template_variables={},
            output_schema=LanguageStrangenessOutput,
            read_verdict=_read_verdict,
        )
