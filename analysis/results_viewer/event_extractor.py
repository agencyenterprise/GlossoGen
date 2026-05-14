"""Extracts scenario-event markers (swap, intern, success/failure) from a run log.

Scenario-agnostic: reads platform-level events (``round_result_recorded``,
``agent_swapped_mid_run``, ``channel_history_cleared``) plus the knob-driven
boundary anchors from ``simulation_started.scenario_config``. Works for any
scenario that opts into ``judge_round_result``.
"""

from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple

import orjson


class TimelineEventKind(StrEnum):
    """Discrete scenario-event categories rendered on a timeline."""

    SWAP = "swap"
    INTERN_JOIN = "intern_join"
    INTERN_TAKEOVER = "intern_takeover"
    COLLAPSE = "collapse"
    STABILIZED = "stabilized"
    POSTMORTEM_CLOSED = "postmortem_closed"


class TimelineEvent(NamedTuple):
    """A single timeline marker pinned to a round."""

    kind: TimelineEventKind
    round_number: int
    label: str


class RunTimeline(NamedTuple):
    """Everything a timeline chart needs for one run."""

    run_id: str
    run_dir: str
    scenario_config: dict[str, Any]
    total_rounds: int
    events: list[TimelineEvent]


_NON_TERMINAL_ROUND_END_TRIGGERS = {"all_agents_idle", "round_timeout"}


def _scan_jsonl(jsonl_path: Path) -> tuple[dict[str, Any], int, list[TimelineEvent]]:
    """Single-pass scan over a run's JSONL file, returning config + events."""
    scenario_config: dict[str, Any] = {}
    total_rounds = 0
    events: list[TimelineEvent] = []
    collapsed_rounds: set[int] = set()
    stabilized_rounds: set[int] = set()
    postmortem_closed_rounds: set[int] = set()
    scheduled_swap_rounds: list[tuple[int, str]] = []
    non_terminal_ended_rounds: set[int] = set()
    round_results: dict[int, list[bool]] = {}

    with jsonl_path.open("rb") as f:
        for line in f:
            raw = orjson.loads(line)
            event_type = raw.get("event_type")
            if event_type == "simulation_started":
                scenario_config = raw.get("scenario_config") or {}
            elif event_type == "round_advanced":
                rnd = int(raw.get("round_number", 0))
                if rnd > total_rounds:
                    total_rounds = rnd
            elif event_type == "round_ended":
                trigger = raw.get("trigger") or ""
                rnd = int(raw.get("round_number", 0))
                if trigger in _NON_TERMINAL_ROUND_END_TRIGGERS:
                    non_terminal_ended_rounds.add(rnd)
            elif event_type == "round_result_recorded":
                rnd = int(raw.get("round_number", 0))
                round_results.setdefault(rnd, []).append(bool(raw.get("success", False)))
            elif event_type == "agent_swapped_mid_run":
                rnd = int(raw.get("round_number", 0))
                agent_id = str(raw.get("agent_id") or "")
                scheduled_swap_rounds.append((rnd, agent_id))
            elif event_type == "channel_history_cleared":
                rnd = int(raw.get("round_number", 0))
                postmortem_closed_rounds.add(rnd)

    # Multi-team rounds emit one event per team. A round counts as
    # stabilized only when every team succeeded; otherwise it's a
    # collapse. This matches the "joint success" semantic the platform
    # `round_success` metric uses for the per-round observation.
    for rnd, successes in round_results.items():
        if successes and all(successes):
            stabilized_rounds.add(rnd)
        else:
            collapsed_rounds.add(rnd)

    # Older runs (predating `round_result_recorded`) can still surface
    # implicit collapses from rounds that ended via all_agents_idle /
    # round_timeout without a corresponding result. New runs hit the
    # `round_results` branch above and never need this fallback.
    inferred_collapsed = non_terminal_ended_rounds - collapsed_rounds - stabilized_rounds
    collapsed_rounds.update(inferred_collapsed)

    for rnd in sorted(collapsed_rounds):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.COLLAPSE,
                round_number=rnd,
                label="Round failed",
            )
        )
    for rnd in sorted(stabilized_rounds):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.STABILIZED,
                round_number=rnd,
                label="Round succeeded",
            )
        )
    for rnd in sorted(postmortem_closed_rounds):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.POSTMORTEM_CLOSED,
                round_number=rnd,
                label="Postmortem closed",
            )
        )
    for rnd, agent_id in sorted(scheduled_swap_rounds):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.SWAP,
                round_number=rnd,
                label=f"Scheduled swap ({agent_id})",
            )
        )
    return scenario_config, total_rounds, events


def _config_events(scenario_config: dict[str, Any]) -> list[TimelineEvent]:
    """Anchor events pulled directly from scenario_config (swap/intern rounds)."""
    events: list[TimelineEvent] = []
    swap_round = scenario_config.get("swap_round")
    if isinstance(swap_round, int):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.SWAP,
                round_number=swap_round,
                label=f"Two-team swap (round {swap_round})",
            )
        )
    intern_join_round = scenario_config.get("intern_join_round")
    if isinstance(intern_join_round, int):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.INTERN_JOIN,
                round_number=intern_join_round,
                label=f"Intern joined (round {intern_join_round})",
            )
        )
    intern_takeover_round = scenario_config.get("intern_takeover_round")
    if isinstance(intern_takeover_round, int):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.INTERN_TAKEOVER,
                round_number=intern_takeover_round,
                label=f"Intern takeover (round {intern_takeover_round})",
            )
        )
    return events


def load_run_timeline(run_dir: Path, scenario_name: str) -> RunTimeline:
    """Read a run's JSONL once and return everything the timeline chart needs."""
    jsonl_path = run_dir / f"{scenario_name}.jsonl"
    scenario_config, total_rounds, events = _scan_jsonl(jsonl_path=jsonl_path)
    events.extend(_config_events(scenario_config=scenario_config))
    events.sort(key=lambda e: (e.round_number, e.kind.value))
    run_id = f"{run_dir.parent.name}/{run_dir.name}"
    return RunTimeline(
        run_id=run_id,
        run_dir=str(run_dir),
        scenario_config=scenario_config,
        total_rounds=total_rounds,
        events=events,
    )
