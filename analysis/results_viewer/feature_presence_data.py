"""Load per-run ``communication_feature_presence.json`` sidecars + the matching ontology.

The communication-feature pipeline writes one
:class:`CommunicationFeaturePresenceSidecar` per run carrying a 0-1
confidence per ontology category, plus the matching ontology JSON under
``analysis/communication_ontology/``. This module reads both, joins
each run's per-category scores with the run's labels, scenario config,
and the report-derived in-team and cross-team round-success values, and
exposes one :class:`FeaturePresenceRun` per run for the Streamlit
"Language features" tab.

Per-run reads run concurrently in worker threads via ``asyncio.gather``
+ ``asyncio.to_thread`` and are memoized in a module-level dict keyed
on each run's sidecar / report / labels / manifest file stats. The
module is streamlit-free.
"""

import asyncio
import logging
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import orjson

from analysis.results_viewer.run_catalog import EvaluatedRun
from schmidt.scenarios.veyru.evaluation.metrics.communication.label_models import (
    CommunicationFeaturePresenceSidecar,
    CommunicationOntology,
    OntologyCategory,
)

logger = logging.getLogger(__name__)

FEATURE_PRESENCE_SIDECAR_FILENAME = "communication_feature_presence.json"
CROSS_RUN_MANIFEST_FILENAME = "cross_run_replace_manifest.json"
LABELS_FILENAME = "labels.json"
ONTOLOGY_DEFAULT_DIR = Path("analysis/communication_ontology")


FEATURE_CLASS_PRESETS: dict[str, list[str]] = {
    "Abbreviation family": [
        "first_letter_abbreviation",
        "syllable_truncation_abbreviation",
        "vowel_deletion_abbreviation",
        "single_letter_symptom_code",
    ],
    "Arbitrary mapping family": [
        "numeric_substitution",
        "positional_slot_ordering",
    ],
    "Structural family": [
        "telegraphic_ellipsis",
        "implicit_conjunction_of_sequential_steps",
        "arrow_notation_for_sequential_steps",
        "punctuation_as_inline_separator",
    ],
    "Pragmatic family": [
        "single_token_acknowledgement",
        "clarification_request",
        "register_shift_on_failure",
        "self_correction_without_prompting",
    ],
    "Reuse / evolution family": [
        "lexical_reuse_across_rounds",
        "compression_accelerates_across_rounds",
        "asymmetric_compression_by_role",
    ],
}
"""Preset groupings of ontology categories used by the hypothesis-test UI.

Lookup keys are display labels shown in the preset picker; values are
ontology category ids that should be selected for that family. Missing
categories (e.g. ontology changed) are silently filtered out when the
preset is applied.
"""


class _FeaturePresenceCacheKey(NamedTuple):
    """Identity tuple capturing every file this loader touches per run."""

    sidecar: tuple[int, int] | None
    labels: tuple[int, int] | None
    cross_run_manifest: tuple[int, int] | None
    report_mtime_ns: int


_FEATURE_PRESENCE_CACHE: dict[Path, tuple[_FeaturePresenceCacheKey, "FeaturePresenceRun"]] = {}


class FeaturePresenceRun(NamedTuple):
    """One run's feature-presence vector joined with outcome metrics."""

    run_id: str
    run_dir: Path
    primary_model: str
    scenario_config: dict[str, object]
    labels: list[str]
    ontology_version: str
    scores: dict[str, float]
    justifications: dict[str, str]
    notes: str
    in_team_round_success: float | None
    after_resume_round_success: float | None
    cross_team_source_a_run_id: str | None


class OntologyView(NamedTuple):
    """Loaded ontology with category lookup."""

    version: str
    path: Path
    categories: list[OntologyCategory]
    by_id: dict[str, OntologyCategory]


_ONTOLOGY_CACHE: dict[Path, tuple[tuple[int, int], OntologyView]] = {}


def _stat_or_none(path: Path) -> tuple[int, int] | None:
    """Return ``(size, mtime_ns)`` if the file exists, else ``None``."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


def _read_labels(run_dir: Path) -> list[str]:
    """Return the labels stored in the run directory's ``labels.json``."""
    labels_path = run_dir / LABELS_FILENAME
    if not labels_path.exists():
        return []
    try:
        raw = orjson.loads(labels_path.read_bytes())
    except Exception:
        logger.exception("Failed to read labels at %s", labels_path)
        return []
    if not isinstance(raw, list):
        return []
    return [label for label in raw if isinstance(label, str)]


def _read_cross_team_source_a(run_dir: Path) -> str | None:
    """Read ``cross_run_replace_manifest.json`` and return ``source_a_run_id`` if present."""
    manifest_path = run_dir / CROSS_RUN_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    try:
        raw = orjson.loads(manifest_path.read_bytes())
    except Exception:
        logger.exception("Failed to read cross-run manifest at %s", manifest_path)
        return None
    if not isinstance(raw, dict):
        return None
    source_a = raw.get("source_a_run_id")
    if isinstance(source_a, str):
        return source_a
    return None


def _measurement_score(evaluated: EvaluatedRun, metric_name: str) -> float | None:
    """Return the score of ``metric_name`` from the run's evaluation report, or ``None``."""
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == metric_name:
            return measurement.score
    return None


def _resolve_after_resume_score(evaluated: EvaluatedRun) -> float | None:
    """Return the run's ``round_success_after_resume`` score under any of its naming variants.

    The metric emits one Measurement per swap anchor: the manifest-based
    cross-run anchor keeps the bare name ``round_success_after_resume``;
    in-run scheduled-swap anchors append ``_round_<R>_<agent_id>``. For
    the cross-team transmissibility plot we want the manifest anchor
    score, so we prefer the bare name and fall back to the first
    matching prefix if the run only carries an in-run anchor.
    """
    bare = _measurement_score(evaluated=evaluated, metric_name="round_success_after_resume")
    if bare is not None:
        return bare
    for measurement in evaluated.report.measurements:
        if measurement.metric_name.startswith("round_success_after_resume"):
            return measurement.score
    return None


def _feature_presence_cache_key(evaluated: EvaluatedRun) -> _FeaturePresenceCacheKey:
    """Build the cache key from every file this loader reads."""
    run_dir = evaluated.run_dir
    return _FeaturePresenceCacheKey(
        sidecar=_stat_or_none(run_dir / FEATURE_PRESENCE_SIDECAR_FILENAME),
        labels=_stat_or_none(run_dir / LABELS_FILENAME),
        cross_run_manifest=_stat_or_none(run_dir / CROSS_RUN_MANIFEST_FILENAME),
        report_mtime_ns=_evaluated_report_mtime_ns(evaluated=evaluated),
    )


def _evaluated_report_mtime_ns(evaluated: EvaluatedRun) -> int:
    """Mtime of the run's evaluation report; ``0`` when the file is missing."""
    report_path = evaluated.run_dir / f"{evaluated.scenario_name}_report.json"
    try:
        return report_path.stat().st_mtime_ns
    except FileNotFoundError:
        return 0


def _build_feature_presence_run(evaluated: EvaluatedRun) -> FeaturePresenceRun | None:
    """Load one run's sidecar + manifest + report-derived metrics, or ``None`` to skip."""
    sidecar_path = evaluated.run_dir / FEATURE_PRESENCE_SIDECAR_FILENAME
    if not sidecar_path.exists():
        return None
    cache_key = _feature_presence_cache_key(evaluated=evaluated)
    cached = _FEATURE_PRESENCE_CACHE.get(evaluated.run_dir)
    if cached is not None and cached[0] == cache_key:
        return cached[1]
    try:
        sidecar = CommunicationFeaturePresenceSidecar.model_validate_json(sidecar_path.read_bytes())
    except Exception:
        logger.exception("Failed to parse feature-presence sidecar at %s", sidecar_path)
        return None
    scores = {entry.category_id: entry.confidence for entry in sidecar.scores}
    justifications = {entry.category_id: entry.justification for entry in sidecar.scores}
    in_team = _measurement_score(evaluated=evaluated, metric_name="round_success")
    after_resume = _resolve_after_resume_score(evaluated=evaluated)
    run = FeaturePresenceRun(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        primary_model=evaluated.metadata.primary_model,
        scenario_config=dict(evaluated.metadata.scenario_config),
        labels=_read_labels(run_dir=evaluated.run_dir),
        ontology_version=sidecar.ontology_version,
        scores=scores,
        justifications=justifications,
        notes=sidecar.notes,
        in_team_round_success=in_team,
        after_resume_round_success=after_resume,
        cross_team_source_a_run_id=_read_cross_team_source_a(run_dir=evaluated.run_dir),
    )
    _FEATURE_PRESENCE_CACHE[evaluated.run_dir] = (cache_key, run)
    return run


async def _build_feature_presence_run_async(
    evaluated: EvaluatedRun,
) -> FeaturePresenceRun | None:
    """Worker-thread wrapper around :func:`_build_feature_presence_run`."""
    return await asyncio.to_thread(_build_feature_presence_run, evaluated)


async def _list_feature_presence_runs_async(
    candidates: list[EvaluatedRun],
) -> list[FeaturePresenceRun]:
    """Concurrent fan-out across candidate runs, returning successful loads."""
    results = await asyncio.gather(
        *(_build_feature_presence_run_async(evaluated=run) for run in candidates),
    )
    return [run for run in results if run is not None]


def list_feature_presence_runs(evaluated_runs: list[EvaluatedRun]) -> list[FeaturePresenceRun]:
    """Return one :class:`FeaturePresenceRun` per run that has a feature-presence sidecar.

    Warm-cache fast path: when every candidate's cache key matches the
    module-level cache, the asyncio fan-out is skipped entirely (no
    thread pool spin-up, no event loop). On the typical Streamlit rerun
    this keeps the loader well under 20ms for 400+ run corpora — only
    the very first call per session pays the parallel-parse cost.
    """
    candidates = [
        run for run in evaluated_runs if (run.run_dir / FEATURE_PRESENCE_SIDECAR_FILENAME).exists()
    ]
    if not candidates:
        return []
    warm: list[FeaturePresenceRun] = []
    cold: list[EvaluatedRun] = []
    for evaluated in candidates:
        cached = _FEATURE_PRESENCE_CACHE.get(evaluated.run_dir)
        if cached is not None and cached[0] == _feature_presence_cache_key(evaluated=evaluated):
            warm.append(cached[1])
        else:
            cold.append(evaluated)
    if not cold:
        return warm
    cold_results = asyncio.run(_list_feature_presence_runs_async(candidates=cold))
    return warm + cold_results


def _load_ontology_from_path(ontology_path: Path) -> OntologyView | None:
    """Parse one ontology JSON file with caching."""
    stat = _stat_or_none(ontology_path)
    if stat is None:
        return None
    cached = _ONTOLOGY_CACHE.get(ontology_path)
    if cached is not None and cached[0] == stat:
        return cached[1]
    try:
        ontology = CommunicationOntology.model_validate_json(ontology_path.read_bytes())
    except Exception:
        logger.exception("Failed to parse ontology at %s", ontology_path)
        return None
    view = OntologyView(
        version=ontology.version,
        path=ontology_path,
        categories=ontology.categories,
        by_id={cat.id: cat for cat in ontology.categories},
    )
    _ONTOLOGY_CACHE[ontology_path] = (stat, view)
    return view


def resolve_ontology(
    runs: list[FeaturePresenceRun],
    ontology_dir: Path,
) -> OntologyView | None:
    """Pick the ontology JSON that matches the most-common sidecar version.

    The sidecars carry ``ontology_version`` (the version stem written by
    the consolidation script). We find the ontology JSON whose stem
    matches that version; failing that we fall back to the most recently
    written JSON in ``ontology_dir`` so the tab still loads with some
    category metadata even when versions drift.
    """
    if not ontology_dir.exists():
        return None
    if runs:
        most_common_version = Counter(run.ontology_version for run in runs).most_common(1)
        if most_common_version:
            preferred_stem = most_common_version[0][0]
            candidate = ontology_dir / f"{preferred_stem}.json"
            view = _load_ontology_from_path(ontology_path=candidate)
            if view is not None:
                return view
    json_files = sorted(
        ontology_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )
    for path in json_files:
        view = _load_ontology_from_path(ontology_path=path)
        if view is not None:
            return view
    return None


def runs_matching_feature_class(
    runs: list[FeaturePresenceRun],
    category_ids: set[str],
    threshold: float,
    require_all: bool,
) -> list[FeaturePresenceRun]:
    """Filter ``runs`` to those exhibiting the category set above ``threshold``.

    ``require_all=False`` (the default in the UI) keeps runs that score
    at or above ``threshold`` on **any** of the chosen categories;
    ``require_all=True`` requires every chosen category to meet the bar.
    Categories missing from a run's score dict count as 0.
    """
    if not category_ids:
        return []
    matching: list[FeaturePresenceRun] = []
    for run in runs:
        hits = [run.scores.get(cat_id, 0.0) >= threshold for cat_id in category_ids]
        if require_all:
            qualifies = all(hits)
        else:
            qualifies = any(hits)
        if qualifies:
            matching.append(run)
    return matching
