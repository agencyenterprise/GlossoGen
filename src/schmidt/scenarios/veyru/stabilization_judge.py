"""LLM-based judge that evaluates whether a field observer's stabilization
action matches the expected procedure for a Veyru failure case.

Uses ``generate_structured`` to get a validated yes/no judgment with
an explanation from the configured judge model.
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dir=PROMPTS_DIR)


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
    judgment = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=StabilizationJudgment,
    )
    logger.info(
        "Stabilization judge result: match=%s — %s",
        judgment.match,
        judgment.explanation,
    )
    return judgment
