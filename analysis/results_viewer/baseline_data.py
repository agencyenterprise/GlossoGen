"""Load baseline-labeled runs with the metrics used by the baseline tab plot.

Carries the three round-level metrics we currently plot: ``round_success``
(rounds fully stabilized), ``round_ended_idle`` (rounds ended because all
agents went idle on ``read_notifications``), and ``round_ended_timeout``
(rounds ended because the wall-clock round duration was reached). All three
are integer counts of rounds out of ``total_rounds``, so they share a common
Y axis scaled to the simulation's round count.

This module is streamlit-free so it can be reused by ad-hoc analysis scripts.
"""

from pathlib import Path
from typing import Callable, NamedTuple

import orjson

from analysis.results_viewer.run_catalog import EvaluatedRun

_BASELINE_LABEL = "baseline"
_BUDGET_PREFIX = "budget="
_ROUND_SUCCESS_EVALUATOR = "round_success"
_ROUND_ENDED_IDLE_EVALUATOR = "round_ended_idle"
_ROUND_ENDED_TIMEOUT_EVALUATOR = "round_ended_timeout"
_CONTENT_FILTER_REFUSAL_EVALUATOR = "content_filter_refusal"


class BaselineRun(NamedTuple):
    """A single baseline-labeled run with its budget and round-level metric counts.

    The three ``round_*`` and the ``content_filter_refusal_rounds`` fields are
    counts of rounds (0..total_rounds) and share a common Y-axis scale. The
    ``content_filter_refusal_total`` field is the raw number of refusals that
    occurred during the run and can be much larger than total_rounds (the
    runner retries each refusal, so a single round can accumulate many).
    """

    run_id: str
    run_dir: Path
    budget: int
    model: str
    postmortem_enabled: bool
    total_rounds: int
    round_success: int
    round_ended_idle: int
    round_ended_timeout: int
    content_filter_refusal_rounds: int
    content_filter_refusal_total: int
    labels: list[str]

    @property
    def series_key(self) -> str:
        """Plot-series identifier: one trace per (model, postmortem) variant."""
        suffix = "postmortem" if self.postmortem_enabled else "no-postmortem"
        return f"{self.model} · {suffix}"


class MetricOption(NamedTuple):
    """User-selectable metric for the baseline plot.

    ``attr`` is the ``BaselineRun`` integer field to aggregate; the plot shows
    the per-bucket mean and std of that count, so the Y axis is in
    ``number of rounds``. ``display_name`` is what the selector shows;
    ``y_axis_label`` is the wording shown on the chart's Y axis.
    """

    display_name: str
    attr: str
    y_axis_label: str

    def extract(self, run: "BaselineRun") -> float:
        """Pull this metric's count out of ``run`` as a float for aggregation."""
        return float(getattr(run, self.attr))


METRIC_OPTIONS: list[MetricOption] = [
    MetricOption(
        display_name="round_success",
        attr="round_success",
        y_axis_label="round_success (# of rounds stabilized)",
    ),
    MetricOption(
        display_name="round_ended_idle",
        attr="round_ended_idle",
        y_axis_label="round_ended_idle (# of rounds ended via all_agents_idle)",
    ),
    MetricOption(
        display_name="round_ended_timeout",
        attr="round_ended_timeout",
        y_axis_label="round_ended_timeout (# of rounds ended via round_timeout)",
    ),
]


REFUSAL_METRIC = MetricOption(
    display_name="content_filter_refusal",
    attr="content_filter_refusal_total",
    y_axis_label="content_filter refusals (total per run)",
)
"""Metric definition for the dedicated refusal plot.

Lives outside ``METRIC_OPTIONS`` because its magnitude (can exceed 100 per run)
doesn't share a Y axis with the round-count metrics. The baseline tab plots it
in its own section.
"""


def _read_labels(run_dir: Path) -> list[str]:
    """Return the labels stored in the run directory's ``labels.json``, or an empty list."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return []
    raw = orjson.loads(labels_path.read_bytes())
    if not isinstance(raw, list):
        return []
    return [label for label in raw if isinstance(label, str)]


def _parse_budget(labels: list[str]) -> int | None:
    """Extract the integer value from the first ``budget=<N>`` label, if any."""
    for label in labels:
        if label.startswith(_BUDGET_PREFIX):
            value = label[len(_BUDGET_PREFIX) :]
            if value.isdigit():
                return int(value)
    return None


def _metric_round_count(evaluated: EvaluatedRun, evaluator_name: str) -> int | None:
    """Return the number of rounds flagged by ``evaluator_name`` in the run's report.

    Uses ``len(rounds_identified)`` directly rather than ``score × total_rounds``
    to avoid floating-point rounding when the rate denominator is large.
    """
    for metric in evaluated.report.metrics:
        if metric.evaluator_name == evaluator_name:
            return len(metric.rounds_identified)
    return None


def _refusal_total(evaluated: EvaluatedRun, total_rounds: int) -> int:
    """Return the total number of refusals recorded for the run.

    The ``content_filter_refusal`` evaluator's ``score`` field is
    ``total_refusals / total_rounds``; multiplying back and rounding recovers
    the raw count. Returns 0 when the metric is missing (older evaluations).
    """
    for metric in evaluated.report.metrics:
        if metric.evaluator_name == _CONTENT_FILTER_REFUSAL_EVALUATOR:
            return round(float(metric.score) * total_rounds)
    return 0


def build_baseline_run(evaluated: EvaluatedRun) -> BaselineRun | None:
    """Convert an ``EvaluatedRun`` into a ``BaselineRun`` if it qualifies.

    A run qualifies when it has the ``baseline`` label, a parseable ``budget=<N>``
    label, and a ``round_success`` metric in its evaluation report. The two
    round-end metrics default to 0.0 when missing so older runs evaluated
    before they existed still render on the chart (just as a flat zero line).
    """
    labels = _read_labels(run_dir=evaluated.run_dir)
    if _BASELINE_LABEL not in labels:
        return None
    budget = _parse_budget(labels=labels)
    if budget is None:
        return None
    round_success = _metric_round_count(
        evaluated=evaluated, evaluator_name=_ROUND_SUCCESS_EVALUATOR
    )
    if round_success is None:
        return None
    idle = _metric_round_count(evaluated=evaluated, evaluator_name=_ROUND_ENDED_IDLE_EVALUATOR)
    timeout = _metric_round_count(
        evaluated=evaluated, evaluator_name=_ROUND_ENDED_TIMEOUT_EVALUATOR
    )
    refusal_rounds = _metric_round_count(
        evaluated=evaluated, evaluator_name=_CONTENT_FILTER_REFUSAL_EVALUATOR
    )
    postmortem_enabled = bool(evaluated.metadata.scenario_config.get("postmortem_enabled", False))
    total_rounds = int(evaluated.metadata.scenario_config.get("round_count", 0))
    refusal_total = _refusal_total(evaluated=evaluated, total_rounds=total_rounds)
    return BaselineRun(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        budget=budget,
        model=evaluated.metadata.primary_model,
        postmortem_enabled=postmortem_enabled,
        total_rounds=total_rounds,
        round_success=round_success,
        round_ended_idle=idle if idle is not None else 0,
        round_ended_timeout=timeout if timeout is not None else 0,
        content_filter_refusal_rounds=refusal_rounds if refusal_rounds is not None else 0,
        content_filter_refusal_total=refusal_total,
        labels=labels,
    )


def list_baseline_runs(evaluated_runs: list[EvaluatedRun]) -> list[BaselineRun]:
    """Filter ``evaluated_runs`` down to those labeled ``baseline`` with a budget."""
    out: list[BaselineRun] = []
    for run in evaluated_runs:
        baseline = build_baseline_run(evaluated=run)
        if baseline is not None:
            out.append(baseline)
    return out


class BudgetStats(NamedTuple):
    """Aggregate statistics for one (series, budget) bucket.

    ``series`` identifies the visual trace on the plot — currently
    ``"<model> · postmortem"`` or ``"<model> · no-postmortem"``.
    """

    series: str
    budget: int
    n: int
    mean: float
    std: float
    min_value: float
    max_value: float


def _mean(values: list[float]) -> float:
    """Arithmetic mean of ``values``; caller guarantees non-empty."""
    return sum(values) / len(values)


def _std(values: list[float], mean: float) -> float:
    """Population standard deviation of ``values`` around ``mean``.

    Uses population (N) rather than sample (N-1) so a single replica yields 0.0
    instead of NaN; the error bars then vanish cleanly for n=1 buckets.
    """
    if len(values) == 0:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance**0.5


def aggregate_by_budget(
    runs: list[BaselineRun],
    value_of: Callable[[BaselineRun], float],
) -> list[BudgetStats]:
    """Group ``runs`` by ``(series_key, budget)`` and compute per-bucket statistics.

    ``value_of`` extracts the metric to aggregate from each run — passing
    ``MetricOption.extract`` selects which of the three metrics is plotted.
    Output is sorted by series then budget so plot traces render in a stable order.
    """
    buckets: dict[tuple[str, int], list[float]] = {}
    for run in runs:
        key = (run.series_key, run.budget)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(value_of(run))
    out: list[BudgetStats] = []
    for (series, budget), scores in sorted(buckets.items()):
        mean = _mean(values=scores)
        std = _std(values=scores, mean=mean)
        out.append(
            BudgetStats(
                series=series,
                budget=budget,
                n=len(scores),
                mean=mean,
                std=std,
                min_value=min(scores),
                max_value=max(scores),
            )
        )
    return out
