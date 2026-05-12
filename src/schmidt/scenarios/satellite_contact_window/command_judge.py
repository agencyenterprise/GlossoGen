"""LLM-based judge that evaluates whether an operator's submitted command sequence
satisfies every required criterion for the current satellite contact-window case.

Uses ``generate_structured`` to get a validated per-criterion verdict with a
free-form explanation from the configured judge model.
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.scenarios.satellite_contact_window.cases import AuthorizationEnvelope, CommandStep
from schmidt.scenarios.satellite_contact_window.events import SatelliteCommandJudgment
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])


class CommandJudgmentResult(BaseModel):
    """Structured output from the satellite command-sequence judge LLM call."""

    judgment: SatelliteCommandJudgment
    violations: list[str]
    explanation: str


def _format_sequence(sequence: tuple[CommandStep, ...]) -> str:
    """Render an ordered command sequence as a numbered list for the judge prompt."""
    lines: list[str] = []
    for idx, step in enumerate(sequence, start=1):
        lines.append(f"{idx}. action={step.action} wait_seconds={step.wait_seconds}")
    return "\n".join(lines)


def _format_envelope(envelope: AuthorizationEnvelope) -> str:
    """Render the authorization envelope as a structured text block."""
    authorized = "\n".join(f"- {a}" for a in envelope.authorized_actions)
    forbidden = "\n".join(f"- {a}" for a in envelope.forbidden_actions)
    if len(envelope.dependencies) == 0:
        dependencies = "(none)"
    else:
        dependencies = "\n".join(
            f"- {d.action} requires prior action {d.requires_prior_action}"
            for d in envelope.dependencies
        )
    return (
        f"Authorized actions:\n{authorized}\n\n"
        f"Forbidden actions:\n{forbidden}\n\n"
        f"Dependencies:\n{dependencies}\n\n"
        f"Remaining window seconds: {envelope.remaining_window_seconds}\n"
        f"Director notes: {envelope.notes}"
    )


async def judge_command_sequence(
    provider: LLMProvider,
    expected_sequence: tuple[CommandStep, ...],
    authorization_envelope: AuthorizationEnvelope,
    submitted_sequence: tuple[CommandStep, ...],
) -> CommandJudgmentResult:
    """Ask the LLM judge whether the submitted sequence meets every required criterion.

    ``expected_sequence`` is the ground-truth ordered command sequence for
    the round (wait values already rendered). ``authorization_envelope``
    carries the round's authorized/forbidden actions and ordering
    dependencies. The judge returns a per-criterion
    ``SatelliteCommandJudgment``, a list of explicit violations, and a
    free-form explanation.
    """
    system_prompt = _renderer.render(
        template_name="command_judge.jinja",
        template_variables={},
    )
    expected_block = _format_sequence(sequence=expected_sequence)
    submitted_block = _format_sequence(sequence=submitted_sequence)
    envelope_block = _format_envelope(envelope=authorization_envelope)
    user_message = (
        f"Expected command sequence (ground truth, ordered):\n{expected_block}\n\n"
        f"Authorization envelope:\n{envelope_block}\n\n"
        f"Operator's submitted sequence:\n{submitted_block}"
    )
    logger.info(
        "Command-sequence judge input: expected=[%s] envelope=[%s] submitted=[%s]",
        expected_block,
        envelope_block,
        submitted_block,
    )
    result = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=CommandJudgmentResult,
    )
    logger.info(
        "Command-sequence judge result: judgment=%s violations=%s explanation=%s",
        result.judgment.model_dump(),
        result.violations,
        result.explanation,
    )
    return result
