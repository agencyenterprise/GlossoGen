"""Per-message gpt2 perplexity scoring with a per-run on-disk cache.

Mirrors the ``perplexity`` metric (``minicons.IncrementalLMScorer`` with
``reduction = -x.mean(0)``) and caches each run's per-message result beside its
JSONL, keyed by the JSONL's size + mtime + message count + a cache version. An
export where every run is already cached never loads gpt2.
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

import orjson
import torch
from minicons import scorer  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Per-run cache of message perplexities, written beside each run's JSONL. Recomputed
# whenever the JSONL changes or _PERPLEXITY_CACHE_VERSION is bumped (walk-order change).
_MESSAGE_PERPLEXITY_CACHE_NAME = "message_perplexity_cache.json"
_PERPLEXITY_CACHE_VERSION = 1


def _score_texts(lm_scorer: object, texts: list[str]) -> list[float | None]:
    """Per-message mean per-token surprisal (nats) under gpt2, aligned with ``texts``.

    Mirrors the ``perplexity`` metric: ``minicons.IncrementalLMScorer`` with
    ``reduction = -x.mean(0)``. Empty messages and single-token inputs (which return
    NaN — no left context) map to ``None`` so the column stays numeric elsewhere.
    """

    def _negative_mean(tensor: object) -> float:
        return -tensor.mean(0).item()  # type: ignore[attr-defined]

    results: list[float | None] = [None] * len(texts)
    scored_indices = [index for index, text in enumerate(texts) if text and text.strip()]
    batch_size = 256
    flat_scores: list[float] = []
    for start in range(0, len(scored_indices), batch_size):
        chunk = [texts[i] for i in scored_indices[start : start + batch_size]]
        flat_scores.extend(lm_scorer.sequence_score(chunk, reduction=_negative_mean))  # type: ignore[attr-defined]
    for index, score in zip(scored_indices, flat_scores):
        value = float(score)
        if not math.isnan(value):
            results[index] = value
    return results


class _PerplexityCacheKey(NamedTuple):
    """Identity of a run's cached per-message perplexities.

    A cache hit requires all fields to match, so any edit to the run's JSONL (size
    or mtime), a change in message count, or a bump to ``_PERPLEXITY_CACHE_VERSION``
    (used when the message-walk order changes) forces a recompute.
    """

    jsonl_size: int
    jsonl_mtime_ns: int
    message_count: int
    cache_version: int


def _perplexity_cache_key(jsonl_path: Path, message_count: int) -> _PerplexityCacheKey:
    """Build the cache key for ``jsonl_path``'s ``message_count`` link messages."""
    stat = jsonl_path.stat()
    return _PerplexityCacheKey(
        jsonl_size=stat.st_size,
        jsonl_mtime_ns=stat.st_mtime_ns,
        message_count=message_count,
        cache_version=_PERPLEXITY_CACHE_VERSION,
    )


def _read_perplexity_cache(
    cache_path: Path, cache_key: _PerplexityCacheKey
) -> list[float | None] | None:
    """Return the cached per-message perplexities if the cache matches ``cache_key``."""
    if not cache_path.exists():
        return None
    try:
        payload = orjson.loads(cache_path.read_bytes())
    except (orjson.JSONDecodeError, OSError):
        logger.exception("perplexity cache unreadable, recomputing: %s", cache_path)
        return None
    matches = (
        payload.get("jsonl_size") == cache_key.jsonl_size
        and payload.get("jsonl_mtime_ns") == cache_key.jsonl_mtime_ns
        and payload.get("message_count") == cache_key.message_count
        and payload.get("cache_version") == cache_key.cache_version
    )
    if not matches:
        return None
    return list(payload["perplexities"])


def _write_perplexity_cache(
    cache_path: Path, cache_key: _PerplexityCacheKey, perplexities: list[float | None]
) -> None:
    """Persist ``perplexities`` for a run, keyed by ``cache_key``, beside its JSONL."""
    payload = {
        "jsonl_size": cache_key.jsonl_size,
        "jsonl_mtime_ns": cache_key.jsonl_mtime_ns,
        "message_count": cache_key.message_count,
        "cache_version": cache_key.cache_version,
        "perplexities": perplexities,
    }
    cache_path.write_bytes(orjson.dumps(payload))


class MessagePerplexityScorer:
    """Scores link-message perplexity, caching each run's result beside its JSONL.

    The gpt2 model is loaded lazily on the first cache miss and reused for the rest of
    the run, so an export where every run is already cached never loads gpt2 at all.
    """

    def __init__(self) -> None:
        self._lm_scorer: object | None = None

    def _ensure_scorer(self) -> object:
        if self._lm_scorer is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("perplexity: loading gpt2 on %s for uncached runs", device)
            self._lm_scorer = scorer.IncrementalLMScorer("gpt2", device)
        return self._lm_scorer

    def score_run(self, jsonl_path: Path, texts: list[str]) -> list[float | None]:
        """Return per-message perplexities for one run, reading or writing its cache."""
        cache_path = jsonl_path.parent / _MESSAGE_PERPLEXITY_CACHE_NAME
        cache_key = _perplexity_cache_key(jsonl_path=jsonl_path, message_count=len(texts))
        cached = _read_perplexity_cache(cache_path=cache_path, cache_key=cache_key)
        if cached is not None:
            return cached
        perplexities: list[float | None]
        if any(text and text.strip() for text in texts):
            perplexities = _score_texts(lm_scorer=self._ensure_scorer(), texts=texts)
        else:
            perplexities = [None] * len(texts)
        _write_perplexity_cache(
            cache_path=cache_path, cache_key=cache_key, perplexities=perplexities
        )
        return perplexities
