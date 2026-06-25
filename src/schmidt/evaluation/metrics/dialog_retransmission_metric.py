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

One judge call per run returns per-round counts; the metric emits two Measurements
(``dialog_count`` and ``retransmission_request_count``), each scored as the mean count per
round.

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

import logging
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

_DIALOG_MEASUREMENT = "dialog_count"
_RETRANSMISSION_MEASUREMENT = "retransmission_request_count"


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


class DialogRetransmissionMetric(Metric):
    """Counts dialog and retransmission-request messages per round via an LLM judge.

    Emits two Measurements — ``dialog_count`` and ``retransmission_request_count`` — each
    scored as the mean count per round across the run. Scenarios with no messages get a
    no-op result.
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
        """Count dialog and retransmission-request messages per round."""
        _ = agent_configs, run_dir, options
        round_transcripts = build_round_transcripts(
            events=events,
            scenario=scenario,
            pristine_index=build_pristine_text_index(events=events),
        )
        if not round_transcripts:
            logger.info("%s: skipping — no messages found", self.name)
            return []

        judge_prompt = render_evaluator_prompt(
            template_name="dialog_retransmission_user.jinja",
            template_variables={"rounds": round_transcripts},
        )
        result = await llm_provider.generate_structured(
            system_prompt=render_evaluator_prompt(
                template_name="evaluator_system.jinja",
                template_variables={},
            ),
            messages=[LLMMessage(role="user", content=judge_prompt)],
            output_schema=DialogRetransmissionOutput,
        )

        total_rounds = len(round_transcripts)
        dialog_measurement = _build_measurement(
            metric_name=_DIALOG_MEASUREMENT,
            label="dialog",
            counts=[(c.round_number, c.dialog_count, c.evidence) for c in result.per_round_counts],
            total_rounds=total_rounds,
            explanation=result.explanation,
        )
        retransmission_measurement = _build_measurement(
            metric_name=_RETRANSMISSION_MEASUREMENT,
            label="retransmission request",
            counts=[
                (c.round_number, c.retransmission_request_count, c.evidence)
                for c in result.per_round_counts
            ],
            total_rounds=total_rounds,
            explanation=result.explanation,
        )
        return [dialog_measurement, retransmission_measurement]


def _build_measurement(
    metric_name: str,
    label: str,
    counts: list[tuple[int, int, str]],
    total_rounds: int,
    explanation: str,
) -> Measurement:
    """Build one Measurement from per-round (round, count, evidence) triples.

    ``score`` is the mean count per round across all rounds (zero rounds are omitted from
    ``counts`` but still divide the total). ``per_round`` lists only rounds with a non-zero
    count, mirroring the flag-style LLM-judge metrics.
    """
    per_round = [
        RoundObservation(round_number=round_number, value=float(count), note=evidence)
        for round_number, count, evidence in counts
        if count > 0
    ]
    total_count = sum(count for _, count, _ in counts)
    mean_per_round = 0.0
    if total_rounds > 0:
        mean_per_round = total_count / total_rounds
    summary = (
        f"{total_count} {label} messages across {total_rounds} rounds "
        f"(mean {mean_per_round:.3f}/round, in {len(per_round)} rounds). {explanation}"
    )
    return Measurement(
        metric_name=metric_name,
        score=mean_per_round,
        score_unit=f"{label} messages/round",
        summary=summary,
        per_round=per_round,
        per_agent=[],
    )
