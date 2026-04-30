"""Mean Length of Utterance (MLU) evaluator for primary-channel messages.

Computes the average word count per message sent on the scenario's primary
channel, where "word" is defined as a whitespace-delimited token. Aggregates
per-round and overall statistics into the result's evidence. Verdict is
always ``PARTIAL`` -- this evaluator reports numbers, not a classification.

Complements the perplexity evaluator: perplexity captures *how surprising*
each token is, MLU captures *how long the messages are*. A compressed or
coded protocol typically pushes perplexity up and MLU down.
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundMLU(NamedTuple):
    """Per-round aggregate of mean word count across primary-channel messages."""

    round_number: int
    mean_words: float
    std_words: float
    message_count: int


class RoundMessages(NamedTuple):
    """All primary-channel message texts for a single round."""

    round_number: int
    texts: list[str]


class MLUEvaluator(Evaluator):
    """Reports per-round mean words-per-message of primary-channel messages.

    Splits each primary-channel message on whitespace, counts tokens, and
    averages. Returns ``PARTIAL`` with a numeric ``score`` equal to the
    overall mean words-per-message across the run (flattened, not mean of
    round means). Scenarios without a primary channel get a no-op result.
    """

    name = "mean_length_utterance"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Score primary-channel messages and report per-round word-count stats."""
        _ = agent_configs, llm_provider, run_dir
        primary_channel_id = scenario.get_primary_channel_id()
        if primary_channel_id is None:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.PARTIAL,
                score=0.0,
                evidence=["scenario has no primary channel; mlu evaluator skipped"],
                per_agent={},
                rounds_identified=[],
            )

        rounds = _collect_primary_messages_by_round(
            events=events,
            primary_channel_id=primary_channel_id,
        )
        if not rounds:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.PARTIAL,
                score=0.0,
                evidence=[
                    f"no messages found on primary channel {primary_channel_id!r}; "
                    "mlu evaluator has nothing to score",
                ],
                per_agent={},
                rounds_identified=[],
            )

        round_mlus = [_score_round(round_messages=rm) for rm in rounds]

        all_word_counts = [
            float(_word_count(text=text))
            for round_messages in rounds
            for text in round_messages.texts
        ]
        total_messages = len(all_word_counts)
        overall_mean = _mean(values=all_word_counts)
        overall_std = _std(values=all_word_counts, mean=overall_mean)

        evidence = [
            f"mlu unit: words (whitespace split); primary channel: {primary_channel_id}",
            f"scored {total_messages} messages across {len(round_mlus)} rounds",
            (f"overall mean words/message: {overall_mean:.2f} " f"(std {overall_std:.2f})"),
        ]
        for rm in round_mlus:
            evidence.append(
                f"round {rm.round_number}: mean={rm.mean_words:.2f} "
                f"std={rm.std_words:.2f} n={rm.message_count}"
            )

        logger.info(
            "mlu evaluator: %.2f words/msg over %d msgs in %d rounds",
            overall_mean,
            total_messages,
            len(round_mlus),
        )
        return MetricResult(
            evaluator_name=self.name,
            verdict=Verdict.PARTIAL,
            score=overall_mean,
            evidence=evidence,
            per_agent={},
            rounds_identified=[],
        )


def _collect_primary_messages_by_round(
    events: list[SimulationEvent],
    primary_channel_id: str,
) -> list[RoundMessages]:
    """Extract message texts from MessageSent events on the primary channel, by round."""
    by_round: dict[int, list[str]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id != primary_channel_id:
            continue
        text = event.message.text
        if not text:
            continue
        if event.round_number not in by_round:
            by_round[event.round_number] = []
        by_round[event.round_number].append(text)
    return [RoundMessages(round_number=rn, texts=by_round[rn]) for rn in sorted(by_round.keys())]


def _word_count(text: str) -> int:
    """Return the number of whitespace-delimited tokens in ``text``."""
    return len(text.split())


def _score_round(round_messages: RoundMessages) -> RoundMLU:
    """Aggregate word counts for a round's messages into a RoundMLU."""
    counts = [float(_word_count(text=text)) for text in round_messages.texts]
    mean_words = _mean(values=counts)
    std_words = _std(values=counts, mean=mean_words)
    return RoundMLU(
        round_number=round_messages.round_number,
        mean_words=mean_words,
        std_words=std_words,
        message_count=len(counts),
    )


def _mean(values: list[float]) -> float:
    """Arithmetic mean; returns 0.0 for an empty list."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float], mean: float) -> float:
    """Population standard deviation; returns 0.0 for fewer than two values."""
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)
