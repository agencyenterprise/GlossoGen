"""Mean Chars per Message (MCM) metric for primary-channel messages.

Computes the mean number of characters per message sent on the scenario's
primary channel. Aggregates per-round and overall statistics. Deterministic —
does not consult the LLM provider.

Pairs with ``mean_chars_per_round``: MCR conflates message density with
verbosity, so rounds that need more back-and-forth inflate the score.
MCM normalizes by message count, isolating "how many characters does each
message carry" from "how many messages does the round need".
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

from schmidt.evaluation.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundMCM(NamedTuple):
    """Per-round aggregate of mean character count across primary-channel messages."""

    round_number: int
    mean_chars: float
    std_chars: float
    message_count: int


class RoundMessages(NamedTuple):
    """All primary-channel message texts for a single round."""

    round_number: int
    texts: list[str]


class MCMMetric(Metric):
    """Reports per-round mean chars-per-message of primary-channel messages.

    Counts characters in each primary-channel message and averages. The
    headline ``score`` is the overall mean chars/message across the run
    (flattened, not mean of round means). Scenarios without a primary
    channel get a no-op result.
    """

    name = "mean_chars_per_message"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> list[Measurement]:
        """Score primary-channel messages and report per-round char-count stats."""
        _ = agent_configs, llm_provider, run_dir
        primary_channel_id = scenario.get_primary_channel_id()
        if primary_channel_id is None:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="chars/message",
                    summary="scenario has no primary channel; mcm metric skipped",
                    per_round=[],
                    per_agent=[],
                )
            ]

        rounds = _collect_primary_messages_by_round(
            events=events,
            primary_channel_id=primary_channel_id,
        )
        if not rounds:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="chars/message",
                    summary=(
                        f"no messages found on primary channel {primary_channel_id!r}; "
                        "mcm metric has nothing to score"
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        round_mcms = [_score_round(round_messages=rm) for rm in rounds]

        all_char_counts = [
            float(len(text)) for round_messages in rounds for text in round_messages.texts
        ]
        total_messages = len(all_char_counts)
        overall_mean = _mean(values=all_char_counts)
        overall_std = _std(values=all_char_counts, mean=overall_mean)

        per_round = [
            RoundObservation(
                round_number=rm.round_number,
                value=rm.mean_chars,
                note=f"{rm.message_count} messages, std={rm.std_chars:.2f}",
            )
            for rm in round_mcms
        ]
        summary = (
            f"{total_messages} messages on {primary_channel_id} across "
            f"{len(round_mcms)} rounds; mean {overall_mean:.2f} chars/message "
            f"(std {overall_std:.2f})"
        )

        logger.info(
            "mcm metric: %.2f chars/msg over %d msgs in %d rounds",
            overall_mean,
            total_messages,
            len(round_mcms),
        )
        return [
            Measurement(
                metric_name=self.name,
                score=overall_mean,
                score_unit="chars/message",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]


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


def _score_round(round_messages: RoundMessages) -> RoundMCM:
    """Aggregate char counts for a round's messages into a RoundMCM."""
    counts = [float(len(text)) for text in round_messages.texts]
    mean_chars = _mean(values=counts)
    std_chars = _std(values=counts, mean=mean_chars)
    return RoundMCM(
        round_number=round_messages.round_number,
        mean_chars=mean_chars,
        std_chars=std_chars,
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
