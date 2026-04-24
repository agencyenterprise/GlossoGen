"""Evaluator that measures how transparent the specialist's instructions were.

For each stage of each round's case (ground-truth data emitted via
``VeyruCaseStarted`` events), this evaluator presents a neutral simulated
field observer with the stage's ``observable_symptoms`` plus the specialist's
messages from that round, forces an invocation of the real ``stabilize_veyru``
tool, and judges the resulting action against the ground-truth
``judge_expected_actions`` using the existing ``judge_stabilization`` function.

Specialist messages are split across stages using ``STABILIZATION_SUCCESS_MARKER``
timestamps in ``ToolResultReceived`` events as stage boundaries: stage k gets
every specialist message sent through the k-th success. When a round collapses
before reaching stage k, the full round's specialist transcript is used instead.

Per-round accuracy = matches / stages. Run score = mean across all rounds.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent, ToolResultReceived, VeyruCaseStarted
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.prompt_renderer import render_veyru_prompt
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_ID,
    LINK_CHANNEL_ID,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    SPECIALIST_ID,
    STABILIZATION_SUCCESS_MARKER,
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


class RoundInputs(NamedTuple):
    """Everything needed to evaluate a single round."""

    round_number: int
    case: VeyruCaseStarted
    specialist_messages: list[tuple[datetime, str]]
    success_timestamps: list[datetime]


class StageResult(NamedTuple):
    """Outcome of a single simulated stabilize attempt for one stage."""

    round_number: int
    stage_index: int
    match: bool
    proposed_action: str
    expected_actions: str
    judge_explanation: str


class FieldObserverTransparencyEvaluator(Evaluator):
    """Measures whether the specialist's instructions were clear enough that
    a naive observer could execute them correctly from the channel transcript
    alone, without the real observer's own contributions.
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
        """Simulate a neutral observer per case stage and score accuracy."""
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

        total_stages = sum(len(r.case.stages) for r in round_inputs)
        logger.info(
            "field_observer_transparency: %d round(s), %d stage(s) total to evaluate",
            len(round_inputs),
            total_stages,
        )
        for r in round_inputs:
            logger.info(
                "Round %d plan: case_number=%d failure=%r stages=%d "
                "specialist_messages=%d success_markers=%d",
                r.round_number,
                r.case.case_number,
                r.case.failure_name,
                len(r.case.stages),
                len(r.specialist_messages),
                len(r.success_timestamps),
            )

        stage_results: list[StageResult] = []
        stage_counter = 0
        for r in round_inputs:
            for stage_index in range(len(r.case.stages)):
                stage_counter += 1
                logger.info(
                    "=== Evaluating stage %d/%d (round %d, stage_index %d) ===",
                    stage_counter,
                    total_stages,
                    r.round_number,
                    stage_index,
                )
                stage_result = await _score_stage(
                    llm_provider=llm_provider,
                    round_inputs=r,
                    stage_index=stage_index,
                )
                stage_results.append(stage_result)
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
) -> StageResult:
    """Render the prompts, force a stabilize_veyru tool call, then judge the action."""
    stage = round_inputs.case.stages[stage_index]
    specialist_lines = _specialist_messages_for_stage(
        messages=round_inputs.specialist_messages,
        success_timestamps=round_inputs.success_timestamps,
        stage_index=stage_index,
    )
    logger.info(
        "Round %d stage %d input — observed symptoms:\n%s",
        round_inputs.round_number,
        stage_index,
        stage.observable_symptoms,
    )
    if specialist_lines:
        logger.info(
            "Round %d stage %d input — %d specialist message(s) on link:\n%s",
            round_inputs.round_number,
            stage_index,
            len(specialist_lines),
            "\n".join(specialist_lines),
        )
    else:
        logger.info(
            "Round %d stage %d input — specialist sent no messages in this round",
            round_inputs.round_number,
            stage_index,
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
            "observed_symptoms": stage.observable_symptoms,
            "specialist_messages": specialist_lines,
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


def _specialist_messages_for_stage(
    messages: list[tuple[datetime, str]],
    success_timestamps: list[datetime],
    stage_index: int,
) -> list[str]:
    """Return the specialist message strings that belong to this stage's window.

    Stage k is bounded by the k-th ``STABILIZATION_SUCCESS_MARKER`` timestamp:
    all specialist messages with ``ts <= successes[k]`` are included. When the
    round collapsed before reaching stage k (``k >= len(successes)``), the full
    round's specialist transcript is used so the simulated observer still has
    whatever the specialist actually said to work with.
    """
    if stage_index < len(success_timestamps):
        cutoff = success_timestamps[stage_index]
        return [f"- {text}" for ts, text in messages if ts <= cutoff]
    return [f"- {text}" for _, text in messages]


def _extract_round_inputs(events: list[SimulationEvent]) -> list[RoundInputs]:
    """Group ground-truth case events with per-round message + success data."""
    cases_by_round: dict[int, VeyruCaseStarted] = {}
    specialist_by_round: dict[int, list[tuple[datetime, str]]] = {}
    successes_by_round: dict[int, list[datetime]] = {}

    for event in events:
        if isinstance(event, VeyruCaseStarted):
            cases_by_round[event.round_number] = event
            continue
        if isinstance(event, MessageSent):
            if event.message.channel_id != LINK_CHANNEL_ID:
                continue
            if event.message.sender_agent_id != SPECIALIST_ID:
                continue
            specialist_by_round.setdefault(event.round_number, []).append(
                (event.message.timestamp, event.message.text)
            )
            continue
        if isinstance(event, ToolResultReceived):
            if event.tool_name != STABILIZE_VEYRU_TOOL:
                continue
            if event.agent_id != FIELD_OBSERVER_ID:
                continue
            if STABILIZATION_SUCCESS_MARKER not in event.result:
                continue
            successes_by_round.setdefault(event.round_number, []).append(event.timestamp)
            continue

    return [
        RoundInputs(
            round_number=rn,
            case=cases_by_round[rn],
            specialist_messages=specialist_by_round.get(rn, []),
            success_timestamps=successes_by_round.get(rn, []),
        )
        for rn in sorted(cases_by_round.keys())
    ]


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
