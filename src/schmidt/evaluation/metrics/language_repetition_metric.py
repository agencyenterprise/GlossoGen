"""Metric that measures how much agents redundantly re-encode information.

Under channel noise, agents defend against character loss by encoding the same
information more than once — repeating tokens (``Lf Lf 12 12 gentle gentle``),
dual-encoding a value two ways (``12 twelve``, ``12twelve``), or pairing an
abbreviation with its full word (``gnt gentle``). An LLM judge reads each round's
primary-channel transcript (on the *pristine* text the agent composed, before the
noise transform) and counts, per round, the number of distinct pieces of
information conveyed and the total number of encodings of them. The metric derives
a per-round redundancy factor ``total_encodings / distinct_units`` (>= 1.0,
unbounded above).

The judge is called ``_JUDGE_REPLICAS`` times per run; each round's factor is
averaged across the replicas that scored it, and the per-replica spread is
recorded in the observation note so judge disagreement (e.g. on how to count a
character run) is visible. The headline score is the mean averaged factor across
rounds.
"""

import asyncio
import logging
import statistics
from pathlib import Path

from pydantic import BaseModel, Field

from schmidt.evaluation.metric_core.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from schmidt.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from schmidt.evaluation.round_transcript_builder import build_round_transcripts
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_JUDGE_REPLICAS = 3


class RoundRedundancy(BaseModel):
    """Per-round encoding counts judged on the primary channel."""

    round_number: int = Field(
        description="The round these counts apply to.",
    )
    distinct_units: int = Field(
        description=(
            "Number of DISTINCT pieces of information conveyed on the PRIMARY "
            "CHANNEL this round — each value/instruction/field counted once "
            "(a motif name, a face, an intensity, a duration, a count, a "
            "confirmation, ...)."
        ),
    )
    total_encodings: int = Field(
        description=(
            "Total times those units were transmitted, counting EVERY copy and "
            "EVERY alternate form of the same unit. 'T1 T1 T1' adds 3 for that "
            "unit; '12 twelve' adds 2; 'gnt gentle' adds 2. Always >= distinct_units."
        ),
    )
    examples: list[str] = Field(
        description="Most-repeated units with multiplicity, e.g. 'T1 x3', '12/twelve x2'.",
    )


class LanguageRepetitionOutput(BaseModel):
    """LLM judge output for the language-repetition evaluation."""

    per_round: list[RoundRedundancy] = Field(
        description="One entry per round that had primary-channel messages.",
    )
    explanation: str = Field(
        description="Overall reasoning, citing specific examples from the transcripts.",
    )


class LanguageRepetitionMetric(Metric):
    """Measures per-round redundant re-encoding of information on the primary channel.

    Fires the judge ``_JUDGE_REPLICAS`` times and averages each round's redundancy
    factor (mean encodings per distinct information unit, floored at 1.0) across
    replicas; the headline score is the mean averaged factor across rounds with
    primary-channel content. Scenarios with no messages get a no-op result.
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
        """Judge per-round redundancy on pristine primary-channel text, averaged over replicas."""
        _ = agent_configs, run_dir, options
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
            pristine_index=build_pristine_text_index(events=events),
        )
        if not round_transcripts:
            logger.info("%s: skipping — no messages found", self.name)
            return []

        system_prompt = render_evaluator_prompt(
            template_name="evaluator_system.jinja",
            template_variables={},
        )
        user_prompt = render_evaluator_prompt(
            template_name="language_repetition_user.jinja",
            template_variables={"rounds": round_transcripts},
        )
        raw_replicas = await asyncio.gather(
            *[
                llm_provider.generate_structured(
                    system_prompt=system_prompt,
                    messages=[LLMMessage(role="user", content=user_prompt)],
                    output_schema=LanguageRepetitionOutput,
                )
                for _ in range(_JUDGE_REPLICAS)
            ],
            return_exceptions=True,
        )
        replicas = [r for r in raw_replicas if isinstance(r, LanguageRepetitionOutput)]
        for failure in (r for r in raw_replicas if isinstance(r, BaseException)):
            logger.warning("%s: a judge replica failed: %r", self.name, failure)
        if not replicas:
            logger.warning("%s: all %d judge replicas failed", self.name, _JUDGE_REPLICAS)
            return []

        transcript_rounds = {transcript.round_number for transcript in round_transcripts}
        per_round = _aggregate_replicas(replicas=replicas, transcript_rounds=transcript_rounds)
        if not per_round:
            logger.info(
                "%s: skipping — no primary-channel rounds with scorable content",
                self.name,
            )
            return []

        overall = sum(obs.value for obs in per_round) / len(per_round)
        max_factor = max(obs.value for obs in per_round)
        summary = (
            f"mean redundancy factor {overall:.2f}x across {len(per_round)} rounds "
            f"(max {max_factor:.2f}x) over {len(replicas)} judge replicas. "
            f"{replicas[0].explanation}"
        )
        return [
            Measurement(
                metric_name=self.name,
                score=overall,
                score_unit="mean encodings per information unit (x; 1.0 = no repetition)",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]


def _aggregate_replicas(
    replicas: list[LanguageRepetitionOutput],
    transcript_rounds: set[int],
) -> list[RoundObservation]:
    """Average each round's redundancy factor across judge replicas.

    For each round present in the transcript, collects the factor from every
    replica that scored it (``distinct_units > 0``), averages them, and records
    the per-replica factors + spread in the note so judge disagreement (e.g. on
    how to count a character run) is visible. Examples are taken from the first
    replica that scored the round. Rounds no replica scored are skipped, mirroring
    how ``perplexity`` / ``mcm`` skip message-less rounds.
    """
    factors_by_round: dict[int, list[float]] = {}
    examples_by_round: dict[int, list[str]] = {}
    for replica in replicas:
        for redundancy in replica.per_round:
            if redundancy.round_number not in transcript_rounds:
                continue
            if redundancy.distinct_units <= 0:
                continue
            factor = max(1.0, redundancy.total_encodings / redundancy.distinct_units)
            factors_by_round.setdefault(redundancy.round_number, []).append(factor)
            if redundancy.round_number not in examples_by_round and redundancy.examples:
                examples_by_round[redundancy.round_number] = redundancy.examples

    observations: list[RoundObservation] = []
    for round_number in sorted(factors_by_round):
        factors = factors_by_round[round_number]
        mean_factor = statistics.fmean(factors)
        spread = statistics.pstdev(factors) if len(factors) > 1 else 0.0
        rendered = ", ".join(f"{factor:.2f}" for factor in factors)
        note = (
            f"mean {mean_factor:.2f}x over {len(factors)}/{len(replicas)} replicas "
            f"[{rendered}], std {spread:.2f}"
        )
        examples = examples_by_round.get(round_number, [])
        if examples:
            note += f" (e.g. {'; '.join(examples)})"
        observations.append(
            RoundObservation(round_number=round_number, value=mean_factor, note=note)
        )
    return observations
