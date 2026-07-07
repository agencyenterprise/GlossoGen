"""LLM-judge metric counting dialog and retransmission-request messages per round.

For each round, an LLM judge reads that round's primary-channel transcript and counts
two distinct kinds of message:

- **retransmission requests** — a message asking the partner to repeat or resend
  information that was lost or garbled (e.g. "say again", "resend the pressure value",
  "didn't catch last"); the natural consequence of a noisy channel.
- **dialog** — clarification / coordination back-and-forth that is *not* transmitting new
  task data (asking for clarification, confirming or acknowledging receipt, coordinating
  turns). Pure retransmission requests are counted in their own bucket, not double-counted
  as dialog.

The whole-run judge call is made ``_JUDGE_REPLICAS`` times and the per-round counts are
**averaged across replicas** (a replica that omits a round contributes 0 for it), which
smooths the LLM judge's run-to-run variance. The metric then emits two Measurements
(``dialog_count`` and ``retransmission_request_count``), each scored as the mean averaged
count per round.

Because the agents' communication protocol evolves into terse, coded shorthand, a single
message can be cryptic in isolation. The judge therefore receives the **full run context**:
every round's transcript (so the protocol's evolution is visible) with each round split into
its primary-channel messages and its other-channel messages — including the **postmortem**
debriefs where agents establish and explain their codes. The prompt directs the judge to use
that context as a codebook to decode terse primary-channel messages before classifying them,
and to infer communicative intent from meaning rather than surface cues like question marks.
The transcript renders the **pristine** composed text (resolved via the ``message_id`` link)
so protocol shorthand is read without extra channel-noise garbling on top.
"""

import asyncio
import logging
import statistics
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from glossogen.evaluation.prompts.prompt_renderer import render_evaluator_prompt
from glossogen.evaluation.round_transcript_builder import build_round_transcripts
from glossogen.llm.provider import LLMMessage, LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_DIALOG_MEASUREMENT = "dialog_count"
_RETRANSMISSION_MEASUREMENT = "retransmission_request_count"
_JUDGE_REPLICAS = 3


class RoundCommCounts(BaseModel):
    """Per-round counts of dialog and retransmission-request messages."""

    round_number: int = Field(description="The round number these counts apply to.")
    dialog_count: int = Field(
        description=(
            "Number of messages this round that are dialog: clarification or coordination "
            "back-and-forth not transmitting new task data (asking for clarification, "
            "confirming/acknowledging receipt, coordinating turns). Do NOT count pure "
            "retransmission requests here. 0 if none."
        ),
    )
    retransmission_request_count: int = Field(
        description=(
            "Number of messages this round that ask the partner to repeat or resend "
            "information that was lost or garbled (e.g. 'say again', 'resend pressure', "
            "'didn't catch last'). 0 if none."
        ),
    )
    evidence: str = Field(
        description="Brief examples from this round supporting the counts (quote fragments).",
    )


class DialogRetransmissionOutput(BaseModel):
    """LLM judge output: per-round dialog and retransmission-request counts."""

    per_round_counts: list[RoundCommCounts] = Field(
        description=(
            "One entry for EVERY round that has at least one dialog message or one "
            "retransmission request. Omit rounds where both counts are 0."
        ),
    )
    explanation: str = Field(
        description="Overall reasoning, citing specific examples from the transcripts.",
    )


class _RoundAverage(NamedTuple):
    """A round's per-replica counts and their mean, for one phenomenon."""

    round_number: int
    mean_count: float
    replica_counts: list[int]
    evidence: str


class DialogRetransmissionMetric(Metric):
    """Counts dialog and retransmission-request messages per round via an LLM judge.

    Runs the judge ``_JUDGE_REPLICAS`` times and averages the per-round counts, then emits
    two Measurements — ``dialog_count`` and ``retransmission_request_count`` — each scored as
    the mean averaged count per round across the run. Scenarios with no messages get a no-op
    result.
    """

    name = "dialog_retransmission"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Count dialog and retransmission-request messages per round, averaged over replicas."""
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
        judge_prompt = render_evaluator_prompt(
            template_name="dialog_retransmission_user.jinja",
            template_variables={"rounds": round_transcripts},
        )
        replicas = await asyncio.gather(
            *[
                _judge_once(
                    llm_provider=llm_provider,
                    system_prompt=system_prompt,
                    user_prompt=judge_prompt,
                )
                for _ in range(_JUDGE_REPLICAS)
            ]
        )
        successful = [replica for replica in replicas if replica is not None]
        if not successful:
            logger.warning("%s: every judge replica failed", self.name)
            return []

        round_numbers = [transcript.round_number for transcript in round_transcripts]
        dialog_averages = _average_replicas(
            replicas=successful,
            round_numbers=round_numbers,
            select_dialog=True,
        )
        retransmission_averages = _average_replicas(
            replicas=successful,
            round_numbers=round_numbers,
            select_dialog=False,
        )
        return [
            _build_measurement(
                metric_name=_DIALOG_MEASUREMENT,
                label="dialog",
                averages=dialog_averages,
                total_rounds=len(round_numbers),
                replica_count=len(successful),
                explanation=successful[0].explanation,
            ),
            _build_measurement(
                metric_name=_RETRANSMISSION_MEASUREMENT,
                label="retransmission request",
                averages=retransmission_averages,
                total_rounds=len(round_numbers),
                replica_count=len(successful),
                explanation=successful[0].explanation,
            ),
        ]


async def _judge_once(
    llm_provider: LLMProvider,
    system_prompt: str,
    user_prompt: str,
) -> DialogRetransmissionOutput | None:
    """One judge replica; returns ``None`` on failure so one bad call can't sink the run."""
    try:
        return await llm_provider.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=user_prompt)],
            output_schema=DialogRetransmissionOutput,
        )
    except Exception:
        logger.exception("dialog_retransmission: a judge replica failed")
        return None


def _average_replicas(
    replicas: list[DialogRetransmissionOutput],
    round_numbers: list[int],
    select_dialog: bool,
) -> list[_RoundAverage]:
    """Average one phenomenon's per-round counts across replicas (omitted round = 0)."""
    by_replica: list[dict[int, RoundCommCounts]] = [
        {counts.round_number: counts for counts in replica.per_round_counts} for replica in replicas
    ]
    averages: list[_RoundAverage] = []
    for round_number in round_numbers:
        replica_counts = [
            _count_for(counts=mapping.get(round_number), select_dialog=select_dialog)
            for mapping in by_replica
        ]
        evidence = _first_evidence(
            by_replica=by_replica, round_number=round_number, select_dialog=select_dialog
        )
        averages.append(
            _RoundAverage(
                round_number=round_number,
                mean_count=statistics.fmean(replica_counts),
                replica_counts=replica_counts,
                evidence=evidence,
            )
        )
    return averages


def _count_for(counts: RoundCommCounts | None, select_dialog: bool) -> int:
    """The selected phenomenon's count for one round/replica; 0 when the replica omitted it."""
    if counts is None:
        return 0
    if select_dialog:
        return counts.dialog_count
    return counts.retransmission_request_count


def _first_evidence(
    by_replica: list[dict[int, RoundCommCounts]], round_number: int, select_dialog: bool
) -> str:
    """First non-empty evidence among replicas that reported a non-zero count for this round."""
    for mapping in by_replica:
        counts = mapping.get(round_number)
        if counts is None:
            continue
        if _count_for(counts=counts, select_dialog=select_dialog) > 0 and counts.evidence:
            return counts.evidence
    return ""


def _build_measurement(
    metric_name: str,
    label: str,
    averages: list[_RoundAverage],
    total_rounds: int,
    replica_count: int,
    explanation: str,
) -> Measurement:
    """Build one Measurement from per-round replica-averaged counts.

    ``score`` is the mean averaged count per round across all rounds (rounds averaging to 0
    still divide the total). ``per_round`` lists only rounds with a non-zero averaged count,
    each noting its per-replica counts so the judge's stability is visible.
    """
    per_round = [
        RoundObservation(
            round_number=average.round_number,
            value=average.mean_count,
            note=f"replicas={average.replica_counts}; {average.evidence}",
        )
        for average in averages
        if average.mean_count > 0
    ]
    total_count = sum(average.mean_count for average in averages)
    mean_per_round = 0.0
    if total_rounds > 0:
        mean_per_round = total_count / total_rounds
    summary = (
        f"mean {label} {mean_per_round:.3f}/round across {total_rounds} rounds "
        f"(averaged over {replica_count} judge replicas, in {len(per_round)} rounds). "
        f"{explanation}"
    )
    return Measurement(
        metric_name=metric_name,
        score=mean_per_round,
        score_unit=f"{label} messages/round",
        summary=summary,
        per_round=per_round,
        per_agent=[],
    )
