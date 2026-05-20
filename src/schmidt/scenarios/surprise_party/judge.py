"""LLM judge for the ``submit_guess`` tool in the surprise_party scenario.

One judge call per guess. The judge sees the agent's freetext guess and emits
a structured verdict (correct + short explanation). A guess is correct only
when it clearly identifies that Alice is organizing a surprise party for
Chris (i.e. the guesser has spotted both the surprise-party nature of the
plan and Chris as the guest of honor).
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
            "True when the freetext guess clearly indicates the guesser has "
            "figured out that a surprise party is being organized for Chris. "
            "False if the guess only describes a normal meetup, names a "
            "different secret, names a different person as the honoree, or "
            "is too vague to identify Chris as the guest of honor."
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

    async def judge(self, guess: str) -> GuessVerdict:
        """Score one freetext guess against the surprise-party-for-Chris secret."""
        system_prompt = self._renderer.render(
            template_name=JUDGE_SYSTEM_TEMPLATE,
            template_variables={},
        )
        user_prompt = self._renderer.render(
            template_name=JUDGE_USER_TEMPLATE,
            template_variables={"guess": guess},
        )
        return await self._provider.generate_structured(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=user_prompt)],
            output_schema=GuessVerdict,
        )
