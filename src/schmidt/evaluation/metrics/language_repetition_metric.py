"""Metric that measures how much each message redundantly re-encodes information.

Under channel noise, agents defend against character loss by encoding the same
information more than once within a message — repeating tokens (``Lf Lf 12 12``),
dual-encoding a value two ways (``12 twelve``, ``12twelve``), or pairing an
abbreviation with its full word (``gnt gentle``).

For each round, the round's ``#link`` (primary-channel) messages are collected on
the *pristine* text the sender composed (before the noise transform) and fed to an
LLM judge as an enumerated list. The judge returns one ``repetition_factor`` per
message (>= 1.0; 1.0 = each piece of information stated once, 2.0 = roughly twice,
3.0 = roughly three times). Each round is judged ``_JUDGE_REPLICAS`` times and the
per-message factors are averaged across replicas — so the judge is called
``rounds * _JUDGE_REPLICAS`` times per run.

The per-message factors are written to a ``language_repetition_messages.jsonl``
sidecar (keyed by ``message_id``) for message-level analysis. The ``Measurement``
carries the per-round mean factor (mean across that round's messages) as each
``RoundObservation`` and the run-level mean as the headline score.
"""

import asyncio
import json
import logging
import statistics
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.metric_core.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.metric_core.pristine_text_index import (
    build_pristine_text_index,
    pristine_text_for,
)
from schmidt.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_JUDGE_REPLICAS = 3
_MAX_CONCURRENT_JUDGE_CALLS = 8
_SIDECAR_FILENAME = "language_repetition_messages.jsonl"


class MessageRepetition(BaseModel):
    """The judge's redundancy factor for a single enumerated message."""

    message_number: int = Field(
        description="The 1-based number of the message in the enumerated list.",
    )
    repetition_factor: float = Field(
        description=(
            "How many times, on average, each distinct piece of information in THIS "
            "message is encoded. 1.0 = stated once (no redundancy); 2.0 = roughly "
            "twice ('12 12', 'gentle gentle', '12 twelve', 'gnt gentle'); 3.0 = "
            "roughly three times ('T1 T1 T1'). Always >= 1.0."
        ),
    )


class RoundRepetitionOutput(BaseModel):
    """LLM judge output for one round: one entry per enumerated message."""

    per_message: list[MessageRepetition] = Field(
        description="Exactly one entry per enumerated message; fill in every message.",
    )


class _LinkMessage(NamedTuple):
    """One primary-channel message's identity and pristine text."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str


class _RoundMessages(NamedTuple):
    """A round's ordered primary-channel messages."""

    round_number: int
    messages: list[_LinkMessage]


class _MessageScore(NamedTuple):
    """A message's per-replica factors and their mean."""

    message: _LinkMessage
    round_number: int
    message_number: int
    mean_factor: float
    replica_factors: list[float]


class LanguageRepetitionMetric(Metric):
    """Per-message within-message redundancy on the primary channel, judged per round.

    Judges each round's enumerated ``#link`` messages ``_JUDGE_REPLICAS`` times,
    averages each message's factor across replicas, writes per-message rows to a
    sidecar, and reports the per-round mean factor (and run-level mean) as the
    ``Measurement``. Scenarios with no primary channel get a no-op result.
    """

    name = "language_repetition"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Judge per-message redundancy on pristine primary-channel text, per round and channel."""
        _ = agent_configs, options
        channels = scenario.get_primary_channels()
        if not channels:
            logger.info("%s: skipping — scenario has no primary channel", self.name)
            return []

        pristine_index = build_pristine_text_index(events=events)
        system_prompt = render_evaluator_prompt(
            template_name="evaluator_system.jinja",
            template_variables={},
        )
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_JUDGE_CALLS)
        measurements: list[Measurement] = []
        all_message_scores: list[_MessageScore] = []
        for channel in channels:
            rounds = _collect_link_messages_by_round(
                events=events,
                primary_channel_id=channel.channel_id,
                pristine_index=pristine_index,
            )
            if not rounds:
                logger.info("%s: no messages on primary channel %r", self.name, channel.channel_id)
                continue

            scored_rounds = await asyncio.gather(
                *[
                    _score_round(
                        llm_provider=llm_provider,
                        system_prompt=system_prompt,
                        round_messages=round_messages,
                        semaphore=semaphore,
                    )
                    for round_messages in rounds
                ]
            )
            message_scores = [score for round_scores in scored_rounds for score in round_scores]
            if not message_scores:
                logger.warning(
                    "%s: every judge replica failed on channel %r", self.name, channel.channel_id
                )
                continue
            all_message_scores.extend(message_scores)

            per_round = _per_round_observations(rounds=rounds, scored_rounds=scored_rounds)
            overall = statistics.fmean(obs.value for obs in per_round)
            max_factor = max(obs.value for obs in per_round)
            summary = (
                f"mean redundancy factor {overall:.2f}x across {len(per_round)} rounds on "
                f"{channel.channel_id} (max {max_factor:.2f}x), per-message judged over "
                f"{_JUDGE_REPLICAS} replicas; per-message factors in {_SIDECAR_FILENAME}"
            )
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=overall,
                    score_unit="mean encodings per information unit (x; 1.0 = no repetition)",
                    summary=summary,
                    per_round=per_round,
                    per_agent=[],
                )
            )

        if all_message_scores:
            _write_sidecar(run_dir=run_dir, message_scores=all_message_scores)
        return measurements


def _collect_link_messages_by_round(
    events: list[SimulationEvent],
    primary_channel_id: str,
    pristine_index: dict[str, str],
) -> list[_RoundMessages]:
    """Group primary-channel messages by round, in order, on pristine text."""
    by_round: dict[int, list[_LinkMessage]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id != primary_channel_id:
            continue
        text = pristine_text_for(index=pristine_index, message=event)
        if not text:
            continue
        by_round.setdefault(event.round_number, []).append(
            _LinkMessage(
                message_id=event.message.message_id,
                channel_id=event.message.channel_id,
                sender_agent_id=event.message.sender_agent_id,
                text=text,
            )
        )
    return [
        _RoundMessages(round_number=rn, messages=by_round[rn]) for rn in sorted(by_round.keys())
    ]


async def _score_round(
    llm_provider: LLMProvider,
    system_prompt: str,
    round_messages: _RoundMessages,
    semaphore: asyncio.Semaphore,
) -> list[_MessageScore]:
    """Judge one round's messages ``_JUDGE_REPLICAS`` times and average per message.

    Each replica returns one factor per enumerated message; factors are matched
    back by ``message_number`` and floored at 1.0. A message with no replica value
    falls back to 1.0 (no observed repetition).
    """
    enumerated = [
        {"number": index, "sender": message.sender_agent_id, "text": message.text}
        for index, message in enumerate(round_messages.messages, start=1)
    ]
    user_prompt = render_evaluator_prompt(
        template_name="language_repetition_user.jinja",
        template_variables={"round_number": round_messages.round_number, "messages": enumerated},
    )
    replicas = await asyncio.gather(
        *[
            _judge_once(
                llm_provider=llm_provider,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                semaphore=semaphore,
            )
            for _ in range(_JUDGE_REPLICAS)
        ]
    )

    factors_by_number: dict[int, list[float]] = {}
    for replica in replicas:
        if replica is None:
            continue
        for entry in replica.per_message:
            factors_by_number.setdefault(entry.message_number, []).append(
                max(1.0, entry.repetition_factor)
            )

    scores: list[_MessageScore] = []
    for index, message in enumerate(round_messages.messages, start=1):
        replica_factors = factors_by_number.get(index, [])
        mean_factor = statistics.fmean(replica_factors) if replica_factors else 1.0
        scores.append(
            _MessageScore(
                message=message,
                round_number=round_messages.round_number,
                message_number=index,
                mean_factor=mean_factor,
                replica_factors=replica_factors,
            )
        )
    return scores


async def _judge_once(
    llm_provider: LLMProvider,
    system_prompt: str,
    user_prompt: str,
    semaphore: asyncio.Semaphore,
) -> RoundRepetitionOutput | None:
    """One bounded judge call; returns ``None`` on failure so one bad call can't sink the run."""
    async with semaphore:
        try:
            return await llm_provider.generate_structured(
                system_prompt=system_prompt,
                messages=[LLMMessage(role="user", content=user_prompt)],
                output_schema=RoundRepetitionOutput,
            )
        except Exception:
            logger.exception("language_repetition: a judge replica failed")
            return None


def _per_round_observations(
    rounds: list[_RoundMessages],
    scored_rounds: list[list[_MessageScore]],
) -> list[RoundObservation]:
    """One observation per round: the mean per-message factor, with a spread note."""
    observations: list[RoundObservation] = []
    for round_messages, scores in zip(rounds, scored_rounds):
        if not scores:
            continue
        factors = [score.mean_factor for score in scores]
        mean_factor = statistics.fmean(factors)
        max_factor = max(factors)
        note = (
            f"{len(scores)} msgs, mean {mean_factor:.2f}x, max {max_factor:.2f}x "
            f"over {_JUDGE_REPLICAS} replicas"
        )
        observations.append(
            RoundObservation(
                round_number=round_messages.round_number,
                value=mean_factor,
                note=note,
            )
        )
    return observations


def _write_sidecar(run_dir: Path, message_scores: list[_MessageScore]) -> None:
    """Write one JSONL row per scored message, keyed by ``message_id``."""
    lines = [
        json.dumps(
            {
                "round_number": score.round_number,
                "message_number": score.message_number,
                "message_id": score.message.message_id,
                "channel_id": score.message.channel_id,
                "sender_agent_id": score.message.sender_agent_id,
                "repetition_factor": score.mean_factor,
                "replica_factors": score.replica_factors,
            }
        )
        for score in message_scores
    ]
    (run_dir / _SIDECAR_FILENAME).write_text("\n".join(lines) + "\n")
