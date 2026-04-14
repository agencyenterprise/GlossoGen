"""LLM-based judge that evaluates whether a field observer's stabilization
action matches the critical actions required for a Veyru failure case.

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
    failure_name: str,
    critical_actions: str,
    observer_action: str,
) -> StabilizationJudgment:
    """Ask the LLM judge whether the observer's action adequately stabilizes the Veyru.

    Returns a ``StabilizationJudgment`` with a boolean ``match`` and an ``explanation``.
    """
    system_prompt = _renderer.render(
        template_name="stabilization_judge.jinja",
        template_variables={},
    )
    user_message = (
        f"Veyru failure: {failure_name}\n\n"
        f"Required stabilization actions:\n{critical_actions}\n\n"
        f"Field observer's reported action:\n{observer_action}"
    )
    judgment = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=StabilizationJudgment,
    )
    logger.info(
        "Stabilization judge for %s: match=%s — %s",
        failure_name,
        judgment.match,
        judgment.explanation,
    )
    return judgment
