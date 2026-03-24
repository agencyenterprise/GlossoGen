"""Question bank for the persuasion debate scenario.

Loads trivia questions from a JSON file. Each question has a reference answer
and an optional wrong answer used by the adversary in misinformation/balanced modes.
"""

from pathlib import Path

from pydantic import BaseModel


class Question(BaseModel):
    """A single trivia question with reference and optional wrong answer."""

    question_id: str
    question_text: str
    reference_answer: str
    wrong_answer: str
    category: str


class QuestionBank(BaseModel):
    """Collection of trivia questions loaded from a JSON file."""

    questions: list[Question]

    @staticmethod
    def load_from_file(path: Path) -> "QuestionBank":
        """Load a question bank from a JSON file."""
        return QuestionBank.model_validate_json(path.read_text())
