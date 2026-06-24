"""Character-level English trigram language model.

Trains an add-1-smoothed character trigram on the ``wikitext-2-raw-v1`` train
split (downloaded once via ``datasets``) and scores arbitrary text by its mean
per-character surprisal in nats. Words are lowercased, reduced to ``[a-z]``
during training, and padded with ``^^`` start context and a ``$`` end marker so
word boundaries are modeled.

The built counts are cached to ``~/.cache/schmidt/english_char_trigram.json``;
every later load reads the cache with no network. Higher surprisal means a
string is less English-like — degenerate repetition (``LLLLLLL``), emergent
codes (``Lf Lf``), and digit runs (``12``) all score high because the
underlying character transitions are rare or absent in English.
"""

import logging
import math
from pathlib import Path
from typing import Any, cast

from datasets import load_dataset  # type: ignore[import-untyped]
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_CACHE_PATH = Path.home() / ".cache" / "schmidt" / "english_char_trigram.json"
_DATASET_NAME = "wikitext"
_DATASET_CONFIG = "wikitext-2-raw-v1"
_DATASET_SPLIT = "train"

_START_CONTEXT = "^^"
_END_MARKER = "$"
_OOV_CHAR = "\x00"
_SMOOTHING_K = 1.0


class EnglishTrigramModel(BaseModel):
    """Add-1-smoothed character trigram over lowercased English letters.

    ``bigram`` maps each 2-character context to its occurrence count;
    ``trigram`` maps each 3-character (context + next char) sequence to its
    count. ``vocab`` is the sorted set of characters seen in training
    (``[a-z]`` plus the ``^`` and ``$`` markers).
    """

    vocab: list[str]
    bigram: dict[str, int]
    trigram: dict[str, int]

    def mean_char_surprisal(self, text: str) -> float:
        """Return the mean per-character surprisal (nats) of ``text``.

        The text is lowercased and split on whitespace; each word is padded
        with ``^^`` and ``$`` and scored character by character under add-1
        smoothing. Characters outside the trained vocabulary are mapped to an
        out-of-vocabulary sentinel so non-English symbols (digits, glyphs)
        land on unseen contexts and accrue high surprisal. Returns ``nan`` for
        text with no scorable characters.
        """
        vocab_size = len(self.vocab)
        vocab_set = set(self.vocab)
        total_surprisal = 0.0
        scored_chars = 0
        for word in text.lower().split():
            mapped = _map_to_vocab(word=word, vocab_set=vocab_set)
            padded = _START_CONTEXT + mapped + _END_MARKER
            for i in range(len(_START_CONTEXT), len(padded)):
                context = padded[i - 2 : i]
                char = padded[i]
                trigram_count = self.trigram.get(context + char, 0)
                context_count = self.bigram.get(context, 0)
                probability = (trigram_count + _SMOOTHING_K) / (
                    context_count + _SMOOTHING_K * vocab_size
                )
                total_surprisal += -math.log(probability)
                scored_chars += 1
        if scored_chars == 0:
            return math.nan
        return total_surprisal / scored_chars


def _map_to_vocab(word: str, vocab_set: set[str]) -> str:
    """Map each character to itself if trained, else to the OOV sentinel."""
    return "".join(_keep_or_oov(char=char, vocab_set=vocab_set) for char in word)


def _keep_or_oov(char: str, vocab_set: set[str]) -> str:
    """Return the character if it is in the trained vocabulary, else the sentinel."""
    if char in vocab_set:
        return char
    return _OOV_CHAR


def load_english_trigram_model() -> EnglishTrigramModel:
    """Load the cached trigram model, building and caching it on first use.

    Reads ``~/.cache/schmidt/english_char_trigram.json`` when present; otherwise
    downloads ``wikitext-2-raw-v1``, trains the trigram, writes the cache, and
    returns the model. CPU- and I/O-bound — callers should invoke this off the
    event loop via ``asyncio.to_thread``.
    """
    if _CACHE_PATH.exists():
        logger.info("english_ngram: loading cached model from %s", _CACHE_PATH)
        return EnglishTrigramModel.model_validate_json(_CACHE_PATH.read_text())
    logger.info(
        "english_ngram: no cache at %s; building from %s/%s",
        _CACHE_PATH,
        _DATASET_NAME,
        _DATASET_CONFIG,
    )
    model = _build_model_from_wikitext()
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(model.model_dump_json())
    logger.info(
        "english_ngram: cached model (vocab=%d, trigrams=%d) to %s",
        len(model.vocab),
        len(model.trigram),
        _CACHE_PATH,
    )
    return model


def _build_model_from_wikitext() -> EnglishTrigramModel:
    """Train the character trigram on the wikitext-2 train split."""
    loader = cast(Any, load_dataset)
    dataset = loader(_DATASET_NAME, _DATASET_CONFIG, split=_DATASET_SPLIT)
    lines = cast(list[str], dataset["text"])
    bigram: dict[str, int] = {}
    trigram: dict[str, int] = {}
    vocab: set[str] = set()
    for line in lines:
        _accumulate_line(line=line, bigram=bigram, trigram=trigram, vocab=vocab)
    return EnglishTrigramModel(vocab=sorted(vocab), bigram=bigram, trigram=trigram)


def _accumulate_line(
    line: str,
    bigram: dict[str, int],
    trigram: dict[str, int],
    vocab: set[str],
) -> None:
    """Count the trigrams and bigrams of every letter-word in one line."""
    for word in line.lower().split():
        letters = "".join(char for char in word if "a" <= char <= "z")
        if not letters:
            continue
        padded = _START_CONTEXT + letters + _END_MARKER
        vocab.update(padded)
        for i in range(len(_START_CONTEXT), len(padded)):
            context = padded[i - 2 : i]
            char = padded[i]
            bigram[context] = bigram.get(context, 0) + 1
            trigram[context + char] = trigram.get(context + char, 0) + 1
