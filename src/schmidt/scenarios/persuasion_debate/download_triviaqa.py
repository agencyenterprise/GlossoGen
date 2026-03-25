"""Download a subset of TriviaQA questions and save as a JSON question bank.

Requires the ``datasets`` library (``pip install datasets``).
Uses streaming mode to avoid downloading the full dataset.
This is a standalone script, not imported by the scenario at runtime.
"""

import argparse
import json
from pathlib import Path

from datasets import load_dataset  # type: ignore[import-untyped]

DEFAULT_OUTPUT = str(Path(__file__).parent / "questions.json")


def main() -> None:
    """Stream TriviaQA questions and write a JSON question bank."""
    parser = argparse.ArgumentParser(
        description="Download TriviaQA subset for persuasion debate",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of questions to sample (default: 100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help="Output JSON file path",
    )
    args = parser.parse_args()

    print("Streaming TriviaQA validation split (unfiltered config)...")
    dataset = load_dataset(
        "trivia_qa",
        "unfiltered",
        split="validation",
        streaming=True,
    )

    collected = []
    for row in dataset:
        collected.append(row)
        if len(collected) >= args.count * 2:
            break

    print(f"Collected {len(collected)} rows, selecting {args.count} questions...")

    questions = []
    for i in range(min(args.count, len(collected))):
        row = collected[i]
        question_text = row["question"]
        answer_data = row["answer"]
        reference_answer = answer_data["value"]

        questions.append(
            {
                "question_id": f"q{i + 1}",
                "question_text": question_text,
                "reference_answer": reference_answer,
                "wrong_answer": "",
                "category": "trivia",
            }
        )

    bank = {"questions": questions}
    with open(args.output, "w") as f:
        json.dump(bank, f, indent=2)

    print(f"Wrote {len(questions)} questions to {args.output}")


if __name__ == "__main__":
    main()
