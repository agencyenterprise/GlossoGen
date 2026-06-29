"""LLM-based judge that evaluates whether the technician's free-text
replacement action carries out the expected multi-step service procedure
(unit + component + every ordered step with its parameters) for the current
stage.

Uses ``generate_structured`` to get a validated yes/no judgment with an
explanation from the configured judge model. To suppress per-call
non-determinism, the verdict is the majority across ``JUDGE_VOTE_COUNT``
independent calls.
"""

import asyncio
import logging
from pathlib import Path

from pydantic import BaseModel

from schmidt.llm.provider import LLMMessage, LLMProvider, SamplingParams
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])

JUDGE_VOTE_COUNT = 1
JUDGE_TEMPERATURE = 0.0


class ReplacementJudgment(BaseModel):
    """Structured output from the replacement judge LLM call."""

    match: bool
    explanation: str


async def judge_replacement(
    provider: LLMProvider,
    expected_action: str,
    technician_action: str,
) -> ReplacementJudgment:
    """Ask the LLM judge whether the technician's action matches the expected one.

    ``expected_action`` is the pre-rendered correct replacement: the unit and
    component followed by the ordered multi-step service procedure (tool,
    torque, passes, calibration, and class-specific counts / patterns / hold
    durations). The judge applies a "naive reader" test: the action must
    reconstruct the full procedure in plain English (private codes allowed only
    as decoration alongside the full word), and the expected procedure is never
    used to decode the action. It is lenient on wording but strict on the unit,
    the component, and every step with its parameters, in order.

    Runs ``JUDGE_VOTE_COUNT`` independent judge calls concurrently and returns
    the majority verdict.
    """
    system_prompt = _renderer.render(
        template_name="replacement_judge.jinja",
        template_variables={},
    )
    user_message = (
        f"Expected replacement:\n{expected_action}\n\n"
        f"Technician's reported action:\n{technician_action}"
    )
    logger.info(
        "Replacement judge input: expected=[%s] action=[%s]",
        expected_action,
        technician_action,
    )
    judgments = await asyncio.gather(
        *[
            provider.generate_structured(
                system_prompt=system_prompt,
                messages=[LLMMessage(role="user", content=user_message)],
                output_schema=ReplacementJudgment,
                sampling=SamplingParams(temperature=JUDGE_TEMPERATURE),
            )
            for _ in range(JUDGE_VOTE_COUNT)
        ]
    )
    match_votes = sum(1 for judgment in judgments if judgment.match)
    majority_match = match_votes * 2 > JUDGE_VOTE_COUNT
    representative = next(judgment for judgment in judgments if judgment.match == majority_match)
    logger.info(
        "Replacement judge result (%d/%d match votes): match=%s — %s",
        match_votes,
        JUDGE_VOTE_COUNT,
        majority_match,
        representative.explanation,
    )
    return ReplacementJudgment(match=majority_match, explanation=representative.explanation)
