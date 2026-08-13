"""Compare two runs by the decisions they made, ignoring how agents got there.

A run's event log is not reproducible end to end. Agents are concurrent asyncio
tasks, so two runs of the same code differ in three ways, each measured rather
than assumed:

- How many cycles each agent spends parking on ``read_notifications`` before
  idle detection closes a round. That moves ``llm_response_received``,
  ``tool_call_invoked`` and ``tool_result_received``, which have been observed
  at 66/33/33 on one run and 62/31/31 on the next.
- The interleaving of messages from *different* agents. Locally this was stable
  across six runs; on CI it was not, putting a different sender at the same
  position. Anything comparing messages as one global sequence is a test that
  passes on a developer's machine and flakes in CI.
- The order of world notifications, including those to the *same* agent. One
  recipient's notifications come from more than one producer: the world reacts
  to messages on its own task while the clock announces round outcomes from
  another. Measured on container_yard_stacking, where a budget-exceeded
  notification and a round-failed one arrive in either order. They are compared
  as a multiset per recipient for that reason, which means this does not compare
  the order an agent was told things in, only what it was told.
- Which round a message is attributed to, since that depends on where the round
  boundary falls relative to an agent's cycle.

What does reproduce is what the scenario decided: which case each round ran,
what each agent was told, when the phase opened and closed, what the world
announced, and how each round was scored. Those were identical in order and
content across six local runs and across CI.

Messages are compared per sender and in order: one agent sends them from a
single sequential script, so they cannot reorder relative to each other, which is
deterministic by construction rather than by observation. A message's round
attribution is left out for the reason above, so this does not compare *when*
something was said. Notifications are compared per recipient as a multiset, so it
does compare everything an agent was told and not the order it heard it in.

Decision events use a blocklist rather than an allowlist, so an event a
scenario adds is compared without anyone remembering to register it.
"""

from typing import Any, cast

# Per-cycle agent chatter. Varies with scheduling, by construction.
AGENT_CYCLE_EVENTS = frozenset(
    {
        "llm_response_received",
        "tool_call_invoked",
        "tool_result_received",
    }
)

# Compared separately, grouped by the participant they belong to. See the module
# docstring.
MESSAGE_EVENT = "message_sent"
WORLD_DELIVERY_EVENT = "world_event_delivered"

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

# A message's round attribution depends on scheduling, so it is not compared.
VOLATILE_MESSAGE_FIELDS = VOLATILE_FIELDS | {"round_number"}


def _without(record: dict[str, Any], fields: frozenset[str]) -> dict[str, Any]:
    """Return ``record`` without ``fields``."""
    return {k: v for k, v in record.items() if k not in fields}


def _strip(event: dict[str, Any]) -> dict[str, Any]:
    """Drop volatile fields from an event and from its nested message."""
    cleaned = _without(event, VOLATILE_FIELDS)
    message = cleaned.get("message")
    if isinstance(message, dict):
        cleaned["message"] = _without(cast(dict[str, Any], message), VOLATILE_FIELDS)
    return cleaned


def decision_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the decisions a run made, in order, stripped of volatile fields.

    Excludes agent chatter, messages and world notifications; those are compared
    by ``messages_by_sender`` and ``deliveries_by_recipient`` instead.
    """
    return [
        _strip(e)
        for e in events
        if e.get("event_type") not in AGENT_CYCLE_EVENTS
        and e.get("event_type") not in (MESSAGE_EVENT, WORLD_DELIVERY_EVENT)
    ]


def messages_by_sender(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return each agent's own messages, in the order that agent sent them."""
    by_sender: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("event_type") != MESSAGE_EVENT:
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        payload = _without(cast(dict[str, Any], message), VOLATILE_MESSAGE_FIELDS)
        sender = str(payload.get("sender_agent_id"))
        by_sender.setdefault(sender, []).append(payload)
    return by_sender


def deliveries_by_recipient(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return each agent's world notifications, in the order it received them."""
    by_recipient: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("event_type") != WORLD_DELIVERY_EVENT:
            continue
        payload = _without(event, VOLATILE_FIELDS)
        recipient = str(payload.get("agent_id"))
        by_recipient.setdefault(recipient, []).append(payload)
    return by_recipient


def describe_difference(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> str:
    """Return a readable account of the first divergence, or '' when equivalent.

    Reports the position, the event type and the disagreeing fields, because a
    dict-inequality dump of two thirty-event lists is unreadable and the useful
    information is which field moved.
    """
    decisions = _describe_sequence(decision_events(left), decision_events(right))
    if decisions:
        return decisions
    messages = _describe_streams(
        messages_by_sender(left), messages_by_sender(right), label="sent by", ordered=True
    )
    if messages:
        return messages
    return _describe_streams(
        deliveries_by_recipient(left),
        deliveries_by_recipient(right),
        label="delivered to",
        ordered=False,
    )


def _describe_sequence(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> str:
    """Describe the first difference between two decision sequences."""
    if len(a) != len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            if x.get("event_type") != y.get("event_type"):
                return (
                    f"decision sequence diverges at {i}: "
                    f"{x.get('event_type')!r} vs {y.get('event_type')!r}"
                )
        return f"decision count differs: {len(a)} vs {len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        if x == y:
            continue
        fields = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
        lines = [f"decision {i} ({x.get('event_type')}) differs on {fields}"]
        for key in fields[:5]:
            lines.append(f"  left  {key}: {str(x.get(key))[:200]}")
            lines.append(f"  right {key}: {str(y.get(key))[:200]}")
        return "\n".join(lines)
    return ""


def _describe_streams(
    a: dict[str, list[dict[str, Any]]],
    b: dict[str, list[dict[str, Any]]],
    label: str,
    ordered: bool,
) -> str:
    """Describe the first difference between two participant-keyed streams.

    ``ordered`` says whether the stream's order is the participant's own. A
    sender's messages are; a recipient's notifications are not, because more
    than one producer writes to them.
    """
    if set(a) != set(b):
        return f"different agents {label}: {sorted(set(a) ^ set(b))}"
    for agent in sorted(a):
        if ordered:
            mine, theirs = a[agent], b[agent]
        else:
            mine = sorted(a[agent], key=_sort_key)
            theirs = sorted(b[agent], key=_sort_key)
        if mine == theirs:
            continue
        if len(mine) != len(theirs):
            return f"{len(mine)} vs {len(theirs)} {label} {agent}"
        for i, (x, y) in enumerate(zip(mine, theirs)):
            if x != y:
                return (
                    f"entry {i} {label} {agent} differs\n"
                    f"  left  {str(x)[:200]}\n"
                    f"  right {str(y)[:200]}"
                )
    return ""


def _sort_key(entry: dict[str, Any]) -> str:
    """Order entries deterministically so two multisets compare elementwise."""
    return "|".join(f"{k}={entry[k]!r}" for k in sorted(entry))
