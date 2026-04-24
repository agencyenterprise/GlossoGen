"""Evaluator that flags content-filter refusals encountered during the simulation.

A refusal is a ``pydantic_ai.exceptions.ContentFilterError`` raised when the
underlying provider (currently most visible on Anthropic's Claude) returns a
``finish_reason`` of ``"refusal"`` / ``"content_filter"``. The runner's
cycle-retry loop catches these and re-prompts the agent, so simulations
usually still make progress, but each refusal wastes an agent cycle and
signals the safety classifier reacting to something in the prompt.

This evaluator is scenario-agnostic: it reads the Python logger's JSONL debug
log (``{scenario}_debug.jsonl``) because refusals are not currently emitted as
first-class simulation events. Each debug-log ERROR entry whose message
contains ``ContentFilterError`` is one refusal; timestamps are correlated with
``RoundAdvanced`` events to bucket refusals by round.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import orjson

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import RoundAdvanced, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_REFUSAL_MARKER = "ContentFilterError"
_RUNNER_LOGGER_NAME = "schmidt.runners.pydantic_ai_runner"
_AGENT_CYCLE_RE = re.compile(r"Agent (\S+) run cycle (\d+) failed")


class _Refusal(NamedTuple):
    """One content-filter refusal entry extracted from the debug log."""

    timestamp: datetime
    agent_id: str


def _parse_timestamp(raw: str) -> datetime | None:
    """Parse an ISO-8601 timestamp from a debug log entry, tolerating ``Z`` suffix."""
    if not isinstance(raw, str) or not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        logger.exception("Failed to parse debug-log timestamp: %r", raw)
        return None


def _read_refusals(debug_log_path: Path) -> list[_Refusal]:
    """Scan the debug log for runner ERROR entries containing a ContentFilterError."""
    if not debug_log_path.exists():
        return []
    refusals: list[_Refusal] = []
    for raw_line in debug_log_path.read_bytes().splitlines():
        if not raw_line:
            continue
        try:
            entry = orjson.loads(raw_line)
        except orjson.JSONDecodeError:
            logger.exception("Skipping malformed debug-log line: %r", raw_line[:200])
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("logger") != _RUNNER_LOGGER_NAME:
            continue
        if entry.get("level") != "ERROR":
            continue
        message = entry.get("message") or ""
        if _REFUSAL_MARKER not in message:
            continue
        match = _AGENT_CYCLE_RE.search(message)
        if match is None:
            continue
        timestamp = _parse_timestamp(raw=entry.get("timestamp", ""))
        if timestamp is None:
            continue
        refusals.append(_Refusal(timestamp=timestamp, agent_id=match.group(1)))
    return refusals


class _RoundWindow(NamedTuple):
    """Time window ``[start, end)`` associated with a round number."""

    round_number: int
    start: datetime
    end: datetime


def _build_round_windows(events: list[SimulationEvent]) -> list[_RoundWindow]:
    """Convert ``RoundAdvanced`` events into ``(round_number, start, end)`` windows.

    Each round's window runs from its own ``RoundAdvanced`` timestamp to the
    next round's ``RoundAdvanced`` (or ``datetime.max`` for the final round).
    """
    advances: list[tuple[int, datetime]] = []
    for event in events:
        if not isinstance(event, RoundAdvanced):
            continue
        advances.append((event.round_number, event.timestamp))
    advances.sort(key=lambda pair: pair[1])
    windows: list[_RoundWindow] = []
    for index, (round_number, start) in enumerate(advances):
        if index + 1 < len(advances):
            end = advances[index + 1][1]
        else:
            end = datetime.max.replace(tzinfo=timezone.utc)
        windows.append(_RoundWindow(round_number=round_number, start=start, end=end))
    return windows


def _round_for(timestamp: datetime, windows: list[_RoundWindow]) -> int | None:
    """Return the round number whose window contains ``timestamp``, or ``None``."""
    for window in windows:
        if window.start <= timestamp < window.end:
            return window.round_number
    return None


class _Aggregate(NamedTuple):
    """Per-run refusal summary after bucketing by round and agent."""

    total: int
    rounds_with_refusal: list[int]
    per_agent_counts: dict[str, int]


def _aggregate(
    refusals: list[_Refusal],
    windows: list[_RoundWindow],
    agent_configs: list[AgentConfig],
) -> _Aggregate:
    """Bucket refusals by round and agent to produce the summary."""
    rounds: set[int] = set()
    per_agent_counts: dict[str, int] = {config.agent_id: 0 for config in agent_configs}
    for refusal in refusals:
        round_number = _round_for(timestamp=refusal.timestamp, windows=windows)
        if round_number is not None:
            rounds.add(round_number)
        if refusal.agent_id not in per_agent_counts:
            per_agent_counts[refusal.agent_id] = 0
        per_agent_counts[refusal.agent_id] += 1
    return _Aggregate(
        total=len(refusals),
        rounds_with_refusal=sorted(rounds),
        per_agent_counts=per_agent_counts,
    )


class ContentFilterRefusalEvaluator(Evaluator):
    """Flags rounds where the agent LLM returned a content-filter refusal.

    The score is the total number of refusals normalized by the total number
    of rounds in the run, so it is directly comparable across different
    ``round_count`` settings. The verdict is PASS when no refusals were seen,
    PARTIAL otherwise (the runner's retry loop typically absorbs refusals, so
    a completed run with refusals has degraded but non-fatal outcomes).
    """

    name = "content_filter_refusal"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Count content-filter refusals from the debug log."""
        _ = llm_provider
        scenario_name = scenario.name()
        debug_log_path = run_dir / f"{scenario_name}_debug.jsonl"
        refusals = _read_refusals(debug_log_path=debug_log_path)
        windows = _build_round_windows(events=events)
        summary = _aggregate(refusals=refusals, windows=windows, agent_configs=agent_configs)

        total_rounds = len(windows)
        if total_rounds > 0:
            score = summary.total / total_rounds
        else:
            score = 0.0
        if summary.total == 0:
            verdict = Verdict.PASS
        else:
            verdict = Verdict.PARTIAL

        evidence: list[str] = []
        evidence.append(
            f"{summary.total} content-filter refusals across "
            f"{len(summary.rounds_with_refusal)}/{total_rounds} rounds."
        )
        for agent_id, count in sorted(summary.per_agent_counts.items()):
            if count > 0:
                evidence.append(f"  {agent_id}: {count} refusals")
        if not debug_log_path.exists():
            evidence.append(
                "Debug log not present at "
                f"{debug_log_path} — cannot detect refusals for this run."
            )

        per_agent: dict[str, Verdict] = {}
        for agent_id, count in summary.per_agent_counts.items():
            per_agent[agent_id] = Verdict.PASS if count == 0 else Verdict.PARTIAL

        logger.info(
            "content_filter_refusal: total=%d rounds_affected=%d score=%.3f verdict=%s",
            summary.total,
            len(summary.rounds_with_refusal),
            score,
            verdict.value,
        )
        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent=per_agent,
            rounds_identified=summary.rounds_with_refusal,
        )
