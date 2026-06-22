"""Per-run records for the Container-yard budget tab.

Each ``ContainerYardBudgetRun`` carries the run's overall ``round_success``
fraction, its budget (``round_time_budget_seconds``), and — for a pair of
user-chosen focus rounds — the per-round success flag plus the first few
link-channel messages of that round. The tab uses the first piece to plot
how round success moves with the communication budget, and the second to
show side-by-side how the emergent protocol differs across budgets at the
same point in the run.

This module is streamlit-free so it can be reused by ad-hoc analysis scripts.
"""

from pathlib import Path
from typing import NamedTuple

import orjson

from analysis.results_viewer.measurement_scores import ROUND_SUCCESS_METRIC, round_success_score
from analysis.results_viewer.run_catalog import EvaluatedRun

CONTAINER_YARD_SCENARIO = "container_yard_stacking"
LINK_CHANNEL_ID = "link"
_FIRST_N_MESSAGES = 3


class LinkMessage(NamedTuple):
    """One link-channel message: sender role and verbatim transmitted text."""

    sender: str
    text: str


class FocusRound(NamedTuple):
    """A round's success flag and its first few link messages for one run."""

    round_number: int
    succeeded: bool | None
    first_messages: list[LinkMessage]


class ContainerYardBudgetRun(NamedTuple):
    """One container-yard run's budget / success / focus-round record."""

    run_id: str
    run_dir: Path
    model: str
    budget: int
    success_fraction: float
    focus_rounds: list[FocusRound]


class _MessageCacheKey(NamedTuple):
    """Identity tuple for a run JSONL used to memoize its parsed link messages."""

    size: int
    mtime_ns: int


_LINK_MESSAGE_CACHE: dict[Path, tuple[_MessageCacheKey, dict[int, list[LinkMessage]]]] = {}


def _resolve_budget(evaluated: EvaluatedRun) -> int | None:
    """Resolve the run's per-round communication budget from scenario_config."""
    value = evaluated.metadata.scenario_config.get("round_time_budget_seconds")
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _per_round_success(evaluated: EvaluatedRun) -> dict[int, bool]:
    """Map round_number to its success flag from the run's ``round_success`` measurement."""
    out: dict[int, bool] = {}
    for measurement in evaluated.report.measurements:
        if measurement.metric_name != ROUND_SUCCESS_METRIC:
            continue
        for obs in measurement.per_round:
            out[int(obs.round_number)] = float(obs.value) >= 0.5
        break
    return out


def _jsonl_path(evaluated: EvaluatedRun) -> Path:
    """Return the path to the run's canonical JSONL event log."""
    return evaluated.run_dir / f"{evaluated.scenario_name}.jsonl"


def _read_link_messages_by_round(jsonl_path: Path) -> dict[int, list[LinkMessage]]:
    """Parse all link-channel messages from a run JSONL, grouped by round.

    Memoized on the JSONL's ``(size, mtime_ns)`` so repeated Streamlit reruns
    over a finished run only pay the parse cost once.
    """
    try:
        stat = jsonl_path.stat()
    except FileNotFoundError:
        return {}
    cache_key = _MessageCacheKey(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
    cached = _LINK_MESSAGE_CACHE.get(jsonl_path)
    if cached is not None and cached[0] == cache_key:
        return cached[1]
    by_round: dict[int, list[LinkMessage]] = {}
    with jsonl_path.open("rb") as f:
        for line in f:
            event = orjson.loads(line)
            if event.get("event_type") != "message_sent":
                continue
            message = event.get("message") or {}
            if message.get("channel_id") != LINK_CHANNEL_ID:
                continue
            round_number = message.get("round_number")
            if not isinstance(round_number, int):
                continue
            by_round.setdefault(round_number, []).append(
                LinkMessage(
                    sender=str(message.get("sender_agent_id", "unknown")),
                    text=str(message.get("text", "")),
                )
            )
    _LINK_MESSAGE_CACHE[jsonl_path] = (cache_key, by_round)
    return by_round


def _build_focus_rounds(
    evaluated: EvaluatedRun,
    focus_round_numbers: list[int],
) -> list[FocusRound]:
    """Build the per-focus-round success + first-messages records for one run."""
    per_round_success = _per_round_success(evaluated=evaluated)
    messages_by_round = _read_link_messages_by_round(jsonl_path=_jsonl_path(evaluated=evaluated))
    out: list[FocusRound] = []
    for round_number in focus_round_numbers:
        out.append(
            FocusRound(
                round_number=round_number,
                succeeded=per_round_success.get(round_number),
                first_messages=messages_by_round.get(round_number, [])[:_FIRST_N_MESSAGES],
            )
        )
    return out


def build_container_yard_budget_run(
    evaluated: EvaluatedRun,
    focus_round_numbers: list[int],
) -> ContainerYardBudgetRun | None:
    """Convert an ``EvaluatedRun`` into a budget record, or ``None`` if it doesn't qualify.

    A run qualifies when it is a container-yard run with a single-team
    ``round_success`` measurement and a resolvable ``round_time_budget_seconds``.
    """
    if evaluated.scenario_name != CONTAINER_YARD_SCENARIO:
        return None
    success_fraction = round_success_score(evaluated=evaluated)
    if success_fraction is None:
        return None
    budget = _resolve_budget(evaluated=evaluated)
    if budget is None:
        return None
    return ContainerYardBudgetRun(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        model=evaluated.metadata.primary_model,
        budget=budget,
        success_fraction=success_fraction,
        focus_rounds=_build_focus_rounds(
            evaluated=evaluated, focus_round_numbers=focus_round_numbers
        ),
    )


def list_container_yard_budget_runs(
    evaluated_runs: list[EvaluatedRun],
    focus_round_numbers: list[int],
) -> list[ContainerYardBudgetRun]:
    """Build budget records for every qualifying container-yard run."""
    out: list[ContainerYardBudgetRun] = []
    for evaluated in evaluated_runs:
        record = build_container_yard_budget_run(
            evaluated=evaluated, focus_round_numbers=focus_round_numbers
        )
        if record is not None:
            out.append(record)
    return out
