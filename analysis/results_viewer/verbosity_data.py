"""Per-run records for the Verbosity tab's success-rate scatter.

Each ``VerbosityRun`` pairs a single language metric (MCR / MCM / perplexity)
with the run's success fraction. Baseline runs use the run-wide
``round_success`` score; resume runs use ``round_success_after_resume`` so
the success-fraction is on the same scope as the language metrics, which are
computed only over post-resume messages.

This module is streamlit-free so it can be reused by ad-hoc analysis scripts.
"""

from pathlib import Path
from typing import NamedTuple

import orjson

from analysis.results_viewer.measurement_scores import (
    MCM_METRIC,
    MCR_METRIC,
    PERPLEXITY_METRIC,
    ROUND_SUCCESS_METRIC,
    mcm_score,
    mcr_score,
    perplexity_score,
    read_labels,
    round_success_after_resume_score,
    round_success_score,
)
from analysis.results_viewer.run_catalog import EvaluatedRun

_BASELINE_LABEL = "baseline"
_RESUME_LABEL = "resume"
_TWO_TEAM_METRIC_NAMES = frozenset({"round_success_team_a", "round_success_team_b"})


class RoundValue(NamedTuple):
    """A single per-round metric reading."""

    round_number: int
    value: float


class VerbosityRun(NamedTuple):
    """One run's verbosity-vs-success data point."""

    run_id: str
    run_dir: Path
    model: str
    postmortem_enabled: bool
    is_resume: bool
    budget: int | None
    success_fraction: float
    mcr_score: float | None
    mcm_score: float | None
    perplexity_score: float | None
    per_round_by_metric: dict[str, list[RoundValue]]
    labels: list[str]

    def series_key(self) -> str:
        """Stable identifier for plot grouping; one trace per (model, postmortem, kind)."""
        suffix = "postmortem" if self.postmortem_enabled else "no-postmortem"
        kind = "resume" if self.is_resume else "baseline"
        return f"{self.model} · {suffix} · {kind}"


class VerbosityMetricOption(NamedTuple):
    """User-selectable language metric for the verbosity scatter X axis."""

    display_name: str
    attr: str
    x_axis_label: str
    description: str


_DISPLAY_NAME_TO_METRIC = {
    "mcr": MCR_METRIC,
    "mcm": MCM_METRIC,
    "perplexity": PERPLEXITY_METRIC,
}


VERBOSITY_METRIC_OPTIONS: list[VerbosityMetricOption] = [
    VerbosityMetricOption(
        display_name="mcr",
        attr="mcr_score",
        x_axis_label="mcr (mean characters per round on primary channel)",
        description=(
            "**mean_chars_per_round (mcr)** — total characters of all "
            "primary-channel messages summed per round, then averaged "
            "across rounds. The headline channel-utilization number — "
            "in Veyru it maps directly to `time_budget_seconds` since "
            "one character costs one second of communication time.\n\n"
            "Lower MCR = teams talk less per round overall."
        ),
    ),
    VerbosityMetricOption(
        display_name="mcm",
        attr="mcm_score",
        x_axis_label="mcm (mean characters per primary-channel message)",
        description=(
            "**mean_chars_per_message (mcm)** — characters per "
            "primary-channel message, averaged across all messages. "
            "Normalizes MCR by message count: rounds that need more "
            "back-and-forth no longer inflate the score, so MCM "
            "isolates per-message verbosity from message density.\n\n"
            "Lower MCM = each message carries fewer characters, "
            "regardless of how many messages the round needed."
        ),
    ),
    VerbosityMetricOption(
        display_name="perplexity",
        attr="perplexity_score",
        x_axis_label="perplexity (mean per-token surprisal, nats, gpt2)",
        description=(
            "**perplexity** — mean per-token surprisal (in nats) of "
            "primary-channel messages under a fixed `gpt2` language model.\n\n"
            "Higher = less natural-looking language. Plain English under "
            "gpt2 sits around ~5 nats; aggressive compression / coded "
            "protocols drive the score up."
        ),
    ),
]


def build_verbosity_run(evaluated: EvaluatedRun) -> VerbosityRun | None:
    """Convert an ``EvaluatedRun`` into a ``VerbosityRun`` if it qualifies.

    A run qualifies when it has the ``baseline`` or ``resume`` label, is not
    a two-team run, and carries the matching success measurement. Resume
    runs use ``round_success_after_resume``; baseline runs use
    ``round_success``.
    """
    labels = read_labels(run_dir=evaluated.run_dir)
    is_baseline = _BASELINE_LABEL in labels
    is_resume = _RESUME_LABEL in labels
    if not is_baseline and not is_resume:
        return None
    if _is_two_team(evaluated=evaluated):
        return None
    if is_resume:
        success_fraction = round_success_after_resume_score(evaluated=evaluated)
    else:
        success_fraction = round_success_score(evaluated=evaluated)
    if success_fraction is None:
        return None
    postmortem_enabled = bool(evaluated.metadata.scenario_config.get("postmortem_enabled", False))
    budget = _resolve_budget(evaluated=evaluated)
    return VerbosityRun(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        model=evaluated.metadata.primary_model,
        postmortem_enabled=postmortem_enabled,
        is_resume=is_resume,
        budget=budget,
        success_fraction=success_fraction,
        mcr_score=mcr_score(evaluated=evaluated),
        mcm_score=mcm_score(evaluated=evaluated),
        perplexity_score=perplexity_score(evaluated=evaluated),
        per_round_by_metric=_collect_per_round(evaluated=evaluated),
        labels=labels,
    )


def _collect_per_round(evaluated: EvaluatedRun) -> dict[str, list[RoundValue]]:
    """Build per-round value lists for each verbosity metric on a run.

    Keyed by the streamlit display name (``mcr`` / ``perplexity``) so the tab
    can look up by ``MetricOption.display_name``.
    Missing metrics yield an empty list rather than absent keys.
    """
    by_name: dict[str, list[RoundValue]] = {display: [] for display in _DISPLAY_NAME_TO_METRIC}
    for measurement in evaluated.report.measurements:
        for display, metric_name in _DISPLAY_NAME_TO_METRIC.items():
            if measurement.metric_name == metric_name:
                by_name[display] = [
                    RoundValue(round_number=int(obs.round_number), value=float(obs.value))
                    for obs in measurement.per_round
                ]
                break
    return by_name


def list_verbosity_runs(evaluated_runs: list[EvaluatedRun]) -> list[VerbosityRun]:
    """Filter ``evaluated_runs`` to baseline and resume runs with success scores."""
    out: list[VerbosityRun] = []
    for run in evaluated_runs:
        verbosity = build_verbosity_run(evaluated=run)
        if verbosity is not None:
            out.append(verbosity)
    return out


def _resolve_budget(evaluated: EvaluatedRun) -> int | None:
    """Resolve the run's character/time budget from its event log.

    Reads the first ``veyru_case_started`` event in the run's JSONL and
    returns its ``time_budget_seconds``. Veyru's character budget equals its
    time budget (one char = one second), and the budget stays constant
    across cases within a run. Works for both baseline and resume runs since
    resumed runs emit case-started events on every round_advanced. Returns
    ``None`` when no case-started event exists (e.g. a run that crashed
    before round 1).
    """
    scenario_name = evaluated.run_id.split("/", 1)[0]
    jsonl_path = evaluated.run_dir / f"{scenario_name}.jsonl"
    if not jsonl_path.exists():
        return None
    with jsonl_path.open("rb") as f:
        for line in f:
            event = orjson.loads(line)
            if event.get("event_type") != "veyru_case_started":
                continue
            value = event.get("time_budget_seconds")
            if isinstance(value, (int, float)):
                return int(value)
            return None
    return None


def _is_two_team(evaluated: EvaluatedRun) -> bool:
    """Detect two-team runs by the presence of per-team round_success measurements.

    Two-team runs emit ``round_success_team_a`` / ``round_success_team_b``
    instead of (or in addition to) the single-team ``round_success``. The
    verbosity tab plots one point per run, so two-team data would muddle the
    cloud — those runs are skipped entirely.
    """
    names = {m.metric_name for m in evaluated.report.measurements}
    if names & _TWO_TEAM_METRIC_NAMES:
        return True
    return ROUND_SUCCESS_METRIC not in names and bool(_TWO_TEAM_METRIC_NAMES & names)
