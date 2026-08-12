"""Compare two runs by the decisions they made, ignoring how agents got there.

A run's event log is not reproducible end to end. Agents are concurrent asyncio
tasks and a round ends on idle detection, so how many times each agent parks on
``read_notifications`` before the round closes varies between two runs of the
same code. Measured on veyru at seed 42: 166 events one run, 158 the next, with
the whole difference in ``llm_response_received`` / ``tool_call_invoked`` /
``tool_result_received``.

Everything else does reproduce exactly. Rounds, cases, injections, phase
transitions, verdicts, world notifications and the messages themselves matched
byte for byte across independent runs. That subset is what a scenario decides,
as opposed to what its agents happened to do, and it is the level at which two
implementations of one scenario can be held to be the same.

Hence a blocklist rather than an allowlist: any event a scenario adds is
structural by default, so a new scenario-specific event is compared without
anyone remembering to register it.
"""

from typing import Any, cast

# The per-cycle agent chatter, which varies run to run by construction.
AGENT_CYCLE_EVENTS = frozenset(
    {
        "llm_response_received",
        "tool_call_invoked",
        "tool_result_received",
    }
)

# Identifiers and clocks that differ between any two runs and carry no behaviour.
VOLATILE_FIELDS = frozenset(
    {
        "event_id",
        "timestamp",
        "message_id",
        "run_id",
        "elapsed_seconds",
        "duration_seconds",
    }
)


def _without_volatile(record: dict[str, Any]) -> dict[str, Any]:
    """Return ``record`` without the fields that differ between any two runs."""
    return {k: v for k, v in record.items() if k not in VOLATILE_FIELDS}


def _strip(event: dict[str, Any]) -> dict[str, Any]:
    """Drop volatile fields from an event and from its nested message."""
    cleaned = _without_volatile(event)
    message = cleaned.get("message")
    if isinstance(message, dict):
        cleaned["message"] = _without_volatile(cast(dict[str, Any], message))
    return cleaned


def structural_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the decisions a run made, in order, stripped of volatile fields."""
    return [_strip(e) for e in events if e.get("event_type") not in AGENT_CYCLE_EVENTS]


def describe_difference(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> str:
    """Return a readable account of the first structural divergence, or ''.

    Reports the position, the event type, and which fields disagree, because a
    raw dict-inequality dump of two 30-event lists is unreadable and the useful
    information is which field moved.
    """
    a = structural_events(left)
    b = structural_events(right)
    if len(a) != len(b):
        types_a = [e.get("event_type") for e in a]
        types_b = [e.get("event_type") for e in b]
        for i, (x, y) in enumerate(zip(types_a, types_b)):
            if x != y:
                return f"structural sequence diverges at {i}: {x!r} vs {y!r}"
        return f"structural event count differs: {len(a)} vs {len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        if x == y:
            continue
        fields = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
        lines = [f"structural event {i} ({x.get('event_type')}) differs on {fields}"]
        for key in fields[:5]:
            lines.append(f"  left  {key}: {str(x.get(key))[:200]}")
            lines.append(f"  right {key}: {str(y.get(key))[:200]}")
        return "\n".join(lines)
    return ""
