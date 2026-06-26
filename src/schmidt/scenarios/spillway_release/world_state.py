"""Round outcome type and the deterministic round-resolution rule.

``SpillwayOutcome`` is the immutable record of one finished round.
``resolve_round`` is the pure function the world calls at round end to
compute every success clause from the round's case and the agents' actions:
the gate setting the dam operator committed, whether the park ranger secured
the park, and whether civil defense ordered an evacuation. Keeping the rule
in a pure function makes it independently testable.
"""

from typing import NamedTuple

from schmidt.scenarios.spillway_release.spillway_cases import SpillwayCase


class SpillwayOutcome(NamedTuple):
    """Result of a single spillway case after a round completes."""

    case_number: int
    current_time_hours: float
    start_level: int
    inflow: int
    end_level: float
    gates_opened: int
    release_duration_hours: float
    release_total: float
    park_opens_at_hours: float | None
    park_lockable: bool
    park_secured: bool
    evacuated: bool
    would_overlap: bool
    clearing_was_needed: bool
    budget_exceeded: bool
    characters_used: int
    round_time_budget_seconds: int
    dam_ok: bool
    casualties: bool
    needless_closure: bool
    false_alarm: bool
    round_succeeded: bool
    failure_reason: str


def _park_is_occupied(case: SpillwayCase) -> bool:
    """Whether the park is open for visitors at any point in the operating day."""
    if case.park_opens_at_hours is None:
        return False
    return case.park_opens_at_hours < case.day_end_hours


def _failure_reason(
    budget_exceeded: bool,
    end_level: float,
    case: SpillwayCase,
    casualties: bool,
    false_alarm: bool,
    needless_closure: bool,
) -> str:
    """Return the first failing clause's human-readable reason, or '' on success."""
    if budget_exceeded:
        return "Communication budget exhausted."
    if end_level > case.max_level:
        return (
            f"Dam collapsed: reservoir reached {end_level:.0f}% "
            f"(collapse threshold {case.max_level}%)."
        )
    if end_level < case.min_level:
        return (
            f"Reservoir drained below the minimum supply level: {end_level:.0f}% "
            f"(minimum {case.min_level}%)."
        )
    if casualties:
        return "Dangerous release sent over an occupied park with no closure or evacuation."
    if false_alarm:
        return (
            "Unnecessary evacuation ordered (no warranted release over an occupied park, "
            "or the park could have been closed instead)."
        )
    if needless_closure:
        return "Park needlessly closed when no release would have endangered it."
    return ""


def resolve_round(
    case: SpillwayCase,
    gates_opened: int,
    release_duration_hours: float,
    park_secured: bool,
    evacuated: bool,
    characters_used: int,
    budget_exceeded: bool,
) -> SpillwayOutcome:
    """Compute the full per-clause outcome for one finished round."""
    has_release = gates_opened > 0 and release_duration_hours > 0
    if has_release:
        release_total = float(
            gates_opened * case.release_per_gate_per_hour * release_duration_hours
        )
        window_end = case.current_time_hours + release_duration_hours
    else:
        release_total = 0.0
        window_end = case.current_time_hours
    end_level = case.start_level + case.inflow - release_total

    park_occupied = _park_is_occupied(case=case)
    would_overlap = (
        has_release
        and park_occupied
        and case.park_opens_at_hours is not None
        and window_end > case.park_opens_at_hours
    )
    downstream_cleared = park_secured or evacuated
    clearing_was_needed = would_overlap
    casualties = would_overlap and not downstream_cleared
    needless_closure = park_secured and not clearing_was_needed
    evacuation_warranted = clearing_was_needed and not case.park_lockable
    false_alarm = evacuated and not evacuation_warranted
    dam_ok = case.min_level <= end_level <= case.max_level

    round_succeeded = (
        not budget_exceeded
        and dam_ok
        and not casualties
        and not needless_closure
        and not false_alarm
    )
    failure_reason = _failure_reason(
        budget_exceeded=budget_exceeded,
        end_level=end_level,
        case=case,
        casualties=casualties,
        false_alarm=false_alarm,
        needless_closure=needless_closure,
    )
    return SpillwayOutcome(
        case_number=case.case_number,
        current_time_hours=case.current_time_hours,
        start_level=case.start_level,
        inflow=case.inflow,
        end_level=end_level,
        gates_opened=gates_opened,
        release_duration_hours=release_duration_hours,
        release_total=release_total,
        park_opens_at_hours=case.park_opens_at_hours,
        park_lockable=case.park_lockable,
        park_secured=park_secured,
        evacuated=evacuated,
        would_overlap=would_overlap,
        clearing_was_needed=clearing_was_needed,
        budget_exceeded=budget_exceeded,
        characters_used=characters_used,
        round_time_budget_seconds=case.round_time_budget_seconds,
        dam_ok=dam_ok,
        casualties=casualties,
        needless_closure=needless_closure,
        false_alarm=false_alarm,
        round_succeeded=round_succeeded,
        failure_reason=failure_reason,
    )
