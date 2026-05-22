"""Per-round link-channel message similarity between resume runs, averaged over phases.

For each ``MultiSwapRun`` the helpers here group every ``message_sent`` event
on the ``link`` channel by ``round_number`` and concatenate the texts within
each round. A per-round similarity score is computed between each pair of runs
(only on rounds where **both** sides have at least one link message) under a
caller-supplied :data:`SimilarityScoreFn`, and the per-phase score is the mean
of those per-round similarities.

Two score functions are exported:

- :func:`levenshtein_score` — normalized character-level edit distance. Sensitive
  to retry-loop length and message-count divergence (a replica that needs more
  back-and-forth on a round scores lower even when the shorthand vocabulary is
  identical).
- :func:`bigram_jaccard_score` — Jaccard similarity over word-level bigrams.
  Captures shared vocabulary and phrasing while being mostly insensitive to
  transcript length (because Jaccard is a set operation).

Result is cached per ``MultiSwapRun.run_id`` on the JSONL ``(size, mtime_ns)``
fingerprint so repeat lookups during a Streamlit rerender are free.
"""

import logging
from pathlib import Path
from typing import Callable

import orjson
from rapidfuzz.distance import Levenshtein

from analysis.results_viewer.multi_swap_data import MultiSwapRun

logger = logging.getLogger(__name__)

_LINK_CHANNEL_ID = "link"

SimilarityScoreFn = Callable[[str, str], float | None]
"""Single-pair similarity score in [0, 1] on two non-empty texts, or ``None`` when undefined."""


class _PerRoundCacheKey:
    """Identity tuple of (JSONL size, mtime_ns) — refreshed only when the file changes."""

    __slots__ = ("size", "mtime_ns")

    def __init__(self, size: int, mtime_ns: int) -> None:
        self.size = size
        self.mtime_ns = mtime_ns

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _PerRoundCacheKey):
            return False
        return self.size == other.size and self.mtime_ns == other.mtime_ns

    def __hash__(self) -> int:
        return hash((self.size, self.mtime_ns))


# run_id -> (cache_key, phase_index -> {round_number: concatenated_link_text})
_PER_ROUND_CACHE: dict[str, tuple[_PerRoundCacheKey, dict[int, dict[int, str]]]] = {}


def _jsonl_path(run: MultiSwapRun) -> Path:
    return run.run_dir / f"{run.scenario_name}.jsonl"


def _extract_per_round_texts(run: MultiSwapRun) -> dict[int, dict[int, str]]:
    """Return ``{phase_index: {round_number: concatenated_link_text}}`` for every phase.

    Reads the run's JSONL once, bucketing every link ``message_sent`` event
    into the phase whose round window contains its ``round_number`` and the
    specific round inside that phase. Multiple messages within a single round
    are joined with newlines (in send-order). Cached on the JSONL fingerprint
    so repeated calls during the same Streamlit session are free.
    """
    jsonl_path = _jsonl_path(run=run)
    try:
        stat = jsonl_path.stat()
    except FileNotFoundError:
        return {}
    cache_key = _PerRoundCacheKey(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
    cached = _PER_ROUND_CACHE.get(run.run_id)
    if cached is not None and cached[0] == cache_key:
        return cached[1]

    phase_for_round: dict[int, int] = {}
    for phase in run.phases:
        for round_number in range(phase.round_start, phase.round_end + 1):
            phase_for_round[round_number] = phase.phase_index

    # {phase_index: {round_number: [text, ...]}}
    bucket: dict[int, dict[int, list[str]]] = {p.phase_index: {} for p in run.phases}
    with jsonl_path.open(mode="rb") as handle:
        for raw in handle:
            if b'"message_sent"' not in raw:
                continue
            event = orjson.loads(raw)
            if event.get("event_type") != "message_sent":
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            if message.get("channel_id") != _LINK_CHANNEL_ID:
                continue
            round_number = event.get("round_number")
            if not isinstance(round_number, int):
                continue
            phase_index = phase_for_round.get(round_number)
            if phase_index is None:
                continue
            text = message.get("text") or ""
            if not isinstance(text, str) or not text:
                continue
            bucket[phase_index].setdefault(round_number, []).append(text)
    joined: dict[int, dict[int, str]] = {}
    for phase_index, rounds in bucket.items():
        joined[phase_index] = {rn: "\n".join(texts) for rn, texts in rounds.items()}
    _PER_ROUND_CACHE[run.run_id] = (cache_key, joined)
    return joined


def _per_round_texts(run: MultiSwapRun, phase_index: int) -> dict[int, str]:
    """Return ``{round_number: link_text}`` for ``run`` inside ``phase_index``."""
    return _extract_per_round_texts(run=run).get(phase_index, {})


def phase_round_texts(run: MultiSwapRun, phase_index: int) -> dict[int, str]:
    """Public wrapper: ``{round_number: concatenated_link_text}`` for one phase of ``run``."""
    return _per_round_texts(run=run, phase_index=phase_index)


def levenshtein_score(text_a: str, text_b: str) -> float | None:
    """Normalized character-level Levenshtein similarity in [0, 1].

    Returns ``None`` when either side is empty. Sensitive to message length and
    retry-count divergence — a replica that runs extra retry exchanges in a
    round scores low even when its shorthand vocabulary is identical to the
    reference.
    """
    if not text_a or not text_b:
        return None
    return float(Levenshtein.normalized_similarity(text_a, text_b))


def _word_bigrams(text: str) -> set[tuple[str, str]]:
    """Lower-cased whitespace-tokenized word bigrams from ``text``.

    Punctuation stays attached to the token (so ``"V21:"`` and ``"V21,"`` are
    distinct) — that's intentional since the shorthand protocol uses
    punctuation meaningfully (round prefix, separators, terminator marks).
    Returns an empty set when ``text`` has fewer than two tokens.
    """
    tokens = text.lower().split()
    if len(tokens) < 2:
        return set()
    return set(zip(tokens, tokens[1:]))


def bigram_jaccard_score(text_a: str, text_b: str) -> float | None:
    """Jaccard similarity of word-bigram sets in [0, 1].

    Captures shared vocabulary and phrasing in a way that is mostly insensitive
    to transcript length (because Jaccard is a set operation): a replica that
    runs extra retry exchanges keeps its shared bigrams from the source plus
    adds new ones, so the union grows linearly while the intersection stays
    near-constant. That makes it complementary to
    :func:`levenshtein_score` for diagnosing "is the protocol vocabulary the
    same?" vs. "is the transcript trajectory the same?".

    Returns ``None`` when either side is empty or has fewer than two tokens
    (so no bigrams can be formed).
    """
    if not text_a or not text_b:
        return None
    bigrams_a = _word_bigrams(text_a)
    bigrams_b = _word_bigrams(text_b)
    if not bigrams_a or not bigrams_b:
        return None
    union = bigrams_a | bigrams_b
    return len(bigrams_a & bigrams_b) / len(union)


def _per_round_mean(
    rounds_a: dict[int, str],
    rounds_b: dict[int, str],
    score_fn: SimilarityScoreFn,
) -> float | None:
    """Mean ``score_fn`` over rounds present in both sides with non-empty text.

    Returns ``None`` when no round is comparable (no shared rounds with text
    on both sides, or every per-round score came back ``None``).
    """
    common_rounds = set(rounds_a) & set(rounds_b)
    sims: list[float] = []
    for round_number in common_rounds:
        text_a = rounds_a.get(round_number, "")
        text_b = rounds_b.get(round_number, "")
        score = score_fn(text_a, text_b)
        if score is None:
            continue
        sims.append(score)
    if not sims:
        return None
    return sum(sims) / len(sims)


def similarity_to_reference(
    run: MultiSwapRun,
    reference_run: MultiSwapRun,
    phase_index: int,
    score_fn: SimilarityScoreFn,
) -> float | None:
    """Mean per-round ``score_fn`` between ``run`` and ``reference_run`` on ``phase_index``.

    Per round in ``phase_index``: similarity = ``score_fn(replica_text,
    source_text)`` on the concatenated link-channel text for that round on each
    side. Rounds with empty text on either side (or where ``score_fn`` returns
    ``None``) are skipped. The phase score is the arithmetic mean over the
    surviving per-round scores. ``None`` if no round produced a score.
    """
    return _per_round_mean(
        rounds_a=_per_round_texts(run=run, phase_index=phase_index),
        rounds_b=_per_round_texts(run=reference_run, phase_index=phase_index),
        score_fn=score_fn,
    )


def mean_similarity_to_pool(
    run: MultiSwapRun,
    pool: list[MultiSwapRun],
    phase_index: int,
    score_fn: SimilarityScoreFn,
) -> float | None:
    """Mean of ``similarity_to_reference(run, ref, phase_index, score_fn)`` over every ``ref``.

    Self-comparison (``ref.run_id == run.run_id``) is excluded so an
    intervention replica is never accidentally compared to itself when it
    appears in both ``pool`` and as ``run``.
    """
    run_rounds = _per_round_texts(run=run, phase_index=phase_index)
    if not run_rounds:
        return None
    sims: list[float] = []
    for ref in pool:
        if ref.run_id == run.run_id:
            continue
        ref_rounds = _per_round_texts(run=ref, phase_index=phase_index)
        if not ref_rounds:
            continue
        value = _per_round_mean(rounds_a=run_rounds, rounds_b=ref_rounds, score_fn=score_fn)
        if value is None:
            continue
        sims.append(value)
    if not sims:
        return None
    return sum(sims) / len(sims)


def pool_self_similarity(
    pool: list[MultiSwapRun],
    phase_index: int,
    score_fn: SimilarityScoreFn,
) -> float | None:
    """Mean per-round-mean ``score_fn`` over every unordered pair within ``pool``.

    The "noise floor" for the overview chart: how similar are the pool members
    to each other under the chosen score function? The overview shows
    ``mean(intervention-to-pool) − pool_self_similarity``. ``None`` if fewer
    than two pool members have extractable per-round text on this phase.
    """
    members: list[dict[int, str]] = []
    for run in pool:
        rounds = _per_round_texts(run=run, phase_index=phase_index)
        if rounds:
            members.append(rounds)
    if len(members) < 2:
        return None
    sims: list[float] = []
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            value = _per_round_mean(rounds_a=members[i], rounds_b=members[j], score_fn=score_fn)
            if value is not None:
                sims.append(value)
    if not sims:
        return None
    return sum(sims) / len(sims)
