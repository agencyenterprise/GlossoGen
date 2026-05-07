"""Metric that detects whether agents developed novel compressed language.

Builds per-round comm link transcripts from MessageSent events, then asks
an LLM judge to identify novel abbreviations, compression trends, and shared
conventions that emerged during the simulation. The headline ``score`` is
the count of rounds where the judge observed novel language patterns.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.measurement import Measurement, RoundNote, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.evaluation.metric_run_options import MetricRunOptions
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.prompt_renderer import render_veyru_prompt
from schmidt.scenarios.veyru.veyru_cases import VeyruCase

logger = logging.getLogger(__name__)


class LanguageEmergenceOutput(BaseModel):
    """LLM judge output for the language emergence evaluation."""

    per_round_notes: list[RoundNote] = Field(
        description=(
            "One entry per round where novel language patterns were observed. "
            "Each note should describe the specific shorthand, codes, or compressed "
            "structures seen that round. Include every round with observable "
            "novelty. Empty when no novel patterns appeared."
        ),
    )
    novel_patterns: list[str] = Field(
        description=(
            "Distinct novel patterns the agents invented across the run "
            "(e.g., letter codes, numbered protocols, abbreviations)."
        ),
    )
    compression_observed: bool = Field(
        description="Whether average message length decreased from early to late rounds.",
    )
    shared_conventions: bool = Field(
        description="Whether multiple agents adopted the same novel shorthand.",
    )
    explanation: str = Field(
        description="Overall reasoning, citing specific examples from the transcripts.",
    )


class RoundTranscript(NamedTuple):
    """Comm link transcript for a single round."""

    round_number: int
    transcript: str
    messages: list[str]


class LanguageEmergenceMetric(Metric):
    """Detects whether agents developed novel compressed language across rounds."""

    name = "language_emergence"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Evaluate whether novel compressed language emerged across rounds."""
        _ = agent_configs, run_dir, options
        round_transcripts = self._build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.warning("LanguageEmergenceMetric: no round transcripts found")
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="rounds with novel language patterns",
                    summary="no messages found in the simulation",
                    per_round=[],
                    per_agent=[],
                )
            ]

        judge_prompt = render_veyru_prompt(
            template_name="language_emergence_user.jinja",
            template_variables={
                "rounds": round_transcripts,
            },
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=LanguageEmergenceOutput,
        )

        per_round = [
            RoundObservation(round_number=note.round_number, value=1.0, note=note.note)
            for note in result.per_round_notes
        ]
        flags: list[str] = []
        if result.novel_patterns:
            flags.append(f"patterns: {', '.join(result.novel_patterns[:5])}")
        if result.compression_observed:
            flags.append("compression observed")
        if result.shared_conventions:
            flags.append("shared conventions")
        flag_text = f" ({'; '.join(flags)})" if flags else ""
        summary = (
            f"{len(per_round)}/{len(round_transcripts)} rounds contained "
            f"novel language patterns{flag_text}. {result.explanation}"
        )

        return [
            Measurement(
                metric_name=self.name,
                score=float(len(per_round)),
                score_unit=f"rounds with novel language patterns (out of {len(round_transcripts)})",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]

    def _build_round_transcripts(
        self,
        events: list[SimulationEvent],
        scenario: SimulationScenario,
    ) -> list[RoundTranscript]:
        """Extract per-round comm link transcripts from MessageSent events."""
        veyru_cases: list[VeyruCase] = scenario.veyru_cases  # type: ignore[attr-defined]
        messages_by_round: dict[int, list[str]] = {}
        for event in events:
            if not isinstance(event, MessageSent):
                continue
            rn = event.round_number
            sender = scenario.get_agent_display_name(
                agent_id=event.message.sender_agent_id,
            )
            line = f"{sender}: {event.message.text}"
            if rn not in messages_by_round:
                messages_by_round[rn] = []
            messages_by_round[rn].append(line)

        _ = veyru_cases
        transcripts: list[RoundTranscript] = []
        for rn in sorted(messages_by_round.keys()):
            messages = messages_by_round[rn]
            transcripts.append(
                RoundTranscript(
                    round_number=rn,
                    transcript="\n".join(messages),
                    messages=messages,
                )
            )
        return transcripts
