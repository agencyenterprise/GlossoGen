"""Extracts scenario-event markers (swap, intern, collapse, stabilize) from a run log."""

from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple

import orjson

from schmidt.scenarios.veyru.ids import (
    INTERN_JOIN_REASON,
    INTERN_TAKEOVER_REASON,
    OBSERVER_SWAP_REASON,
    VEYRU_COLLAPSED_MARKER,
    VEYRU_STABILIZED_MARKER,
)


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


def _scan_jsonl(jsonl_path: Path) -> tuple[dict[str, Any], int, list[TimelineEvent]]:
    """Single-pass scan over a run's JSONL file, returning config + events."""
    scenario_config: dict[str, Any] = {}
    total_rounds = 0
    events: list[TimelineEvent] = []
    collapsed_rounds: set[int] = set()
    stabilized_rounds: set[int] = set()
    postmortem_closed_rounds: set[int] = set()

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
            elif event_type == "world_event_delivered":
                text = raw.get("text") or ""
                rnd = int(raw.get("round_number", 0))
                if VEYRU_COLLAPSED_MARKER in text:
                    collapsed_rounds.add(rnd)
                elif VEYRU_STABILIZED_MARKER in text:
                    stabilized_rounds.add(rnd)
            elif event_type == "channel_history_cleared":
                reason = raw.get("reason") or ""
                rnd = int(raw.get("round_number", 0))
                if reason in {OBSERVER_SWAP_REASON, INTERN_TAKEOVER_REASON}:
                    postmortem_closed_rounds.add(rnd)

    for rnd in sorted(collapsed_rounds):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.COLLAPSE,
                round_number=rnd,
                label="Veyru collapsed",
            )
        )
    for rnd in sorted(stabilized_rounds):
        events.append(
            TimelineEvent(
                kind=TimelineEventKind.STABILIZED,
                round_number=rnd,
                label="Veyru stabilized",
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
                label=f"Observer swap (round {swap_round})",
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
    # rely on INTERN_JOIN_REASON elsewhere; keep the constant import stable.
    _ = INTERN_JOIN_REASON
    return events


def load_run_timeline(run_dir: Path) -> RunTimeline:
    """Read a run's JSONL once and return everything the timeline chart needs."""
    jsonl_path = run_dir / "veyru.jsonl"
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
