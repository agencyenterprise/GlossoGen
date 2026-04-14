"""Evaluator that detects whether agents developed novel compressed language
during the Veyru stabilization simulation.
"""

import logging
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.prompt_renderer import render_veyru_prompt
from schmidt.scenarios.veyru.veyru_cases import VEYRU_CASES

logger = logging.getLogger(__name__)


class LanguageEmergenceOutput(BaseModel):
    """LLM judge output for the language emergence evaluation."""

    novel_patterns: list[str] = Field(
        description=(
            "List of novel abbreviations, codes, or shorthand the agents invented "
            "during the simulation. Because the domain is fictional, any shorthand "
            "is necessarily novel."
        ),
    )
    rounds_identified: list[int] = Field(
        description="Round numbers where novel language patterns were observed.",
    )
    compression_observed: bool = Field(
        description="Whether average message length decreased from early to late rounds.",
    )
    shared_conventions: bool = Field(
        description="Whether both agents adopted the same novel shorthand.",
    )
    verdict: Literal["PASS", "PARTIAL", "FAIL"] = Field(
        description=(
            "PASS: clear novel language patterns emerged and were adopted by both agents. "
            "PARTIAL: some compression or shorthand appeared but was not consistently adopted. "
            "FAIL: agents used standard language throughout with no novel patterns."
        ),
    )
    explanation: str = Field(
        description="Reasoning for the verdict, citing specific examples from the transcripts.",
    )


class RoundTranscript(NamedTuple):
    """Comm link transcript for a single round."""

    round_number: int
    transcript: str
    messages: list[str]


class LanguageEmergenceEvaluator(Evaluator):
    """Detects whether agents developed novel compressed language across rounds.

    Builds per-round comm link transcripts from MessageSent events, then asks
    an LLM judge to identify novel abbreviations, compression trends, and shared
    conventions that emerged during the simulation.
    """

    name = "language_emergence"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate whether novel compressed language emerged across rounds."""
        _ = agent_configs
        round_transcripts = self._build_round_transcripts(
            events=events,
            scenario=scenario,
        )

        if not round_transcripts:
            logger.warning("LanguageEmergenceEvaluator: no round transcripts found")
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No messages found in the simulation"],
                per_agent={},
            )

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

        verdict = Verdict(result.verdict.lower())

        score = 0.0
        if verdict == Verdict.PASS:
            score = 1.0
        elif verdict == Verdict.PARTIAL:
            score = 0.5

        evidence: list[str] = [result.explanation]
        if result.rounds_identified:
            evidence.append(f"Rounds: {', '.join(str(r) for r in result.rounds_identified)}")
        if result.novel_patterns:
            evidence.append(f"Novel patterns found: {', '.join(result.novel_patterns)}")
        if result.compression_observed:
            evidence.append("Message compression observed across rounds")
        if result.shared_conventions:
            evidence.append("Shared conventions adopted by both agents")

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )

    def _build_round_transcripts(
        self,
        events: list[SimulationEvent],
        scenario: SimulationScenario,
    ) -> list[RoundTranscript]:
        """Extract per-round comm link transcripts from MessageSent events."""
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

        transcripts: list[RoundTranscript] = []
        for case in VEYRU_CASES:
            rn = case.case_number
            messages = messages_by_round.get(rn, [])
            transcripts.append(
                RoundTranscript(
                    round_number=rn,
                    transcript="\n".join(messages),
                    messages=messages,
                )
            )
        return transcripts
