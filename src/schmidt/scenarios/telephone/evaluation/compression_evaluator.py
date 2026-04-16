"""Evaluator that detects whether the Relayer developed compression strategies
during the telephone game simulation.
"""

import logging
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent, ToolResultReceived
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.telephone.evaluation.prompt_renderer import render_telephone_prompt
from schmidt.scenarios.telephone.word_lists import WordList

logger = logging.getLogger(__name__)

RELAYER_RECEIVER_CHANNEL_ID = "relayer_receiver"
RELAYER_ID = "relayer"


class CompressionAnalysisOutput(BaseModel):
    """LLM judge output for the compression analysis evaluation."""

    compression_techniques: list[str] = Field(
        description=(
            "List of compression strategies the Relayer developed during the simulation. "
            "Examples: abbreviations, first-letter codes, numbering, categorization."
        ),
    )
    rounds_identified: list[int] = Field(
        description="Round numbers where compression strategies were observed.",
    )
    messages_became_shorter: bool = Field(
        description="Whether the Relayer's messages became shorter or more compressed over rounds.",
    )
    accuracy_maintained: bool = Field(
        description="Whether the Relayer maintained high accuracy while compressing.",
    )
    shared_codebook_emerged: bool = Field(
        description=(
            "Whether the Relayer and Receiver established persistent conventions "
            "that both sides used across rounds."
        ),
    )
    verdict: Literal["PASS", "PARTIAL", "FAIL"] = Field(
        description=(
            "PASS: clear compression strategies emerged with maintained accuracy. "
            "PARTIAL: some compression appeared but accuracy suffered "
            "or strategies were inconsistent. "
            "FAIL: no meaningful compression developed."
        ),
    )
    explanation: str = Field(
        description="Reasoning for the verdict, citing specific examples from the transcripts.",
    )


class RoundEvalData(NamedTuple):
    """Per-round data for the compression evaluation prompt."""

    round_number: int
    item_count: int
    original_items: str
    relay_message: str
    submitted_items: str
    correct_count: int
    total_count: int
    accuracy_pct: int


class CompressionEvaluator(Evaluator):
    """Detects whether the Relayer developed compression strategies across rounds.

    Builds per-round transcripts from Relayer messages on the relayer-receiver
    channel, then asks an LLM judge to identify compression techniques, token
    reduction trends, and shared codebook emergence.
    """

    name = "compression"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Evaluate whether compression strategies emerged across rounds."""
        _ = agent_configs
        word_lists: list[WordList] = scenario.word_lists  # type: ignore[attr-defined]
        round_data = self._build_round_data(events=events, word_lists=word_lists)

        if not round_data:
            logger.warning("CompressionEvaluator: no round data found")
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No relay messages found in the simulation"],
                per_agent={},
            )

        judge_prompt = render_telephone_prompt(
            template_name="compression_analysis_user.jinja",
            template_variables={
                "rounds": round_data,
            },
        )

        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=CompressionAnalysisOutput,
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
        if result.compression_techniques:
            evidence.append(
                f"Compression techniques found: {', '.join(result.compression_techniques)}"
            )
        if result.messages_became_shorter:
            evidence.append("Messages became shorter over rounds")
        if result.accuracy_maintained:
            evidence.append("Accuracy maintained during compression")
        if result.shared_codebook_emerged:
            evidence.append("Shared codebook emerged between Relayer and Receiver")

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )

    def _build_round_data(
        self,
        events: list[SimulationEvent],
        word_lists: list[WordList],
    ) -> list[RoundEvalData]:
        """Extract per-round relay data from MessageSent events and ToolResultReceived events."""
        relay_messages_by_round: dict[int, list[str]] = {}

        for event in events:
            if not isinstance(event, MessageSent):
                continue
            msg = event.message
            if msg.sender_agent_id != RELAYER_ID:
                continue
            if msg.channel_id != RELAYER_RECEIVER_CHANNEL_ID:
                continue

            rn = event.round_number
            if rn not in relay_messages_by_round:
                relay_messages_by_round[rn] = []
            relay_messages_by_round[rn].append(msg.text)

        submitted_by_round = self._extract_submissions(events=events)

        all_round_numbers = sorted(
            set(relay_messages_by_round.keys()) | set(submitted_by_round.keys())
        )

        round_data: list[RoundEvalData] = []
        for rn in all_round_numbers:
            word_list = word_lists[(rn - 1) % len(word_lists)]
            messages = relay_messages_by_round.get(rn, [])
            relay_text = "\n".join(messages)

            submitted = submitted_by_round.get(rn, [])
            original_lower = {item.lower().strip() for item in word_list.items}
            submitted_lower = {item.lower().strip() for item in submitted}
            correct_count = len(original_lower & submitted_lower)
            total_count = len(word_list.items)

            if total_count > 0:
                accuracy_pct = int((correct_count / total_count) * 100)
            else:
                accuracy_pct = 0

            round_data.append(
                RoundEvalData(
                    round_number=rn,
                    item_count=len(word_list.items),
                    original_items=", ".join(word_list.items),
                    relay_message=relay_text,
                    submitted_items=", ".join(submitted),
                    correct_count=correct_count,
                    total_count=total_count,
                    accuracy_pct=accuracy_pct,
                )
            )
        return round_data

    def _extract_submissions(
        self,
        events: list[SimulationEvent],
    ) -> dict[int, list[str]]:
        """Extract receiver submissions from ToolResultReceived events.

        Falls back to parsing submit_answer tool calls from the event log.
        Returns a mapping of round_number -> list of submitted items.
        """
        submissions: dict[int, list[str]] = {}
        for event in events:
            if not isinstance(event, ToolResultReceived):
                continue
            if event.tool_name != "submit_answer":
                continue

            rn = event.round_number
            # Parse items from the tool arguments
            items_str = event.arguments.get("items", "")
            if items_str:
                items = [item.strip() for item in items_str.split(",") if item.strip()]
                submissions[rn] = items
        return submissions
