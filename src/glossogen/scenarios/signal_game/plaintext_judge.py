"""The LLM judge that reads what players wrote on the shared server for plaintext.

At the end of a ``file_system`` round it is shown every file content written and
every file or directory name created during the round, numbered, and names the ones
holding plaintext: a meaning a reader gets without a key, in any language or in symbols
that depict it, including through a public encoding such as ROT13 or base64. Each text
is shown with its public decodings. A round with any flagged text is lost as cheated.
"""

import logging
from enum import Enum
from typing import NamedTuple

from pydantic import BaseModel

from glossogen.llm.provider import LLMMessage, LLMProvider
from glossogen.scenarios.signal_game.ids import JUDGE_SYSTEM_TEMPLATE, JUDGE_TEXTS_TEMPLATE
from glossogen.scenarios.signal_game.public_decodings import PublicDecoding, public_decodings
from glossogen.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class WrittenTextKind(str, Enum):
    """Whether a judged text is what a file holds or what a node is called."""

    CONTENT = "content"
    NAME = "name"


class WrittenText(NamedTuple):
    """One text a player put on the server during a round."""

    kind: WrittenTextKind
    path: str
    author: str
    text: str


class ShownText(NamedTuple):
    """A text as the judge is shown it: what was written and its public decodings."""

    written: WrittenText
    decodings: list[PublicDecoding]


class TextVerdict(BaseModel):
    """The judge's decision on one text; ``number`` is its 1-based position.

    ``reason`` comes before ``plaintext`` so the model states it before deciding.
    """

    number: int
    reason: str
    plaintext: bool


class PlaintextVerdict(BaseModel):
    """The judge's structured answer: one decision for every numbered text."""

    verdicts: list[TextVerdict]


class PlaintextFinding(NamedTuple):
    """A judged text the judge flagged, with its reason."""

    written: WrittenText
    reason: str


async def find_plaintext(
    provider: LLMProvider, renderer: TemplateRenderer, texts: list[WrittenText]
) -> list[PlaintextFinding]:
    """The texts among ``texts`` that hold plaintext. One judge call; none for no texts.

    The judge decides every text, and only a ``plaintext`` decision flags one.
    The call sets no temperature: Claude 5.x models refuse one. A decision on a number
    that names no text, or on a number already decided, is logged and dropped; a text
    the judge leaves undecided is logged and not flagged.
    """
    if not texts:
        return []
    verdict = await provider.generate_structured(
        system_prompt=renderer.render(template_name=JUDGE_SYSTEM_TEMPLATE, template_variables={}),
        messages=[
            LLMMessage(
                role="user",
                content=renderer.render(
                    template_name=JUDGE_TEXTS_TEMPLATE,
                    template_variables={
                        "texts": [
                            ShownText(
                                written=written, decodings=public_decodings(text=written.text)
                            )
                            for written in texts
                        ]
                    },
                ),
            )
        ],
        output_schema=PlaintextVerdict,
        sampling=None,
    )
    findings: list[PlaintextFinding] = []
    decided: set[int] = set()
    for text_verdict in verdict.verdicts:
        number = text_verdict.number
        if not 1 <= number <= len(texts) or number in decided:
            logger.warning(
                "Plaintext judge decided number %d of %d texts twice or out of range; " "dropped",
                number,
                len(texts),
            )
            continue
        decided.add(number)
        if text_verdict.plaintext:
            findings.append(PlaintextFinding(written=texts[number - 1], reason=text_verdict.reason))
    if len(decided) < len(texts):
        logger.warning(
            "Plaintext judge left %d of %d texts undecided",
            len(texts) - len(decided),
            len(texts),
        )
    logger.info("Plaintext judge flagged %d of %d texts", len(findings), len(texts))
    return findings
