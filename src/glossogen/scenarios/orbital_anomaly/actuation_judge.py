"""LLM-based judge that evaluates whether an astronaut's panel action matches
the expected corrective procedure for an anomaly stage.

Uses ``generate_structured`` to get a validated yes/no judgment with an
explanation from the configured judge model, applying a "naive reader" test
that forces the action's parameters to be stated in plain English so the
compression pressure lands on the comm loop, not the tool call.
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from glossogen.llm.provider import LLMMessage, LLMProvider, SamplingParams
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])

JUDGE_TEMPERATURE = 0.0


class ActuationJudgment(BaseModel):
    """Structured output from the actuation judge LLM call."""

    match: bool
    explanation: str


async def judge_actuation(
    provider: LLMProvider,
    expected_procedure: str,
    astronaut_action: str,
) -> ActuationJudgment:
    """Ask the LLM judge whether the astronaut's action matches the expected procedure.

    ``expected_procedure`` is the fully filled corrective procedure with all
    parameters baked in — no conflicting values for the judge to resolve.
    """
    system_prompt = _renderer.render(template_name="actuation_judge.jinja", template_variables={})
    user_message = (
        f"Expected procedure:\n{expected_procedure}\n\n"
        f"Astronaut's reported action:\n{astronaut_action}"
    )
    logger.info(
        "Actuation judge input: expected=[%s] action=[%s]",
        expected_procedure,
        astronaut_action,
    )
    judgment = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=ActuationJudgment,
        sampling=SamplingParams(temperature=JUDGE_TEMPERATURE),
    )
    logger.info(
        "Actuation judge result: match=%s — %s",
        judgment.match,
        judgment.explanation,
    )
    return judgment
