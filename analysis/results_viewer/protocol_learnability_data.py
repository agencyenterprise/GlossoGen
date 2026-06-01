"""Data loading for the streamlit "Protocol learnability" tab.

Walks every run in the runs directory, joins each ``phase=baseline`` source with
its ``phase=resume_expected`` (the intact team's continued performance — the
"expected" ceiling), ``phase=resume_expected_no_postmortem`` (intact team with
the postmortem channel killed going forward — isolates the no-postmortem effect
from the fresh-observer effect), and ``phase=replace_learned`` (a fresh
same-model field observer that learned the protocol from the windowed link
transcript) derived runs, and scores each derived run's ``round_success`` over a
rounds-window. Also loads per-baseline ``communication_feature_presence``
vectors so the tab can contrast feature confidences between high- and
low-learnability protocols.
"""

import json
import statistics
from pathlib import Path
from typing import NamedTuple

import streamlit as st


class BaselineLearnability(NamedTuple):
    """Aggregated expected / expected_no_postmortem / learned round-success for one baseline source.

    ``expected_no_pm_*`` carries ``mean=0.0, std=0.0, n=0`` when the third
    condition's derived runs haven't been collected yet for this source; the
    renderer skips the triangle marker when ``n_expected_no_pm == 0``.
    """

    src_id: str
    model_short: str
    budget: str
    expected_mean: float
    expected_std: float
    expected_no_pm_mean: float
    expected_no_pm_std: float
    learned_mean: float
    learned_std: float
    delta: float
    n_expected: int
    n_expected_no_pm: int
    n_learned: int


class FeatureContrast(NamedTuple):
    """Mean ``communication_feature_presence`` confidence in a feature, high vs low learnability."""

    feature: str
    high_mean: float
    low_mean: float
    gap: float
    n_high: int
    n_low: int


def _read_labels(run_dir: Path) -> list[str]:
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return []
    return json.loads(labels_path.read_text())


def _label_value(labels: list[str], prefix: str) -> str | None:
    for label in labels:
        if label.startswith(prefix):
            return label[len(prefix) :]
    return None


def _window_round_success(report_path: Path, window_lo: int, window_hi: int) -> float | None:
    if not report_path.exists():
        return None
    report = json.loads(report_path.read_text())
    measurements = report.get("measurements", [])
    rounds = next(
        (m.get("per_round", []) for m in measurements if m.get("metric_name") == "round_success"),
        [],
    )
    values = [
        float(obs["value"]) for obs in rounds if window_lo <= int(obs["round_number"]) <= window_hi
    ]
    if not values:
        return None
    return statistics.mean(values)


def _feature_scores(run_dir: Path) -> dict[str, float] | None:
    path = run_dir / "communication_feature_presence.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    scores: dict[str, float] = {}
    for entry in data.get("scores", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("category_id")
        conf = entry.get("confidence")
        if name is not None and conf is not None:
            scores[str(name)] = float(conf)
    if not scores:
        return None
    return scores


class _Accumulator:
    """Mutable per-baseline collector of expected / expected_no_pm / learned window scores."""

    def __init__(self, model_short: str) -> None:
        self.model_short = model_short
        self.expected: list[float] = []
        self.expected_no_pm: list[float] = []
        self.learned: list[float] = []


def _iter_run_dirs(root: Path) -> list[Path]:
    """Yield every ``<scenario>/<timestamp>`` run directory under ``root``.

    Accepts either the top-level runs directory (``./runs``) or a scenario
    subdirectory (``./runs/veyru``). At the top level, run dirs live at depth 2
    under the scenario subdir; passing a scenario subdir directly puts them at
    depth 1. Subdirectories whose names begin with ``.`` or ``_`` are skipped
    (these are stdout / log buckets, not runs).
    """
    result: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        if (child / "labels.json").exists() or list(child.glob("*.jsonl")):
            result.append(child)
            continue
        for grandchild in child.iterdir():
            if grandchild.is_dir() and not grandchild.name.startswith((".", "_")):
                result.append(grandchild)
    return result


def _load_results_uncached(
    runs_root: str, window_lo: int, window_hi: int
) -> list[BaselineLearnability]:
    root = Path(runs_root)
    baselines: dict[str, tuple[str, str]] = {}
    accums: dict[str, _Accumulator] = {}
    for run_dir in _iter_run_dirs(root=root):
        labels = _read_labels(run_dir=run_dir)
        if "protocol_learnability" not in labels:
            continue
        model_short = _label_value(labels=labels, prefix="model=") or "unknown"
        budget = _label_value(labels=labels, prefix="budget=") or "?"
        scenario_name = run_dir.parent.name
        if "phase=baseline" in labels:
            src_id = f"{scenario_name}/{run_dir.name}"
            baselines[src_id] = (model_short, budget)
            accums.setdefault(src_id, _Accumulator(model_short=model_short))
            continue
        src_id = _label_value(labels=labels, prefix="src=")
        if src_id is None:
            continue
        score = _window_round_success(
            report_path=run_dir / "veyru_report.json",
            window_lo=window_lo,
            window_hi=window_hi,
        )
        if score is None:
            continue
        acc = accums.setdefault(src_id, _Accumulator(model_short=model_short))
        if "phase=resume_expected_no_postmortem" in labels:
            acc.expected_no_pm.append(score)
        elif "phase=resume_expected" in labels:
            acc.expected.append(score)
        elif "phase=replace_learned" in labels:
            acc.learned.append(score)

    results: list[BaselineLearnability] = []
    for src_id, (model_short, budget) in baselines.items():
        acc = accums[src_id]
        if not acc.expected or not acc.learned:
            continue
        expected_mean = statistics.mean(acc.expected)
        learned_mean = statistics.mean(acc.learned)
        expected_std = statistics.stdev(acc.expected) if len(acc.expected) >= 2 else 0.0
        learned_std = statistics.stdev(acc.learned) if len(acc.learned) >= 2 else 0.0
        if acc.expected_no_pm:
            expected_no_pm_mean = statistics.mean(acc.expected_no_pm)
            expected_no_pm_std = (
                statistics.stdev(acc.expected_no_pm) if len(acc.expected_no_pm) >= 2 else 0.0
            )
        else:
            expected_no_pm_mean = 0.0
            expected_no_pm_std = 0.0
        results.append(
            BaselineLearnability(
                src_id=src_id,
                model_short=model_short,
                budget=budget,
                expected_mean=expected_mean,
                expected_std=expected_std,
                expected_no_pm_mean=expected_no_pm_mean,
                expected_no_pm_std=expected_no_pm_std,
                learned_mean=learned_mean,
                learned_std=learned_std,
                delta=learned_mean - expected_mean,
                n_expected=len(acc.expected),
                n_expected_no_pm=len(acc.expected_no_pm),
                n_learned=len(acc.learned),
            )
        )
    results.sort(key=lambda r: r.learned_mean, reverse=True)
    return results


@st.cache_data(show_spinner=False)
def load_results(runs_root: str, window_lo: int, window_hi: int) -> list[BaselineLearnability]:
    """Cached wrapper around the disk walk; key is ``(runs_root, window_lo, window_hi)``."""
    return _load_results_uncached(runs_root=runs_root, window_lo=window_lo, window_hi=window_hi)


def _contrast_uncached(
    runs_root: str, results: list[BaselineLearnability], tertile_fraction: float
) -> list[FeatureContrast]:
    if len(results) < 3:
        return []
    cut = max(1, int(len(results) * tertile_fraction))
    high_ids = {r.src_id.split("/")[-1] for r in results[:cut]}
    low_ids = {r.src_id.split("/")[-1] for r in results[-cut:]}
    high_scores: list[dict[str, float]] = []
    low_scores: list[dict[str, float]] = []
    root = Path(runs_root)
    for run_dir in _iter_run_dirs(root=root):
        if run_dir.name in high_ids:
            sc = _feature_scores(run_dir=run_dir)
            if sc is not None:
                high_scores.append(sc)
        elif run_dir.name in low_ids:
            sc = _feature_scores(run_dir=run_dir)
            if sc is not None:
                low_scores.append(sc)
    if not high_scores or not low_scores:
        return []
    features = {f for s in high_scores for f in s} & {f for s in low_scores for f in s}
    rows: list[FeatureContrast] = []
    for feature in features:
        h_values = [s[feature] for s in high_scores if feature in s]
        l_values = [s[feature] for s in low_scores if feature in s]
        high_mean = statistics.mean(h_values)
        low_mean = statistics.mean(l_values)
        rows.append(
            FeatureContrast(
                feature=feature,
                high_mean=high_mean,
                low_mean=low_mean,
                gap=high_mean - low_mean,
                n_high=len(h_values),
                n_low=len(l_values),
            )
        )
    rows.sort(key=lambda row: abs(row.gap), reverse=True)
    return rows


@st.cache_data(show_spinner=False)
def feature_contrast(
    runs_root: str,
    results: list[BaselineLearnability],
    tertile_fraction: float,
) -> list[FeatureContrast]:
    """Cached wrapper around the high/low tertile feature contrast computation."""
    return _contrast_uncached(
        runs_root=runs_root, results=results, tertile_fraction=tertile_fraction
    )


class FeatureEvidenceSample(NamedTuple):
    """One baseline's confidence + LLM-judge justification for one ontology category."""

    src_id: str
    model_short: str
    confidence: float
    justification: str


class FeatureEvidence(NamedTuple):
    """Per-feature evidence bundle for the contrast view."""

    feature: str
    description: str
    high_samples: list[FeatureEvidenceSample]
    low_samples: list[FeatureEvidenceSample]


@st.cache_data(show_spinner=False)
def load_ontology_descriptions(runs_root: str) -> dict[str, str]:
    """Return ``{category_id: description}`` from the most recent ontology JSON.

    Reads the newest file in ``<runs_root>/veyru/_ontology/*.json`` (resolved by
    mtime). Returns an empty dict when the directory is missing or no JSON
    parses; the tab degrades gracefully (the description line just stays empty).
    """
    ontology_dir = Path(runs_root) / "veyru" / "_ontology"
    if not ontology_dir.exists():
        return {}
    candidates = sorted(
        ontology_dir.glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        cats = data.get("categories")
        if not isinstance(cats, list):
            continue
        out: dict[str, str] = {}
        for entry in cats:
            if not isinstance(entry, dict):
                continue
            cid = entry.get("id")
            desc = entry.get("description")
            if isinstance(cid, str) and isinstance(desc, str):
                out[cid] = desc
        if out:
            return out
    return {}


def _scores_with_justifications(run_dir: Path) -> dict[str, tuple[float, str]]:
    """Return ``{category_id: (confidence, justification)}`` for one baseline."""
    path = run_dir / "communication_feature_presence.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    out: dict[str, tuple[float, str]] = {}
    for entry in data.get("scores", []):
        if not isinstance(entry, dict):
            continue
        cid = entry.get("category_id")
        if cid is None:
            continue
        out[str(cid)] = (
            float(entry.get("confidence", 0.0)),
            str(entry.get("justification", "")),
        )
    return out


def _build_evidence(
    runs_root: str,
    feature: str,
    high_src_ids: tuple[str, ...],
    low_src_ids: tuple[str, ...],
    descriptions: dict[str, str],
) -> FeatureEvidence:
    """Collect per-baseline samples for one feature across the high/low tertile slices."""
    high_samples: list[FeatureEvidenceSample] = []
    low_samples: list[FeatureEvidenceSample] = []
    by_basename = {src.split("/")[-1] for src in (*high_src_ids, *low_src_ids)}
    root = Path(runs_root)
    for run_dir in _iter_run_dirs(root=root):
        if run_dir.name not in by_basename:
            continue
        labels = _read_labels(run_dir=run_dir)
        if "protocol_learnability" not in labels or "phase=baseline" not in labels:
            continue
        model_short = _label_value(labels=labels, prefix="model=") or "unknown"
        scenario_name = run_dir.parent.name
        src_id = f"{scenario_name}/{run_dir.name}"
        scores = _scores_with_justifications(run_dir=run_dir)
        entry = scores.get(feature)
        if entry is None:
            continue
        confidence, justification = entry
        sample = FeatureEvidenceSample(
            src_id=src_id,
            model_short=model_short,
            confidence=confidence,
            justification=justification,
        )
        if src_id in high_src_ids:
            high_samples.append(sample)
        elif src_id in low_src_ids:
            low_samples.append(sample)
    high_samples.sort(key=lambda s: s.confidence, reverse=True)
    low_samples.sort(key=lambda s: s.confidence)
    return FeatureEvidence(
        feature=feature,
        description=descriptions.get(feature, ""),
        high_samples=high_samples,
        low_samples=low_samples,
    )


def _tertile_split(
    results: list[BaselineLearnability], tertile_fraction: float
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(high_src_ids, low_src_ids)`` — top/bottom tertile by learned mean."""
    if len(results) < 3:
        return ((), ())
    cut = max(1, int(len(results) * tertile_fraction))
    high = tuple(r.src_id for r in results[:cut])
    low = tuple(r.src_id for r in results[-cut:])
    return high, low


@st.cache_data(show_spinner=False)
def feature_evidence(
    runs_root: str,
    feature: str,
    results: list[BaselineLearnability],
    tertile_fraction: float,
) -> FeatureEvidence:
    """Cached per-feature evidence bundle (description + tertile samples)."""
    high, low = _tertile_split(results=results, tertile_fraction=tertile_fraction)
    descriptions = load_ontology_descriptions(runs_root=runs_root)
    return _build_evidence(
        runs_root=runs_root,
        feature=feature,
        high_src_ids=high,
        low_src_ids=low,
        descriptions=descriptions,
    )
