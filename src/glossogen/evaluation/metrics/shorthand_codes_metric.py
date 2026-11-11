"""Metric that detects shorthand codes and abbreviation systems in communication."""

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


class ShorthandCodesOutput(BaseModel):
    """LLM judge output for the shorthand codes evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per shorthand code or abbreviation system. Multiple entries "
            "may refer to the same round. Each note should describe the codes seen "
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


def _read_verdict(output: ShorthandCodesOutput) -> FlaggedRoundVerdict:
    """Take the round notes, summary qualifiers and explanation from the judge's answer."""
    qualifiers: list[str] = []
    if output.systematic:
        qualifiers.append("systematic")
    if output.messages_shortened:
        qualifiers.append("messages shortened")
    if output.shared_understanding:
        qualifiers.append("shared understanding")
    return FlaggedRoundVerdict(
        per_round_notes=output.per_round_notes,
        qualifiers=qualifiers,
        explanation=output.explanation,
    )


class ShorthandCodesMetric(Metric):
    """Detects whether agents developed shorthand codes or abbreviation systems."""

    name = "shorthand_codes"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Evaluate whether agents developed shorthand codes."""
        _ = agent_configs, run_dir, options
        return await judge_flagged_rounds(
            metric_name=self.name,
            finding="shorthand codes",
            events=events,
            scenario=scenario,
            llm_provider=llm_provider,
            user_template_name="shorthand_codes_user.jinja",
            extra_template_variables={},
            output_schema=ShorthandCodesOutput,
            read_verdict=_read_verdict,
        )
