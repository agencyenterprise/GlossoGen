"""Generate plausible wrong answers for trivia questions using Claude.

Reads questions.json, calls Claude to produce a plausible-but-incorrect answer
for each question with an empty wrong_answer field, and writes the updated
questions back to the same file. This is a one-time data preparation script,
not a runtime dependency of the scenario.
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from pydantic import BaseModel

from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.llm.provider import LLMMessage
from schmidt.scenarios.persuasion_debate.question_bank import QuestionBank

logger = logging.getLogger(__name__)

QUESTIONS_PATH = Path(__file__).parent / "questions.json"

SYSTEM_PROMPT = (
    "You are a trivia question analyst. Given a trivia question and its correct answer, "
    "generate a single wrong answer that is plausible enough to fool someone who is unsure. "
    "The wrong answer should be in the same category and of similar specificity as the "
    "correct answer, but clearly incorrect to someone who knows the topic well."
)


class WrongAnswerOutput(BaseModel):
    """A plausible but incorrect answer to a trivia question."""

    wrong_answer: str


async def generate_wrong_answer(
    provider: ClaudeProvider,
    question_text: str,
    reference_answer: str,
) -> str:
    """Generate a single plausible wrong answer for a trivia question."""
    user_message = (
        f"Question: {question_text}\n"
        f"Correct answer: {reference_answer}\n\n"
        "Generate a plausible but incorrect answer."
    )
    result = await provider.generate_structured(
        system_prompt=SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user_message)],
        output_schema=WrongAnswerOutput,
    )
    return result.wrong_answer


async def run(model: str, questions_path: Path) -> None:
    """Generate wrong answers for all questions missing them."""
    provider = ClaudeProvider(model=model)
    question_bank = QuestionBank.load_from_file(path=questions_path)

    updated_count = 0
    for question in question_bank.questions:
        if question.wrong_answer:
            logger.info("Skipping %s (already has wrong answer)", question.question_id)
            continue

        logger.info(
            "Generating wrong answer for %s: %s", question.question_id, question.question_text
        )
        wrong = await generate_wrong_answer(
            provider=provider,
            question_text=question.question_text,
            reference_answer=question.reference_answer,
        )
        question.wrong_answer = wrong
        updated_count += 1
        logger.info("  correct=%s  wrong=%s", question.reference_answer, wrong)

    raw = json.loads(questions_path.read_text())
    for i, question in enumerate(question_bank.questions):
        raw["questions"][i]["wrong_answer"] = question.wrong_answer

    questions_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n")
    logger.info("Updated %d questions in %s", updated_count, questions_path)


def main() -> None:
    """CLI entry point for wrong answer generation."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Generate plausible wrong answers for trivia questions"
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Claude model to use for generation",
    )
    parser.add_argument(
        "--questions",
        type=str,
        required=True,
        help="Path to questions.json",
    )
    args = parser.parse_args()
    asyncio.run(run(model=args.model, questions_path=Path(args.questions)))


if __name__ == "__main__":
    main()
