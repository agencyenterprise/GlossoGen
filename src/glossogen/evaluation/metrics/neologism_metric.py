"""Metric that detects whether agents invented new words during communication."""

from pathlib import Path

from pydantic import BaseModel, Field

from glossogen.evaluation.metrics.flagged_round_judge import (
    FlaggedRoundVerdict,
    judge_flagged_rounds,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.measurement import Measurement, RoundNote
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.metric_run_options import MetricRunOptions
from glossogen.scenario_contract.scenario_base import ScenarioBase


class NeologismOutput(BaseModel):
    """LLM judge output for the neologism evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per genuinely invented word. Multiple entries may refer to "
            "the same round. Each note should describe the neologism, with "
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


def _read_verdict(output: NeologismOutput) -> FlaggedRoundVerdict:
    """Take the round notes, summary qualifiers and explanation from the judge's answer."""
    qualifiers: list[str] = []
    if output.semantically_stable:
        qualifiers.append("semantically stable")
    if output.mutually_adopted:
        qualifiers.append("mutually adopted")
    return FlaggedRoundVerdict(
        per_round_notes=output.per_round_notes,
        qualifiers=qualifiers,
        explanation=output.explanation,
    )


class NeologismMetric(Metric):
    """Detects whether agents invented new words or terms during communication."""

    name = "neologism"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Evaluate whether agents invented new vocabulary."""
        _ = run_dir, options
        return await judge_flagged_rounds(
            metric_name=self.name,
            finding="detected neologisms",
            events=events,
            scenario=scenario,
            llm_provider=llm_provider,
            user_template_name="neologism_user.jinja",
            extra_template_variables={
                "agent_prompts": [
                    {"role_name": config.role_name, "system_prompt": config.system_prompt}
                    for config in agent_configs
                ]
            },
            output_schema=NeologismOutput,
            read_verdict=_read_verdict,
        )
