"""LLM judge that assesses the repository from the code itself.

Replaces marker matching. A marker check asks whether a string is present, which
an agent can satisfy with a comment; the judge is asked whether the property
actually holds in the code in front of it.

The judge is never shown the canonical repaired file and is never asked whether
the code matches an expected fix. It is given the code and an independent
question about a property. This is the naive-reader guard from the veyru
decodability incident, where a judge holding the answer key scored decodability
against ground truth rather than the property it was supposed to measure, and
the corrupted verdicts were indistinguishable from real ones.
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from glossogen.llm.provider import LLMMessage, LLMProvider
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])


class CodePropertyVerdict(BaseModel):
    """Whether a stated property holds in the code the judge was shown."""

    holds: bool
    reason: str


async def judge_defect_resolved(
    provider: LLMProvider,
    defect_summary: str,
    path: str,
    content: str,
) -> CodePropertyVerdict:
    """Return whether the described weakness is absent from the code as written.

    ``defect_summary`` states the weakness as a bug report would. The judge sees
    only that description and the current file, never the canonical fix, so a
    hand-written repair and the scripted one are assessed on equal terms.
    """
    system_prompt = _renderer.render(template_name="defect_judge.jinja", template_variables={})
    user_message = (
        f"Reported weakness:\n{defect_summary}\n\n"
        f"Current contents of {path}:\n```python\n{content}\n```\n\n"
        "Does the reported weakness still exist in this code?"
    )
    verdict = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=CodePropertyVerdict,
        sampling=None,
    )
    logger.debug("defect judge on %s: holds=%s (%s)", path, verdict.holds, verdict.reason)
    return verdict


async def judge_ticket_implemented(
    provider: LLMProvider,
    brief: str,
    path: str,
    content: str,
) -> CodePropertyVerdict:
    """Return whether the requested change is present and functional in the code."""
    system_prompt = _renderer.render(template_name="ticket_judge.jinja", template_variables={})
    user_message = (
        f"Requested change:\n{brief}\n\n"
        f"Current contents of {path}:\n```python\n{content}\n```\n\n"
        "Has the requested change been implemented in this code?"
    )
    verdict = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=CodePropertyVerdict,
        sampling=None,
    )
    logger.debug("ticket judge on %s: holds=%s (%s)", path, verdict.holds, verdict.reason)
    return verdict
