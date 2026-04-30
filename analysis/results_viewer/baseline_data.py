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
_ROUND_SUCCESS_METRIC = "round_success"
_ROUND_ENDED_IDLE_METRIC = "round_ended_idle"
_ROUND_ENDED_TIMEOUT_METRIC = "round_ended_timeout"
_CONTENT_FILTER_REFUSAL_METRIC = "content_filter_refusal"
_PERPLEXITY_METRIC = "perplexity"
_MWL_METRIC = "mean_word_length"
_MML_METRIC = "mean_message_length"


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
    perplexity_score: float | None
    mwl_score: float | None
    mml_score: float | None
    labels: list[str]

    def series_key(self, selected_batch_labels: frozenset[str]) -> str:
        """Plot-series identifier: one trace per (model, postmortem, batch-label-subset)."""
        suffix = "postmortem" if self.postmortem_enabled else "no-postmortem"
        carried = sorted(label for label in selected_batch_labels if label in self.labels)
        if carried:
            return f"{self.model} · {suffix} ({', '.join(carried)})"
        return f"{self.model} · {suffix}"


class YAxisSpec(NamedTuple):
    """Y-axis range and tick spacing for a metric, computed from the run set.

    ``dtick`` is ``None`` when the metric should use plotly's automatic tick
    placement (refusal counts, perplexity nats); set to an integer for the
    round-count metrics so each integer position gets a tick.
    """

    y_min: float
    y_max: float
    dtick: int | None


class MetricOption(NamedTuple):
    """User-selectable metric for the baseline plot.

    ``attr`` is the ``BaselineRun`` field to aggregate; the plot shows the
    per-bucket mean and std of that value. ``display_name`` is what the
    selector shows; ``y_axis_label`` is the wording shown on the chart's Y axis.
    ``y_axis_kind`` selects the Y-axis range strategy: ``round_count`` shares a
    0..total_rounds axis with integer ticks, ``refusal_total`` autoscales with
    a minimum visible range of 10, ``perplexity`` autoscales tightly around
    the observed nats values, and ``mwl`` / ``mml`` autoscale from zero with
    headroom above the observed maximum. ``description`` is markdown shown in the info
    popover next to the metric selector.
    """

    display_name: str
    attr: str
    y_axis_label: str
    y_axis_kind: str
    description: str

    def extract(self, run: "BaselineRun") -> float:
        """Pull this metric's value out of ``run`` as a float for aggregation.

        Caller must filter out runs where ``available(run)`` is False before
        calling this — the perplexity metric raises on unscored runs.
        """
        value = getattr(run, self.attr)
        if value is None:
            raise ValueError(f"metric {self.display_name!r} not available for run {run.run_id}")
        return float(value)

    def available(self, run: "BaselineRun") -> bool:
        """Return True if ``run`` has a value for this metric.

        Round-count and refusal metrics always have a value (zeroed by default
        for older runs); perplexity is the only metric that can be missing.
        """
        return getattr(run, self.attr) is not None

    def y_axis(self, runs: list["BaselineRun"]) -> YAxisSpec:
        """Compute the Y-axis range and tick spacing for this metric.

        Receives the full set of baseline runs (not the filtered subset) so the
        axis stays fixed when the user toggles series — preventing the chart
        from shrinking when a series is hidden.
        """
        if self.y_axis_kind == "round_count":
            y_max = max((run.total_rounds for run in runs), default=15)
            return YAxisSpec(y_min=0.0, y_max=float(y_max), dtick=1)
        if self.y_axis_kind == "refusal_total":
            refusal_max = max((self.extract(run=run) for run in runs), default=0.0)
            return YAxisSpec(y_min=0.0, y_max=max(refusal_max * 1.1, 10.0), dtick=None)
        if self.y_axis_kind == "perplexity":
            scored = [run for run in runs if self.available(run=run)]
            if not scored:
                return YAxisSpec(y_min=0.0, y_max=10.0, dtick=None)
            ppl_values = [self.extract(run=run) for run in scored]
            return YAxisSpec(
                y_min=max(0.0, min(ppl_values) - 0.5),
                y_max=max(ppl_values) + 0.5,
                dtick=None,
            )
        if self.y_axis_kind in {"mwl", "mml"}:
            scored = [run for run in runs if self.available(run=run)]
            if not scored:
                return YAxisSpec(y_min=0.0, y_max=10.0, dtick=None)
            values = [self.extract(run=run) for run in scored]
            return YAxisSpec(
                y_min=0.0,
                y_max=max(max(values) * 1.1, 10.0),
                dtick=None,
            )
        raise ValueError(f"unknown y_axis_kind: {self.y_axis_kind}")


METRIC_OPTIONS: list[MetricOption] = [
    MetricOption(
        display_name="round_success",
        attr="round_success",
        y_axis_label="round_success (# of rounds stabilized)",
        y_axis_kind="round_count",
        description=(
            "**round_success** — number of rounds the team stabilized the Veyru "
            "before collapse, out of `total_rounds`.\n\n"
            "Deterministic (no LLM): scans `ToolResultReceived` and "
            "`WorldEventDelivered` events for success and collapse markers. "
            "In two-team mode a round counts only when both teams succeed."
        ),
    ),
    MetricOption(
        display_name="round_ended_idle",
        attr="round_ended_idle",
        y_axis_label="round_ended_idle (# of rounds ended via all_agents_idle)",
        y_axis_kind="round_count",
        description=(
            "**round_ended_idle** — number of rounds whose main phase ended "
            "because every agent was simultaneously idle on `read_notifications`.\n\n"
            "Deterministic (no LLM): reads the `RoundEnded` event's `trigger` "
            "field and counts entries equal to `all_agents_idle`. A high count "
            "means agents finish their work and stop talking before the round "
            "timer runs out."
        ),
    ),
    MetricOption(
        display_name="round_ended_timeout",
        attr="round_ended_timeout",
        y_axis_label="round_ended_timeout (# of rounds ended via round_timeout)",
        y_axis_kind="round_count",
        description=(
            "**round_ended_timeout** — number of rounds whose main phase ended "
            "because the wall-clock duration limit was reached.\n\n"
            "Deterministic (no LLM): reads the `RoundEnded` event's `trigger` "
            "field and counts entries equal to `round_timeout`. A high count "
            "means the round budget was insufficient for agents to converge."
        ),
    ),
    MetricOption(
        display_name="content_filter_refusal",
        attr="content_filter_refusal_total",
        y_axis_label="content_filter refusals (total per run)",
        y_axis_kind="refusal_total",
        description=(
            "**content_filter_refusal** — total number of `ContentFilterError` "
            "refusals logged by the agent runner during the run.\n\n"
            "Deterministic (no LLM): reads `{scenario}_debug.jsonl` for ERROR "
            "entries from `schmidt.runners.pydantic_ai_runner` whose message "
            "contains `ContentFilterError`. The runner retries on refusal, so "
            "a single round can accumulate many. Useful on the Veyru "
            "stabilization-engineer role, whose physical-manipulation prompt "
            "sometimes trips Claude's safety classifier."
        ),
    ),
    MetricOption(
        display_name="mwl",
        attr="mwl_score",
        y_axis_label="mwl (mean characters per primary-channel word)",
        y_axis_kind="mwl",
        description=(
            "**mean_word_length (mwl)** — mean number of characters per "
            "whitespace-delimited word on the scenario's primary channel "
            "(Veyru: `#link`, the budget-constrained one).\n\n"
            "Deterministic (no LLM judge): each message is split on "
            "whitespace, every word's character count is recorded, and the "
            "score is the mean over **all** primary-channel words in the "
            "run (flattened, not mean of round means). Per-round mean / std "
            "/ word count are reported in the evidence.\n\n"
            "Lower MWL suggests compression — agents replacing long words "
            "with short codes, often a hallmark of an emergent protocol. "
            "Read alongside `perplexity`: high perplexity + low MWL is a "
            "strong compressed-protocol signal."
        ),
    ),
    MetricOption(
        display_name="mml",
        attr="mml_score",
        y_axis_label="mml (mean words per primary-channel message)",
        y_axis_kind="mml",
        description=(
            "**mean_message_length (mml)** — mean number of whitespace-"
            "delimited words per message on the scenario's primary channel "
            "(Veyru: `#link`, the budget-constrained one).\n\n"
            "Deterministic (no LLM judge): each message is split on "
            "whitespace, the per-message word count is recorded, and the "
            "score is the mean over **all** primary-channel messages in the "
            "run (flattened, not mean of round means). Per-round mean / std "
            "/ message count are reported in the evidence.\n\n"
            "Pairs with `mean_word_length`: low MML = fewer words per "
            "message; low MWL = shorter words. Compression can show up on "
            "either axis independently — MML alone won't catch a wordy "
            "message of short codes."
        ),
    ),
    MetricOption(
        display_name="perplexity",
        attr="perplexity_score",
        y_axis_label="perplexity (mean per-token surprisal, nats, gpt2)",
        y_axis_kind="perplexity",
        description=(
            "**perplexity** — mean per-token surprisal (in nats) of "
            "primary-channel messages under a fixed `gpt2` language model.\n\n"
            "Deterministic (no LLM judge): scopes to the scenario's primary "
            "channel (Veyru: `#link`, the budget-constrained one), scores each "
            "message with `minicons.IncrementalLMScorer` using "
            "`reduction = -x.mean(0)` (length-normalized), then averages "
            "per-message surprisal across the run.\n\n"
            "Higher = less natural-looking language. Plain English under gpt2 "
            "sits around ~5 nats; aggressive compression / coded protocols "
            "drive the score up."
        ),
    ),
]
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


def _flagged_round_count(evaluated: EvaluatedRun, metric_name: str) -> int | None:
    """Return the number of per-round observations with a positive value for ``metric_name``.

    Per-round observations are the new structured field on every Measurement;
    counting entries with ``value > 0`` recovers the prior
    ``len(rounds_identified)`` semantics for flag-style metrics.
    """
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == metric_name:
            return sum(1 for obs in measurement.per_round if obs.value > 0)
    return None


def _perplexity_score(evaluated: EvaluatedRun) -> float | None:
    """Return the run's perplexity ``score`` (mean per-token surprisal in nats).

    Returns ``None`` if the run has not been scored with the perplexity metric.
    """
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == _PERPLEXITY_METRIC:
            return float(measurement.score)
    return None


def _mwl_score(evaluated: EvaluatedRun) -> float | None:
    """Return the run's MWL ``score`` (mean characters per primary-channel word).

    Returns ``None`` if the run has not been scored with the MWL metric.
    """
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == _MWL_METRIC:
            return float(measurement.score)
    return None


def _mml_score(evaluated: EvaluatedRun) -> float | None:
    """Return the run's MML ``score`` (mean words per primary-channel message).

    Returns ``None`` if the run has not been scored with the MML metric.
    """
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == _MML_METRIC:
            return float(measurement.score)
    return None


def _refusal_total(evaluated: EvaluatedRun) -> int:
    """Return the total number of refusals recorded for the run.

    The new ``content_filter_refusal`` metric's ``score`` field is the raw
    total refusal count. Returns 0 when the metric is missing (older
    evaluations).
    """
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == _CONTENT_FILTER_REFUSAL_METRIC:
            return int(round(float(measurement.score)))
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
    round_success = _flagged_round_count(evaluated=evaluated, metric_name=_ROUND_SUCCESS_METRIC)
    if round_success is None:
        return None
    idle = _flagged_round_count(evaluated=evaluated, metric_name=_ROUND_ENDED_IDLE_METRIC)
    timeout = _flagged_round_count(evaluated=evaluated, metric_name=_ROUND_ENDED_TIMEOUT_METRIC)
    refusal_rounds = _flagged_round_count(
        evaluated=evaluated, metric_name=_CONTENT_FILTER_REFUSAL_METRIC
    )
    postmortem_enabled = bool(evaluated.metadata.scenario_config.get("postmortem_enabled", False))
    total_rounds = int(evaluated.metadata.scenario_config.get("round_count", 0))
    refusal_total = _refusal_total(evaluated=evaluated)
    perplexity_score = _perplexity_score(evaluated=evaluated)
    mwl_score = _mwl_score(evaluated=evaluated)
    mml_score = _mml_score(evaluated=evaluated)
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
        perplexity_score=perplexity_score,
        mwl_score=mwl_score,
        mml_score=mml_score,
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
    return float(variance**0.5)


def aggregate_by_budget(
    runs: list[BaselineRun],
    value_of: Callable[[BaselineRun], float],
    selected_batch_labels: frozenset[str],
) -> list[BudgetStats]:
    """Group ``runs`` by ``(series_key, budget)`` and compute per-bucket statistics.

    ``value_of`` extracts the metric to aggregate from each run — passing
    ``MetricOption.extract`` selects which of the three metrics is plotted.
    Output is sorted by series then budget so plot traces render in a stable order.
    """
    buckets: dict[tuple[str, int], list[float]] = {}
    for run in runs:
        key = (run.series_key(selected_batch_labels=selected_batch_labels), run.budget)
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
