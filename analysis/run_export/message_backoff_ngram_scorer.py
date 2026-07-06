"""Per-message English backoff-trigram surprisal scoring with a per-run on-disk cache.

Mirrors the ``english_ngram_backoff_surprisal`` metric
(``BackoffTrigramModel.mean_char_surprisal``, case-sensitive with digits + punctuation
retained) and caches each run's per-message result beside its JSONL, keyed by the JSONL's
size + mtime + message count + a cache version. An export where every run is already cached
never loads the model. Higher surprisal means a message is less English-like.
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

import orjson

from schmidt.evaluation.metrics.english_ngram.backoff_ngram_model import (
    BackoffTrigramModel,
    load_backoff_ngram_model,
)

logger = logging.getLogger(__name__)

# Per-run cache of message surprisals, written beside each run's JSONL. Recomputed whenever
# the JSONL changes or _BACKOFF_NGRAM_CACHE_VERSION is bumped (walk-order change).
_MESSAGE_BACKOFF_NGRAM_CACHE_NAME = "message_backoff_ngram_cache.json"
_BACKOFF_NGRAM_CACHE_VERSION = 1

# The metric scores with case-sensitivity and punctuation retained; the scorer must match.
_CASE_SENSITIVE = True
_KEEP_PUNCTUATION = True


def _score_texts(model: BackoffTrigramModel, texts: list[str]) -> list[float | None]:
    """Per-message mean per-char backoff surprisal (nats), aligned with ``texts``.

    Empty or whitespace-only messages (which yield NaN — no scorable characters) map to
    ``None`` so the column stays numeric elsewhere.
    """
    results: list[float | None] = [None] * len(texts)
    for index, text in enumerate(texts):
        if not text or not text.strip():
            continue
        value = model.mean_char_surprisal(text=text)
        if not math.isnan(value):
            results[index] = value
    return results


class _BackoffNgramCacheKey(NamedTuple):
    """Identity of a run's cached per-message surprisals.

    A cache hit requires all fields to match, so any edit to the run's JSONL (size or mtime),
    a change in message count, or a bump to ``_BACKOFF_NGRAM_CACHE_VERSION`` forces a recompute.
    """

    jsonl_size: int
    jsonl_mtime_ns: int
    message_count: int
    cache_version: int


def _backoff_ngram_cache_key(jsonl_path: Path, message_count: int) -> _BackoffNgramCacheKey:
    """Build the cache key for ``jsonl_path``'s ``message_count`` link messages."""
    stat = jsonl_path.stat()
    return _BackoffNgramCacheKey(
        jsonl_size=stat.st_size,
        jsonl_mtime_ns=stat.st_mtime_ns,
        message_count=message_count,
        cache_version=_BACKOFF_NGRAM_CACHE_VERSION,
    )


def _read_cache(cache_path: Path, cache_key: _BackoffNgramCacheKey) -> list[float | None] | None:
    """Return the cached per-message surprisals if the cache matches ``cache_key``."""
    if not cache_path.exists():
        return None
    try:
        payload = orjson.loads(cache_path.read_bytes())
    except (orjson.JSONDecodeError, OSError):
        logger.exception("backoff_ngram cache unreadable, recomputing: %s", cache_path)
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
    cache_path: Path, cache_key: _BackoffNgramCacheKey, surprisals: list[float | None]
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


class MessageBackoffNgramScorer:
    """Scores link-message backoff-trigram surprisal, caching each run's result beside its JSONL.

    The model is loaded lazily on the first cache miss and reused for the rest of the run, so
    an export where every run is already cached never loads the model.
    """

    def __init__(self) -> None:
        self._model: BackoffTrigramModel | None = None

    def _ensure_model(self) -> BackoffTrigramModel:
        if self._model is None:
            logger.info("backoff_ngram: loading trigram model for uncached runs")
            self._model = load_backoff_ngram_model(
                case_sensitive=_CASE_SENSITIVE,
                keep_punctuation=_KEEP_PUNCTUATION,
            )
        return self._model

    def score_run(self, jsonl_path: Path, texts: list[str]) -> list[float | None]:
        """Return per-message surprisals for one run, reading or writing its cache."""
        cache_path = jsonl_path.parent / _MESSAGE_BACKOFF_NGRAM_CACHE_NAME
        cache_key = _backoff_ngram_cache_key(jsonl_path=jsonl_path, message_count=len(texts))
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
