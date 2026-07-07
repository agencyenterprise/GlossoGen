"""Character-level English trigram language model with stupid-backoff smoothing.

Trains a character trigram on the ``wikitext-2-raw-v1`` train split (downloaded
once via ``datasets``) and scores arbitrary text by its mean per-character
surprisal in nats. Two deliberate departures from ``english_ngram_model``:

- The trained vocabulary keeps letters, **digits**, and common **punctuation**
  rather than collapsing to ``[a-z]``. Digit runs and punctuation are scored
  against their real English character transitions instead of every non-letter
  landing on an out-of-vocabulary sentinel at near-maximal surprisal.
- Unseen trigrams **back off** to bigrams and then unigrams (stupid backoff,
  Brants et al. 2007) instead of add-1 smoothing, so a never-seen combination
  gets the product of its lower-order character probabilities rather than a flat
  maximal-surprisal floor.

Case handling is explicit: when ``case_sensitive`` is false the text is
lowercased at train and score time (matching ``english_ngram_model``); when true
uppercase and lowercase characters are modeled separately, which preserves
protocols that use case to carry meaning (e.g. ``S`` = large, ``s`` = small).

Built counts are cached under ``~/.cache/glossogen/`` keyed by configuration; every
later load reads the cache with no network. Higher surprisal means a string is
less English-like.
"""

import logging
import math
from pathlib import Path
from typing import Any, cast

from datasets import load_dataset  # type: ignore[import-untyped]
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".cache" / "glossogen"
_DATASET_NAME = "wikitext"
_DATASET_CONFIG = "wikitext-2-raw-v1"
_DATASET_SPLIT = "train"

_START_CONTEXT = "^^"
_END_MARKER = "$"
_OOV_CHAR = "\x00"
_BACKOFF_ALPHA = 0.4

# The padding markers also land in ``vocab`` (added by ``vocab.update(padded)`` at train
# time), so an agent-authored ``^``/``$`` would otherwise test as in-vocabulary and collide
# with the start/end padding. Score-time mapping treats these as out-of-vocabulary instead.
_RESERVED_MARKERS = frozenset((_START_CONTEXT[0], _END_MARKER))

# Punctuation kept in the trained vocabulary. Excludes the reserved ``^`` start
# and ``$`` end markers so agent-authored carets/dollar signs fall through to the
# out-of-vocabulary sentinel rather than colliding with padding.
_PUNCTUATION = set(".,;:!?'\"()[]{}-/+=*&%#@_<>~")


class BackoffTrigramModel(BaseModel):
    """Character trigram with stupid-backoff smoothing over English text.

    ``trigram``/``bigram``/``unigram`` hold n-gram occurrence counts over the
    padded training words; ``total`` is the summed unigram count (the unigram
    denominator). ``vocab`` is the sorted set of characters seen in training.
    ``case_sensitive`` and ``keep_punctuation`` record the preprocessing used so
    scoring applies the identical normalization.
    """

    vocab: list[str]
    trigram: dict[str, int]
    bigram: dict[str, int]
    unigram: dict[str, int]
    total: int
    case_sensitive: bool
    keep_punctuation: bool

    def mean_char_surprisal(self, text: str) -> float:
        """Return the mean per-character surprisal (nats) of ``text``.

        The text is normalized with the model's own case/punctuation policy and
        split on whitespace; each word is padded with ``^^`` and ``$`` and scored
        character by character under stupid backoff. Characters outside the
        trained vocabulary map to an out-of-vocabulary sentinel and take the
        unigram backoff floor. Returns ``nan`` for text with no scorable
        characters.
        """
        vocab_set = set(self.vocab)
        total_surprisal = 0.0
        scored_chars = 0
        for word in _normalize(text=text, case_sensitive=self.case_sensitive).split():
            mapped = _map_to_vocab(
                word=word,
                vocab_set=vocab_set,
                keep_punctuation=self.keep_punctuation,
            )
            padded = _START_CONTEXT + mapped + _END_MARKER
            for i in range(len(_START_CONTEXT), len(padded)):
                context = padded[i - 2 : i]
                char = padded[i]
                total_surprisal += -math.log(self._backoff_probability(context=context, char=char))
                scored_chars += 1
        if scored_chars == 0:
            return math.nan
        return total_surprisal / scored_chars

    def _backoff_probability(self, context: str, char: str) -> float:
        """Return the stupid-backoff score for ``char`` given the 2-char ``context``.

        Falls from trigram to bigram to unigram, multiplying by ``_BACKOFF_ALPHA``
        at each drop. A character absent from every count table takes the
        thrice-discounted uniform-mass floor.
        """
        trigram_count = self.trigram.get(context + char, 0)
        if trigram_count > 0:
            return trigram_count / self.bigram[context]
        bigram_count = self.bigram.get(context[1] + char, 0)
        if bigram_count > 0:
            return _BACKOFF_ALPHA * bigram_count / self.unigram[context[1]]
        unigram_count = self.unigram.get(char, 0)
        if unigram_count > 0:
            return _BACKOFF_ALPHA * _BACKOFF_ALPHA * unigram_count / self.total
        return _BACKOFF_ALPHA * _BACKOFF_ALPHA * _BACKOFF_ALPHA / self.total


def _normalize(text: str, case_sensitive: bool) -> str:
    """Lowercase the text unless the model is case-sensitive."""
    if case_sensitive:
        return text
    return text.lower()


def _map_to_vocab(word: str, vocab_set: set[str], keep_punctuation: bool) -> str:
    """Keep trained characters, drop unwanted ones, map unknown to the sentinel.

    Characters in the trained vocabulary pass through, except the reserved ``^``/``$``
    padding markers, which map to the out-of-vocabulary sentinel so an agent-authored
    caret or dollar sign cannot collide with the padding. Characters that would be kept
    during training but are simply unseen also map to the sentinel. When
    ``keep_punctuation`` is false, punctuation is dropped entirely so it is neither
    modeled nor scored.
    """
    kept: list[str] = []
    for char in word:
        if char in _RESERVED_MARKERS:
            kept.append(_OOV_CHAR)
        elif not keep_punctuation and char in _PUNCTUATION:
            continue
        elif char in vocab_set:
            kept.append(char)
        else:
            kept.append(_OOV_CHAR)
    return "".join(kept)


def load_backoff_ngram_model(case_sensitive: bool, keep_punctuation: bool) -> BackoffTrigramModel:
    """Load the cached backoff trigram model, building and caching on first use.

    The cache filename encodes the case/punctuation configuration so distinct
    configurations coexist. CPU- and I/O-bound on a cache miss — callers should
    invoke this off the event loop via ``asyncio.to_thread``.
    """
    cache_path = _cache_path(case_sensitive=case_sensitive, keep_punctuation=keep_punctuation)
    if cache_path.exists():
        logger.info("backoff_ngram: loading cached model from %s", cache_path)
        return BackoffTrigramModel.model_validate_json(cache_path.read_text())
    logger.info(
        "backoff_ngram: no cache at %s; building from %s/%s",
        cache_path,
        _DATASET_NAME,
        _DATASET_CONFIG,
    )
    model = _build_model(case_sensitive=case_sensitive, keep_punctuation=keep_punctuation)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(model.model_dump_json())
    logger.info(
        "backoff_ngram: cached model (vocab=%d, trigrams=%d) to %s",
        len(model.vocab),
        len(model.trigram),
        cache_path,
    )
    return model


def _cache_path(case_sensitive: bool, keep_punctuation: bool) -> Path:
    """Return the configuration-keyed cache path for a backoff trigram model."""
    if case_sensitive:
        case_tag = "cased"
    else:
        case_tag = "lower"
    if keep_punctuation:
        punct_tag = "punct"
    else:
        punct_tag = "nopunct"
    return _CACHE_DIR / f"english_backoff_trigram_{case_tag}_{punct_tag}.json"


def _build_model(case_sensitive: bool, keep_punctuation: bool) -> BackoffTrigramModel:
    """Train the backoff trigram on the wikitext-2 train split."""
    loader = cast(Any, load_dataset)
    dataset = loader(_DATASET_NAME, _DATASET_CONFIG, split=_DATASET_SPLIT)
    lines = cast(list[str], dataset["text"])
    trigram: dict[str, int] = {}
    bigram: dict[str, int] = {}
    unigram: dict[str, int] = {}
    vocab: set[str] = set()
    for line in lines:
        _accumulate_line(
            line=line,
            case_sensitive=case_sensitive,
            keep_punctuation=keep_punctuation,
            trigram=trigram,
            bigram=bigram,
            unigram=unigram,
            vocab=vocab,
        )
    return BackoffTrigramModel(
        vocab=sorted(vocab),
        trigram=trigram,
        bigram=bigram,
        unigram=unigram,
        total=sum(unigram.values()),
        case_sensitive=case_sensitive,
        keep_punctuation=keep_punctuation,
    )


def _accumulate_line(
    line: str,
    case_sensitive: bool,
    keep_punctuation: bool,
    trigram: dict[str, int],
    bigram: dict[str, int],
    unigram: dict[str, int],
    vocab: set[str],
) -> None:
    """Count the 1-, 2-, and 3-grams of every kept-character word in one line."""
    for word in _normalize(text=line, case_sensitive=case_sensitive).split():
        kept = "".join(
            char for char in word if _is_kept(char=char, keep_punctuation=keep_punctuation)
        )
        if not kept:
            continue
        padded = _START_CONTEXT + kept + _END_MARKER
        vocab.update(padded)
        for i in range(len(padded)):
            unigram[padded[i]] = unigram.get(padded[i], 0) + 1
            if i >= 1:
                pair = padded[i - 1 : i + 1]
                bigram[pair] = bigram.get(pair, 0) + 1
            if i >= 2:
                triple = padded[i - 2 : i + 1]
                trigram[triple] = trigram.get(triple, 0) + 1


def _is_kept(char: str, keep_punctuation: bool) -> bool:
    """Return whether a character is retained during training.

    Letters and digits are always kept. Punctuation is kept only when
    ``keep_punctuation`` is set. The reserved ``^``/``$`` markers are never kept
    as ordinary characters.
    """
    if char in (_START_CONTEXT[0], _END_MARKER):
        return False
    if char.isalnum():
        return True
    return keep_punctuation and char in _PUNCTUATION
