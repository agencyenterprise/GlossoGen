"""Evaluator that measures how transparent the stabilization engineer's instructions were.

For each stage of each round's case (ground-truth data emitted via
``VeyruCaseStarted`` events), this evaluator replays the real simulation up to
the moment just before the field observer invoked ``stabilize_veyru`` for that
stage, shows the full chronological transcript to a fresh LLM, forces a new
``stabilize_veyru`` invocation, and judges the resulting action against
``judge_expected_actions`` using the existing ``judge_stabilization`` function.

The transcript is the exact context the real observer had: every round's
boundary, every ``veyru_case_started`` symptom reveal, every message on the
link channel from both the stabilization engineer and the real observer, and every prior
``stabilize_veyru`` tool call with its result. That includes cross-round
history, so the simulated observer can resolve references like "same technique
as round 2" the same way the real observer could.

Stage k's cutoff is the timestamp of the real observer's k-th
``stabilize_veyru`` invocation within that round; entries with strictly
earlier timestamps form the prompt. Rounds with fewer invocations than the
case has stages are scored only on the stages the real observer actually
attempted.

Per-round accuracy = matches / stages_attempted. Run score = mean across all
rounds that attempted at least one stage.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    MessageSent,
    RoundAdvanced,
    SimulationEvent,
    ToolCallInvoked,
    ToolResultReceived,
    VeyruCaseStarted,
)
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.prompt_renderer import render_veyru_prompt
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_ID,
    LINK_CHANNEL_ID,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    STABILIZATION_ENGINEER_ID,
    STABILIZE_VEYRU_TOOL,
)
from schmidt.scenarios.veyru.stabilization_judge import judge_stabilization

logger = logging.getLogger(__name__)


class StabilizeVeyruInvocation(BaseModel):
    """Apply a stabilization action to the current Veyru. \
Describe exactly what you are doing to stabilize it."""

    action: str = Field(
        description="Describe exactly what you are doing to stabilize the Veyru.",
    )


StabilizeVeyruInvocation.__name__ = STABILIZE_VEYRU_TOOL


class TranscriptEntry(NamedTuple):
    """One chronological line in the replayed observer transcript."""

    timestamp: datetime
    text: str


class RoundInputs(NamedTuple):
    """Per-round ground truth plus the real observer's stage-boundary timestamps."""

    round_number: int
    case: VeyruCaseStarted
    invocation_timestamps: list[datetime]


class StageResult(NamedTuple):
    """Outcome of a single simulated stabilize attempt for one stage."""

    round_number: int
    stage_index: int
    match: bool
    proposed_action: str
    expected_actions: str
    judge_explanation: str


class FieldObserverTransparencyEvaluator(Evaluator):
    """Replays the real observer's context per stage and scores LLM action accuracy.

    The score measures how likely a fresh observer placed in the exact
    conversational context the real observer had would have performed the
    correct stabilization — i.e., how transparent the stabilization engineer's
    instructions actually were in practice, given everything the observer
    already knew.
    """

    name = "field_observer_transparency"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Replay the transcript per stage and score the simulated observer's action."""
        _ = scenario, run_dir
        if _is_two_team_mode(agent_configs=agent_configs):
            logger.info("field_observer_transparency: two-team mode detected, returning FAIL")
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    "field_observer_transparency evaluator supports "
                    "single-team mode only; two-team runs are not yet evaluated."
                ],
                per_agent={},
                rounds_identified=[],
            )

        round_inputs = _extract_round_inputs(events=events)
        if not round_inputs:
            logger.info("field_observer_transparency: no veyru_case_started events found")
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    "field_observer_transparency evaluator requires "
                    "veyru_case_started events; this run predates that event "
                    "type — re-run the scenario to re-evaluate."
                ],
                per_agent={},
                rounds_identified=[],
            )

        transcript_entries = _build_transcript_entries(events=events)
        total_stages = sum(
            min(len(r.case.stages), len(r.invocation_timestamps)) for r in round_inputs
        )
        logger.info(
            "field_observer_transparency: %d round(s), %d scoreable stage(s), "
            "%d transcript entries",
            len(round_inputs),
            total_stages,
            len(transcript_entries),
        )

        stage_coros = [
            _score_stage(
                llm_provider=llm_provider,
                round_inputs=r,
                stage_index=stage_index,
                transcript_entries=transcript_entries,
            )
            for r in round_inputs
            for stage_index in range(min(len(r.case.stages), len(r.invocation_timestamps)))
        ]
        stage_results: list[StageResult] = list(await asyncio.gather(*stage_coros))
        for stage_result in stage_results:
            logger.info(
                "Round %d stage %d verdict: match=%s",
                stage_result.round_number,
                stage_result.stage_index,
                stage_result.match,
            )

        return _aggregate(
            evaluator_name=self.name,
            round_inputs=round_inputs,
            stage_results=stage_results,
        )


async def _score_stage(
    llm_provider: LLMProvider,
    round_inputs: RoundInputs,
    stage_index: int,
    transcript_entries: list[TranscriptEntry],
) -> StageResult:
    """Render the replayed transcript, force a stabilize_veyru call, then judge it."""
    stage = round_inputs.case.stages[stage_index]
    cutoff = round_inputs.invocation_timestamps[stage_index]
    transcript_text = _render_transcript(entries=transcript_entries, cutoff=cutoff)
    logger.info(
        "Round %d stage %d cutoff=%s transcript_lines=%d",
        round_inputs.round_number,
        stage_index,
        cutoff.isoformat(),
        transcript_text.count("\n") + 1 if transcript_text else 0,
    )
    logger.info(
        "Round %d stage %d ground truth expected_actions: %s",
        round_inputs.round_number,
        stage_index,
        stage.judge_expected_actions,
    )
    system_prompt = render_veyru_prompt(
        template_name="field_observer_transparency_system.jinja",
        template_variables={},
    )
    user_prompt = render_veyru_prompt(
        template_name="field_observer_transparency_user.jinja",
        template_variables={
            "round_number": round_inputs.round_number,
            "transcript": transcript_text,
        },
    )
    logger.debug(
        "Round %d stage %d full user prompt:\n%s",
        round_inputs.round_number,
        stage_index,
        user_prompt,
    )
    invocation = await llm_provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_prompt)],
        output_schema=StabilizeVeyruInvocation,
    )
    logger.info(
        "Round %d stage %d simulated observer proposed action: %s",
        round_inputs.round_number,
        stage_index,
        invocation.action,
    )
    judgment = await judge_stabilization(
        provider=llm_provider,
        expected_actions=stage.judge_expected_actions,
        observer_action=invocation.action,
    )
    return StageResult(
        round_number=round_inputs.round_number,
        stage_index=stage_index,
        match=judgment.match,
        proposed_action=invocation.action,
        expected_actions=stage.judge_expected_actions,
        judge_explanation=judgment.explanation,
    )


def _render_transcript(entries: list[TranscriptEntry], cutoff: datetime) -> str:
    """Return a newline-joined transcript of entries with timestamp strictly before ``cutoff``."""
    return "\n".join(entry.text for entry in entries if entry.timestamp < cutoff)


def _build_transcript_entries(events: list[SimulationEvent]) -> list[TranscriptEntry]:
    """Build the chronological transcript the real field observer would have seen.

    Covers cross-round history: round boundaries, each case's initial symptom
    reveal, every link-channel message (both sides), every ``stabilize_veyru``
    tool call by the observer with its verbatim action argument, and every
    ``stabilize_veyru`` tool result returned to the observer.
    """
    entries: list[TranscriptEntry] = []
    for event in events:
        if isinstance(event, RoundAdvanced):
            entries.append(
                TranscriptEntry(
                    timestamp=event.timestamp,
                    text=f"[Round {event.round_number} started — trigger: {event.trigger}]",
                )
            )
            continue
        if isinstance(event, VeyruCaseStarted):
            first_stage = event.stages[0] if event.stages else None
            if first_stage is None:
                continue
            entries.append(
                TranscriptEntry(
                    timestamp=event.timestamp,
                    text=(
                        f"[Round {event.round_number}] New Veyru presented. "
                        f"Initial observable symptoms:\n{first_stage.observable_symptoms}"
                    ),
                )
            )
            continue
        if isinstance(event, MessageSent):
            if event.message.channel_id != LINK_CHANNEL_ID:
                continue
            sender = event.message.sender_agent_id
            if sender == STABILIZATION_ENGINEER_ID:
                label = "engineer"
            elif sender == FIELD_OBSERVER_ID:
                label = "you (field observer)"
            else:
                label = sender
            entries.append(
                TranscriptEntry(
                    timestamp=event.message.timestamp,
                    text=(
                        f"[Round {event.round_number}] {label} (link): " f'"{event.message.text}"'
                    ),
                )
            )
            continue
        if isinstance(event, ToolCallInvoked):
            if event.tool_name != STABILIZE_VEYRU_TOOL:
                continue
            if event.agent_id != FIELD_OBSERVER_ID:
                continue
            action = event.arguments.get("action", "")
            entries.append(
                TranscriptEntry(
                    timestamp=event.timestamp,
                    text=(
                        f"[Round {event.round_number}] you invoked "
                        f'stabilize_veyru(action="{action}")'
                    ),
                )
            )
            continue
        if isinstance(event, ToolResultReceived):
            if event.tool_name != STABILIZE_VEYRU_TOOL:
                continue
            if event.agent_id != FIELD_OBSERVER_ID:
                continue
            entries.append(
                TranscriptEntry(
                    timestamp=event.timestamp,
                    text=(
                        f"[Round {event.round_number}] stabilize_veyru tool "
                        f"result: {event.result}"
                    ),
                )
            )
            continue
    entries.sort(key=lambda entry: entry.timestamp)
    return entries


def _extract_round_inputs(events: list[SimulationEvent]) -> list[RoundInputs]:
    """Group ground-truth cases with the real observer's per-round stabilize timestamps."""
    cases_by_round: dict[int, VeyruCaseStarted] = {}
    invocations_by_round: dict[int, list[datetime]] = {}

    for event in events:
        if isinstance(event, VeyruCaseStarted):
            cases_by_round[event.round_number] = event
            continue
        if isinstance(event, ToolCallInvoked):
            if event.tool_name != STABILIZE_VEYRU_TOOL:
                continue
            if event.agent_id != FIELD_OBSERVER_ID:
                continue
            invocations_by_round.setdefault(event.round_number, []).append(event.timestamp)
            continue

    out: list[RoundInputs] = []
    for rn in sorted(cases_by_round.keys()):
        timestamps = sorted(invocations_by_round.get(rn, []))
        out.append(
            RoundInputs(
                round_number=rn,
                case=cases_by_round[rn],
                invocation_timestamps=timestamps,
            )
        )
    return out


def _aggregate(
    evaluator_name: str,
    round_inputs: list[RoundInputs],
    stage_results: list[StageResult],
) -> MetricResult:
    """Compute mean per-round accuracy, verdict, and evidence lines."""
    per_round_matches: dict[int, int] = {}
    per_round_total: dict[int, int] = {}
    for result in stage_results:
        per_round_total[result.round_number] = per_round_total.get(result.round_number, 0) + 1
        if result.match:
            per_round_matches[result.round_number] = (
                per_round_matches.get(result.round_number, 0) + 1
            )
    per_round_accuracy: dict[int, float] = {
        rn: per_round_matches.get(rn, 0) / total
        for rn, total in per_round_total.items()
        if total > 0
    }

    if per_round_accuracy:
        score = sum(per_round_accuracy.values()) / len(per_round_accuracy)
    else:
        score = 0.0
    verdict = _score_to_verdict(score=score)
    rounds_identified = sorted(rn for rn, acc in per_round_accuracy.items() if acc == 1.0)
    for rn in sorted(per_round_accuracy.keys()):
        logger.info(
            "Aggregate — Round %d: %d/%d stages matched (accuracy=%.2f)",
            rn,
            per_round_matches.get(rn, 0),
            per_round_total[rn],
            per_round_accuracy[rn],
        )
    logger.info(
        "Aggregate — overall mean accuracy=%.4f across %d round(s), verdict=%s",
        score,
        len(per_round_accuracy),
        verdict.value,
    )

    evidence: list[str] = [
        f"Mean per-round transparency accuracy: {score:.2f} across "
        f"{len(per_round_accuracy)} round(s)."
    ]
    for r in round_inputs:
        rn = r.round_number
        if rn not in per_round_total:
            continue
        matches = per_round_matches.get(rn, 0)
        total = per_round_total[rn]
        evidence.append(f"Round {rn}: {matches}/{total} stages matched.")
    for result in stage_results:
        if result.match:
            continue
        explanation = result.judge_explanation.strip().replace("\n", " ")
        if len(explanation) > 240:
            explanation = explanation[:240] + "..."
        proposed = result.proposed_action.strip().replace("\n", " ")
        if len(proposed) > 160:
            proposed = proposed[:160] + "..."
        evidence.append(
            f"Round {result.round_number} stage {result.stage_index + 1} MISS — "
            f"proposed: {proposed} — {explanation}"
        )

    return MetricResult(
        evaluator_name=evaluator_name,
        verdict=verdict,
        score=score,
        evidence=evidence,
        per_agent={},
        rounds_identified=rounds_identified,
    )


def _score_to_verdict(score: float) -> Verdict:
    """Map a 0-1 transparency score to pass/partial/fail."""
    if score >= 0.8:
        return Verdict.PASS
    if score >= 0.5:
        return Verdict.PARTIAL
    return Verdict.FAIL


def _is_two_team_mode(agent_configs: list[AgentConfig]) -> bool:
    """Detect two-team mode from the set of registered agent IDs."""
    agent_ids = {config.agent_id for config in agent_configs}
    return OBSERVER_A_ID in agent_ids and OBSERVER_B_ID in agent_ids
