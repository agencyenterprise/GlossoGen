"""Load oss_frontier and baseline_oss runs for round_success comparison.

oss_frontier runs are mixed-model Veyru sims labeled ``oss_frontier`` with
``engineer=<short>`` and ``field_observer=<short>`` labels. baseline_oss
runs are uniform-model sims (both agents on the same model). This module
projects both into a common ``CellRun`` shape so the comparison tab can
render them side-by-side.

This module is streamlit-free so ad-hoc analysis scripts can reuse it.
"""

from pathlib import Path
from typing import NamedTuple

from analysis.results_viewer.measurement_scores import (
    measurement_score,
    perplexity_score,
    read_labels,
    round_success_score,
)
from analysis.results_viewer.run_catalog import EvaluatedRun

_LANGUAGE_EMERGENCE_METRIC = "language_emergence"

_OSS_FRONTIER_LABEL = "oss_frontier"
_BASELINE_OSS_LABEL = "baseline_oss"
_BUDGET_PREFIX = "budget="
_ENGINEER_PREFIX = "engineer="
_FIELD_OBSERVER_PREFIX = "field_observer="


class CellRun(NamedTuple):
    """A single Veyru run projected as a (group, engineer, observer, pm) cell.

    ``group`` is either ``"baseline_oss"`` or ``"oss_frontier"``. The short
    model names ("llama", "qwen", "sonnet", "gpt", "opus") are read from the
    ``engineer=`` / ``field_observer=`` labels on oss_frontier runs and
    derived from the primary model on baseline_oss runs (both agents share
    the same model in baseline_oss, so engineer == field_observer).
    """

    run_id: str
    run_dir: Path
    group: str
    engineer: str
    field_observer: str
    postmortem: bool
    budget: int
    total_rounds: int
    round_success: float
    perplexity: float | None
    language_emergence: float | None
    labels: list[str]

    def cell_key(self) -> str:
        """Human-readable cell identifier used as the chart x-axis tick."""
        pm = "PM=T" if self.postmortem else "PM=F"
        return f"{self.engineer}-{self.field_observer} {pm}"


def _short_model_name(full_model: str) -> str:
    """Map a full model string to the short form used in oss_frontier labels."""
    lower = full_model.lower()
    if "llama" in lower:
        return "llama"
    if "qwen" in lower:
        return "qwen"
    if "sonnet" in lower:
        return "sonnet"
    if "opus" in lower:
        return "opus"
    if "gpt-5" in lower or "gpt5" in lower:
        return "gpt"
    return full_model.split("/")[-1].lower()


def _label_value(labels: list[str], prefix: str) -> str | None:
    """First label starting with ``prefix`` with the prefix stripped, or ``None``."""
    for label in labels:
        if label.startswith(prefix):
            return label[len(prefix) :]
    return None


def _budget_from_labels(labels: list[str]) -> int | None:
    """Extract integer budget from a ``budget=<int>`` label, or ``None`` if absent."""
    raw = _label_value(labels=labels, prefix=_BUDGET_PREFIX)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _total_rounds(evaluated: EvaluatedRun) -> int:
    """Total round count from scenario_config; ``0`` if absent."""
    return int(evaluated.metadata.scenario_config.get("round_count", 0))


def _postmortem_enabled(evaluated: EvaluatedRun) -> bool:
    """Read postmortem flag from scenario_config; the source of truth.

    Some baseline_oss runs lost their ``postmortem=True/False`` label when
    earlier batch-relabel scripts overwrote ``labels.json``, so the label is
    not reliable. The scenario_config in the JSONL is preserved.
    """
    return bool(evaluated.metadata.scenario_config.get("postmortem_enabled", False))


def _budget_from_config(evaluated: EvaluatedRun) -> int | None:
    """Read ``round_time_budget_seconds`` from scenario_config, or ``None`` if absent."""
    raw = evaluated.metadata.scenario_config.get("round_time_budget_seconds")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def list_oss_frontier_runs(evaluated: list[EvaluatedRun]) -> list[CellRun]:
    """Project oss_frontier + baseline_oss runs that have round_success into ``CellRun``.

    Drops runs without a ``round_success`` measurement, without a ``budget=``
    label, or with no engineer/field_observer information.
    """
    out: list[CellRun] = []
    for run in evaluated:
        labels = read_labels(run_dir=run.run_dir)
        if _OSS_FRONTIER_LABEL in labels:
            group = _OSS_FRONTIER_LABEL
            eng = _label_value(labels=labels, prefix=_ENGINEER_PREFIX)
            obs = _label_value(labels=labels, prefix=_FIELD_OBSERVER_PREFIX)
            if eng is None or obs is None:
                continue
        elif _BASELINE_OSS_LABEL in labels:
            group = _BASELINE_OSS_LABEL
            short = _short_model_name(full_model=run.metadata.primary_model)
            eng = short
            obs = short
        else:
            continue
        budget = _budget_from_labels(labels=labels)
        if budget is None:
            budget = _budget_from_config(evaluated=run)
        if budget is None:
            continue
        score = round_success_score(evaluated=run)
        if score is None:
            continue
        ppl = perplexity_score(evaluated=run)
        emergence = measurement_score(evaluated=run, metric_name=_LANGUAGE_EMERGENCE_METRIC)
        out.append(
            CellRun(
                run_id=run.run_id,
                run_dir=run.run_dir,
                group=group,
                engineer=eng,
                field_observer=obs,
                postmortem=_postmortem_enabled(evaluated=run),
                budget=budget,
                total_rounds=_total_rounds(evaluated=run),
                round_success=float(score),
                perplexity=float(ppl) if ppl is not None else None,
                language_emergence=float(emergence) if emergence is not None else None,
                labels=labels,
            )
        )
    return out


class CellStats(NamedTuple):
    """Mean and spread of round_success for one cell across its replicas."""

    cell_key: str
    group: str
    engineer: str
    field_observer: str
    postmortem: bool
    n: int
    mean: float
    std: float
    min_value: float
    max_value: float


def aggregate_by_cell(runs: list[CellRun]) -> list[CellStats]:
    """Group runs by ``cell_key`` and emit per-cell ``mean``, ``std``, ``n`` stats."""
    buckets: dict[str, list[CellRun]] = {}
    for run in runs:
        buckets.setdefault(run.cell_key(), []).append(run)
    out: list[CellStats] = []
    for cell_key, replicas in sorted(buckets.items()):
        values = [replica.round_success for replica in replicas]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = float(variance**0.5)
        first = replicas[0]
        out.append(
            CellStats(
                cell_key=cell_key,
                group=first.group,
                engineer=first.engineer,
                field_observer=first.field_observer,
                postmortem=first.postmortem,
                n=len(replicas),
                mean=mean,
                std=std,
                min_value=min(values),
                max_value=max(values),
            )
        )
    return out
