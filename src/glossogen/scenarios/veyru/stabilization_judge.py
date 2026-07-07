"""LLM-based judge that evaluates whether a field observer's stabilization
action matches the expected procedure for a Veyru failure case.

Uses ``generate_structured`` to get a validated yes/no judgment with an
explanation from the configured judge model. To suppress per-call
non-determinism, the verdict is the majority across ``JUDGE_VOTE_COUNT``
independent calls.
"""

import asyncio
import logging
from pathlib import Path

from pydantic import BaseModel

from glossogen.llm.provider import LLMMessage, LLMProvider, SamplingParams
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])

JUDGE_VOTE_COUNT = 1
JUDGE_TEMPERATURE = 0.0


class StabilizationJudgment(BaseModel):
    """Structured output from the stabilization judge LLM call."""

    match: bool
    explanation: str


async def judge_stabilization(
    provider: LLMProvider,
    expected_actions: str,
    observer_action: str,
) -> StabilizationJudgment:
    """Ask the LLM judge whether the observer's action matches the expected procedure.

    ``expected_actions`` is a pre-rendered description of the correct
    procedure with stellar parameters already baked in — no conflicting
    numbers for the judge to resolve.

    Runs ``JUDGE_VOTE_COUNT`` independent judge calls concurrently and returns
    the majority verdict. The returned explanation is taken from one call that
    agrees with the majority.
    """
    system_prompt = _renderer.render(
        template_name="stabilization_judge.jinja",
        template_variables={},
    )
    user_message = (
        f"Expected procedure:\n{expected_actions}\n\n"
        f"Field observer's reported action:\n{observer_action}"
    )
    logger.info(
        "Stabilization judge input: expected=[%s] action=[%s]",
        expected_actions,
        observer_action,
    )
    judgments = await asyncio.gather(
        *[
            provider.generate_structured(
                system_prompt=system_prompt,
                messages=[LLMMessage(role="user", content=user_message)],
                output_schema=StabilizationJudgment,
                sampling=SamplingParams(temperature=JUDGE_TEMPERATURE),
            )
            for _ in range(JUDGE_VOTE_COUNT)
        ]
    )
    match_votes = sum(1 for judgment in judgments if judgment.match)
    majority_match = match_votes * 2 > JUDGE_VOTE_COUNT
    representative = next(judgment for judgment in judgments if judgment.match == majority_match)
    logger.info(
        "Stabilization judge result (%d/%d match votes): match=%s — %s",
        match_votes,
        JUDGE_VOTE_COUNT,
        majority_match,
        representative.explanation,
    )
    return StabilizationJudgment(
        match=majority_match,
        explanation=representative.explanation,
    )
