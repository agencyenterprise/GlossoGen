"""LLM-based judge that evaluates whether a floor associate's recovery action
satisfies every required criterion for the current warehouse robot case.

Uses ``generate_structured`` to get a validated per-criterion verdict with
a free-form explanation from the configured judge model.
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.scenarios.warehouse_robot_recovery.events import WarehouseRecoveryJudgment
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])


class RecoveryJudgmentResult(BaseModel):
    """Structured output from the warehouse recovery judge LLM call."""

    judgment: WarehouseRecoveryJudgment
    explanation: str


async def judge_recovery(
    provider: LLMProvider,
    robot_id: str,
    expected_procedure: str,
    safety_constraints: str,
    observer_action: str,
) -> RecoveryJudgmentResult:
    """Ask the LLM judge whether the recovery action meets every required criterion.

    ``expected_procedure`` is the fully rendered ordered list of recovery
    steps for the round's faults (parameters already substituted).
    ``safety_constraints`` lists the round's forbidden actions and
    constraints from the safety coordinator. The judge returns a
    per-criterion ``WarehouseRecoveryJudgment`` plus a free-form
    explanation.
    """
    system_prompt = _renderer.render(
        template_name="recovery_judge.jinja",
        template_variables={},
    )
    user_message = (
        f"Target robot: {robot_id}\n\n"
        f"Expected recovery procedure (in required order):\n{expected_procedure}\n\n"
        f"Safety constraints:\n{safety_constraints}\n\n"
        f"Floor associate's reported action:\n{observer_action}"
    )
    logger.info(
        "Recovery judge input: robot=%s expected=[%s] safety=[%s] action=[%s]",
        robot_id,
        expected_procedure,
        safety_constraints,
        observer_action,
    )
    result = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=RecoveryJudgmentResult,
    )
    judgment = result.judgment
    logger.info(
        "Recovery judge result: robot=%s judgment=%s explanation=%s",
        robot_id,
        judgment.model_dump(),
        result.explanation,
    )
    return result
