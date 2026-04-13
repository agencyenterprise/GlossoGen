"""LLM-based judge that evaluates whether a field responder's treatment action
matches the critical actions required for a patient case.

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


class TreatmentJudgment(BaseModel):
    """Structured output from the treatment judge LLM call."""

    match: bool
    explanation: str


async def judge_treatment(
    provider: LLMProvider,
    condition_name: str,
    critical_actions: str,
    responder_action: str,
) -> TreatmentJudgment:
    """Ask the LLM judge whether the field responder's action adequately addresses the emergency.

    Returns a ``TreatmentJudgment`` with a boolean ``match`` and an ``explanation``.
    """
    system_prompt = _renderer.render(
        template_name="treatment_judge.jinja",
        template_variables={},
    )
    user_message = (
        f"Patient condition: {condition_name}\n\n"
        f"Required critical actions:\n{critical_actions}\n\n"
        f"Field responder's reported action:\n{responder_action}"
    )
    judgment = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=TreatmentJudgment,
    )
    logger.info(
        "Treatment judge for %s: match=%s — %s",
        condition_name,
        judgment.match,
        judgment.explanation,
    )
    return judgment
