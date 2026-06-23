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

from analysis.results_viewer.measurement_scores import (
    LANGUAGE_REPETITION_METRIC,
    MCM_METRIC,
    MCR_METRIC,
    PERPLEXITY_METRIC,
    ROUND_SUCCESS_METRIC,
    language_repetition_score,
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
_CHANNEL_NOISE_LABEL = "channel_noise"
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
    kind: str
    noise_level: float
    budget: int | None
    success_fraction: float
    mcr_score: float | None
    mcm_score: float | None
    perplexity_score: float | None
    repetition_score: float | None
    per_round_by_metric: dict[str, list[RoundValue]]
    labels: list[str]

    def series_key(self) -> str:
        """Stable identifier for plot grouping; one trace per (model, postmortem, kind)."""
        suffix = "postmortem" if self.postmortem_enabled else "no-postmortem"
        return f"{self.model} · {suffix} · {self.kind}"


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
    "repetition": LANGUAGE_REPETITION_METRIC,
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
            "in scenarios where one character on the primary channel costs "
            "one second of a per-round communication budget (Veyru, "
            "container_yard_stacking), MCR maps directly to "
            "`round_time_budget_seconds`.\n\n"
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
    VerbosityMetricOption(
        display_name="repetition",
        attr="repetition_score",
        x_axis_label="repetition (mean encodings per information unit, x)",
        description=(
            "**language_repetition** — an LLM judge counts, per round, the "
            "distinct pieces of information conveyed on the primary channel and "
            "the total number of encodings of them; the redundancy factor is "
            "`total_encodings / distinct_units` (1.0 = each thing said once, "
            "2.0 = twice, 3.0 = three times). Scored on the pristine text the "
            "agent composed, before channel noise.\n\n"
            "Higher = agents re-encode the same information more times to "
            "survive character loss (repeated tokens, digit+word dual-encoding, "
            "abbreviation+expansion)."
        ),
    ),
]


def build_verbosity_run(evaluated: EvaluatedRun) -> VerbosityRun | None:
    """Convert an ``EvaluatedRun`` into a ``VerbosityRun`` if it qualifies.

    A run qualifies when it has the ``baseline``, ``resume``, or
    ``channel_noise`` label, is not a two-team run, and carries the matching
    success measurement. Resume runs use ``round_success_after_resume``;
    baseline and channel_noise runs use ``round_success``.
    """
    labels = read_labels(run_dir=evaluated.run_dir)
    is_baseline = _BASELINE_LABEL in labels
    is_resume = _RESUME_LABEL in labels
    is_channel_noise = _CHANNEL_NOISE_LABEL in labels
    if not is_baseline and not is_resume and not is_channel_noise:
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
        kind=_resolve_kind(is_resume=is_resume, is_channel_noise=is_channel_noise),
        noise_level=_resolve_noise_level(evaluated=evaluated),
        budget=budget,
        success_fraction=success_fraction,
        mcr_score=mcr_score(evaluated=evaluated),
        mcm_score=mcm_score(evaluated=evaluated),
        perplexity_score=perplexity_score(evaluated=evaluated),
        repetition_score=language_repetition_score(evaluated=evaluated),
        per_round_by_metric=_collect_per_round(evaluated=evaluated),
        labels=labels,
    )


def _resolve_kind(is_resume: bool, is_channel_noise: bool) -> str:
    """Pick the display/grouping kind for a run.

    ``resume`` takes precedence (it changes the success-metric scope);
    ``channel_noise`` runs are otherwise tagged as their own kind so they
    can be toggled separately from clean baselines.
    """
    if is_resume:
        return "resume"
    if is_channel_noise:
        return "channel_noise"
    return "baseline"


def _resolve_noise_level(evaluated: EvaluatedRun) -> float:
    """Return the run's applied link-channel noise level from scenario_config.

    Defaults to ``0.0`` (no noise) when the knob is absent, so every run —
    including clean baselines — carries a comparable value for the
    channel-noise filter.
    """
    value = evaluated.metadata.scenario_config.get("channel_noise_level")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


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


def list_verbosity_runs(
    evaluated_runs: list[EvaluatedRun], scenario_name: str
) -> list[VerbosityRun]:
    """Filter ``evaluated_runs`` to ``scenario_name`` baseline / resume runs with success scores."""
    out: list[VerbosityRun] = []
    for run in evaluated_runs:
        if run.scenario_name != scenario_name:
            continue
        verbosity = build_verbosity_run(evaluated=run)
        if verbosity is not None:
            out.append(verbosity)
    return out


def _resolve_budget(evaluated: EvaluatedRun) -> int | None:
    """Resolve the run's per-round communication budget from scenario_config.

    Scenarios with a per-round budget carry ``round_time_budget_seconds``
    in the ``scenario_config`` written into the JSONL at simulation
    start; one character on the primary channel costs one second against
    that budget. Returns ``None`` when the scenario has no per-round
    budget (e.g. Salon).
    """
    value = evaluated.metadata.scenario_config.get("round_time_budget_seconds")
    if isinstance(value, (int, float)):
        return int(value)
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
