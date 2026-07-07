"""Per-message English character-trigram surprisal scoring with a per-run on-disk cache.

Mirrors the ``english_ngram_surprisal`` metric (``EnglishTrigramModel.mean_char_surprisal``)
and caches each run's per-message result beside its JSONL, keyed by the JSONL's size +
mtime + message count + a cache version. An export where every run is already cached
never loads the trigram model. Higher surprisal means a message is less English-like.
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

import orjson

from glossogen.evaluation.metrics.english_ngram.english_ngram_model import (
    EnglishTrigramModel,
    load_english_trigram_model,
)

logger = logging.getLogger(__name__)

# Per-run cache of message surprisals, written beside each run's JSONL. Recomputed
# whenever the JSONL changes or _ENGLISH_NGRAM_CACHE_VERSION is bumped (walk-order change).
_MESSAGE_ENGLISH_NGRAM_CACHE_NAME = "message_english_ngram_cache.json"
_ENGLISH_NGRAM_CACHE_VERSION = 1


def _score_texts(model: EnglishTrigramModel, texts: list[str]) -> list[float | None]:
    """Per-message mean per-char surprisal (nats) under the English trigram, aligned with ``texts``.

    Empty or whitespace-only messages (which yield NaN — no scorable characters)
    map to ``None`` so the column stays numeric elsewhere.
    """
    results: list[float | None] = [None] * len(texts)
    for index, text in enumerate(texts):
        if not text or not text.strip():
            continue
        value = model.mean_char_surprisal(text=text)
        if not math.isnan(value):
            results[index] = value
    return results


class _EnglishNgramCacheKey(NamedTuple):
    """Identity of a run's cached per-message surprisals.

    A cache hit requires all fields to match, so any edit to the run's JSONL (size
    or mtime), a change in message count, or a bump to ``_ENGLISH_NGRAM_CACHE_VERSION``
    (used when the message-walk order changes) forces a recompute.
    """

    jsonl_size: int
    jsonl_mtime_ns: int
    message_count: int
    cache_version: int


def _english_ngram_cache_key(jsonl_path: Path, message_count: int) -> _EnglishNgramCacheKey:
    """Build the cache key for ``jsonl_path``'s ``message_count`` link messages."""
    stat = jsonl_path.stat()
    return _EnglishNgramCacheKey(
        jsonl_size=stat.st_size,
        jsonl_mtime_ns=stat.st_mtime_ns,
        message_count=message_count,
        cache_version=_ENGLISH_NGRAM_CACHE_VERSION,
    )


def _read_cache(cache_path: Path, cache_key: _EnglishNgramCacheKey) -> list[float | None] | None:
    """Return the cached per-message surprisals if the cache matches ``cache_key``."""
    if not cache_path.exists():
        return None
    try:
        payload = orjson.loads(cache_path.read_bytes())
    except (orjson.JSONDecodeError, OSError):
        logger.exception("english_ngram cache unreadable, recomputing: %s", cache_path)
        return None
    matches = (
        payload.get("jsonl_size") == cache_key.jsonl_size
        and payload.get("jsonl_mtime_ns") == cache_key.jsonl_mtime_ns
        and payload.get("message_count") == cache_key.message_count
        and payload.get("cache_version") == cache_key.cache_version
    )
    if not matches:
        return None
    return list(payload["surprisals"])


def _write_cache(
    cache_path: Path, cache_key: _EnglishNgramCacheKey, surprisals: list[float | None]
) -> None:
    """Persist ``surprisals`` for a run, keyed by ``cache_key``, beside its JSONL."""
    payload = {
        "jsonl_size": cache_key.jsonl_size,
        "jsonl_mtime_ns": cache_key.jsonl_mtime_ns,
        "message_count": cache_key.message_count,
        "cache_version": cache_key.cache_version,
        "surprisals": surprisals,
    }
    cache_path.write_bytes(orjson.dumps(payload))


class MessageEnglishNgramScorer:
    """Scores link-message English-trigram surprisal, caching each run's result beside its JSONL.

    The trigram model is loaded lazily on the first cache miss and reused for the rest
    of the run, so an export where every run is already cached never loads the model.
    """

    def __init__(self) -> None:
        self._model: EnglishTrigramModel | None = None

    def _ensure_model(self) -> EnglishTrigramModel:
        if self._model is None:
            logger.info("english_ngram: loading trigram model for uncached runs")
            self._model = load_english_trigram_model()
        return self._model

    def score_run(self, jsonl_path: Path, texts: list[str]) -> list[float | None]:
        """Return per-message surprisals for one run, reading or writing its cache."""
        cache_path = jsonl_path.parent / _MESSAGE_ENGLISH_NGRAM_CACHE_NAME
        cache_key = _english_ngram_cache_key(jsonl_path=jsonl_path, message_count=len(texts))
        cached = _read_cache(cache_path=cache_path, cache_key=cache_key)
        if cached is not None:
            return cached
        surprisals: list[float | None]
        if any(text and text.strip() for text in texts):
            surprisals = _score_texts(model=self._ensure_model(), texts=texts)
        else:
            surprisals = [None] * len(texts)
        _write_cache(cache_path=cache_path, cache_key=cache_key, surprisals=surprisals)
        return surprisals
