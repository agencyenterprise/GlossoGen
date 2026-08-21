"""Measure documentation pages against the bands in docs/documentation-style.md.

Prints one row per page: prose word count, prose words per heading, average
sentence length, long paragraphs, and mid-sentence em-dashes. A row that crosses
a band is marked with the bands it crossed. This is a measurement for the review
described in that document, not a linter: it always exits zero, because a band is
a review trigger rather than a law.
"""

import argparse
import re
from pathlib import Path
from typing import NamedTuple

MAX_PROSE_WORDS_PER_HEADING = 150
MAX_AVERAGE_SENTENCE_WORDS = 20.0
EARNED_PARAGRAPH_WORDS = 60
MAX_PARAGRAPH_WORDS = 100


class PageMeasurements(NamedTuple):
    """The mechanical measurements for one documentation page."""

    prose_words: int
    headings: int
    average_sentence_words: float
    paragraphs_over_60_words: int
    paragraphs_over_100_words: int
    mid_sentence_em_dashes: int


def measure_page(text: str) -> PageMeasurements:
    """Measure one page's markdown source."""
    in_code_block = False
    prose_lines: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            prose_lines.append(line)

    headings = sum(1 for line in prose_lines if re.match(r"^#{1,6} ", line))
    prose_text = " ".join(line for line in prose_lines if not re.match(r"^#{1,6} |^\s*\|", line))
    prose_words = len(prose_text.split())

    sentences = [
        sentence for sentence in re.split(r"(?<=[.!?])\s+", prose_text) if len(sentence.split()) > 2
    ]
    total_sentence_words = sum(len(sentence.split()) for sentence in sentences)
    average_sentence_words = total_sentence_words / max(len(sentences), 1)

    without_code = re.sub(r"```.*?```", "", text, flags=re.S)
    over_60 = 0
    over_100 = 0
    for block in re.split(r"\n\s*\n", without_code):
        collapsed = " ".join(block.split())
        if collapsed.startswith(("#", "|", "-", "*", ">")):
            continue
        if re.match(r"^\d+\. ", collapsed):
            continue
        block_words = len(collapsed.split())
        if block_words > EARNED_PARAGRAPH_WORDS:
            over_60 += 1
        if block_words > MAX_PARAGRAPH_WORDS:
            over_100 += 1

    mid_sentence_em_dashes = sum(
        line.count(" — ") for line in prose_lines if not line.strip().startswith(("-", "*", "|"))
    )

    return PageMeasurements(
        prose_words=prose_words,
        headings=headings,
        average_sentence_words=average_sentence_words,
        paragraphs_over_60_words=over_60,
        paragraphs_over_100_words=over_100,
        mid_sentence_em_dashes=mid_sentence_em_dashes,
    )


def crossed_bands(measurements: PageMeasurements) -> list[str]:
    """Name the bands a page crossed, in the order the table lists them."""
    crossed: list[str] = []
    words_per_heading = measurements.prose_words // max(measurements.headings, 1)
    if words_per_heading > MAX_PROSE_WORDS_PER_HEADING:
        crossed.append("words/heading")
    if measurements.average_sentence_words > MAX_AVERAGE_SENTENCE_WORDS:
        crossed.append("sentence length")
    if measurements.paragraphs_over_100_words > 0:
        crossed.append("paragraph length")
    if measurements.mid_sentence_em_dashes > 0:
        crossed.append("em-dashes")
    return crossed


def main() -> None:
    """Measure every page named on the command line and print one row each."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown pages to measure")
    arguments = parser.parse_args()

    header = (
        f"{'page':44} {'prose':>5} {'w/head':>6} {'sent':>5} "
        f"{'p>60':>4} {'p>100':>5} {'dash':>4}"
    )
    print(header)
    for path in arguments.paths:
        measurements = measure_page(text=path.read_text())
        words_per_heading = measurements.prose_words // max(measurements.headings, 1)
        crossed = crossed_bands(measurements=measurements)
        if crossed:
            verdict = "over: " + ", ".join(crossed)
        else:
            verdict = "ok"
        print(
            f"{str(path):44} {measurements.prose_words:5} {words_per_heading:6} "
            f"{measurements.average_sentence_words:5.1f} "
            f"{measurements.paragraphs_over_60_words:4} "
            f"{measurements.paragraphs_over_100_words:5} "
            f"{measurements.mid_sentence_em_dashes:4}  {verdict}"
        )


if __name__ == "__main__":
    main()
