"""LLM-based judge that scores a team's submitted differences.

Given the round's K planted ground-truth differences and the team's free-text
list of differences, the judge decides which ground-truth differences each
submission identifies and how many submitted items match nothing (false
positives). A submission matches a planted difference when it correctly names
the object involved and the nature of the change; it need not state both
scenes' values, since each viewer sees only one scene.
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from schmidt.llm.provider import LLMMessage, LLMProvider, SamplingParams
from schmidt.scenarios.spot_the_difference.scene_generation import PlantedDifference
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_renderer = TemplateRenderer(prompts_dirs=[PROMPTS_DIR])

JUDGE_TEMPERATURE = 0.0


class SubmissionJudgment(BaseModel):
    """Structured output from the difference judge LLM call.

    ``matched_difference_indices`` are 1-based indices into the enumerated
    ground-truth list that the submission correctly identified (deduplicate
    before use). ``false_positive_count`` is the number of submitted items
    matching no ground-truth difference.
    """

    matched_difference_indices: list[int]
    false_positive_count: int
    explanation: str


def _render_ground_truth(ground_truth: list[PlantedDifference]) -> str:
    """Enumerate the planted differences as a 1-based list for the judge."""
    lines = [f"{index}. {diff.description}" for index, diff in enumerate(ground_truth, start=1)]
    return "\n".join(lines)


def _render_submission(submitted_items: list[str]) -> str:
    """Enumerate the team's submitted difference descriptions."""
    lines = [f"{index}. {item}" for index, item in enumerate(submitted_items, start=1)]
    return "\n".join(lines)


async def judge_submission(
    provider: LLMProvider,
    ground_truth: list[PlantedDifference],
    submitted_items: list[str],
) -> SubmissionJudgment:
    """Ask the LLM judge which planted differences the submission identified."""
    system_prompt = _renderer.render(template_name="difference_judge.jinja", template_variables={})
    user_message = (
        f"GROUND-TRUTH DIFFERENCES (there are exactly {len(ground_truth)}):\n"
        f"{_render_ground_truth(ground_truth=ground_truth)}\n\n"
        f"TEAM'S SUBMITTED DIFFERENCES:\n"
        f"{_render_submission(submitted_items=submitted_items)}"
    )
    logger.info(
        "Difference judge input: %d ground-truth, %d submitted",
        len(ground_truth),
        len(submitted_items),
    )
    judgment = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=SubmissionJudgment,
        sampling=SamplingParams(temperature=JUDGE_TEMPERATURE),
    )
    logger.info(
        "Difference judge result: matched=%s false_positives=%d — %s",
        judgment.matched_difference_indices,
        judgment.false_positive_count,
        judgment.explanation,
    )
    return judgment
