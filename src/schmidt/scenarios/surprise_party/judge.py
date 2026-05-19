"""LLM judge for the ``submit_guess`` tool in the surprise_party scenario.

One judge call per guess. The judge sees the ground-truth party where /
when and the agent's freetext guess, and emits a structured verdict
(correct + short explanation). Lenient matching: synonyms, partial venue
names that uniquely identify the place, and casual time phrasing all pass.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
JUDGE_SYSTEM_TEMPLATE = "guess_judge_system.jinja"
JUDGE_USER_TEMPLATE = "guess_judge.jinja"


class GuessVerdict(BaseModel):
    """Structured judge output for one ``submit_guess`` call."""

    correct: bool = Field(
        description=(
            "True when the freetext guess clearly identifies BOTH the place "
            "and the time of the ground-truth party. False if the guess "
            "misses either half, is too vague to pin down a place / time, or "
            "names a different place or time."
        ),
    )
    explanation: str = Field(
        description=(
            "One short sentence justifying the verdict, suitable for showing back "
            "to the guessing agent so they can reason about how close they were."
        ),
    )


class GuessJudge:
    """LLM-backed match check for surprise-party guesses."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._provider = llm_provider
        self._renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])

    async def judge(
        self,
        ground_truth_where: str,
        ground_truth_when: str,
        guess: str,
    ) -> GuessVerdict:
        """Score one freetext guess against the ground-truth party."""
        system_prompt = self._renderer.render(
            template_name=JUDGE_SYSTEM_TEMPLATE,
            template_variables={},
        )
        user_prompt = self._renderer.render(
            template_name=JUDGE_USER_TEMPLATE,
            template_variables={
                "ground_truth_where": ground_truth_where,
                "ground_truth_when": ground_truth_when,
                "guess": guess,
            },
        )
        return await self._provider.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=user_prompt)],
            output_schema=GuessVerdict,
        )
