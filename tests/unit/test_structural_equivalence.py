"""The comparison has to report differences that matter and ignore the rest.

`test_structural_determinism` shows the comparison is stable against itself,
which a comparison that returned "equivalent" unconditionally would also pass.
These drive it with hand-built logs so both halves are pinned: the differences
it must report, and the churn it must not.

Synthetic rather than simulated on purpose. Producing a run that differs in
exactly one field is not something a real simulation can be asked for.
"""

from typing import Any

from tests.testbed.structural_equivalence import (
    decision_events,
    describe_difference,
    messages_by_sender,
)


def decision(event_type: str, round_number: int, **fields: Any) -> dict[str, Any]:
    """Build a decision event with the volatile fields a real one carries."""
    return {
        "event_id": "generated-per-run",
        "timestamp": "2026-01-01T00:00:00Z",
        "event_type": event_type,
        "round_number": round_number,
        **fields,
    }


def message(sender: str, text: str, round_number: int, channel_id: str) -> dict[str, Any]:
    """Build a message event with the volatile fields a real one carries."""
    return {
        "event_id": "generated-per-run",
        "timestamp": "2026-01-01T00:00:00Z",
        "event_type": "message_sent",
        "round_number": round_number,
        "message": {
            "message_id": "generated-per-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "channel_id": channel_id,
            "sender_agent_id": sender,
            "text": text,
            "round_number": round_number,
        },
    }


BASELINE: list[dict[str, Any]] = [
    decision(event_type="round_advanced", round_number=1, trigger="simulation_start"),
    decision(event_type="veyru_case_started", round_number=1, case_number=7),
    decision(event_type="injection_delivered", round_number=1, agent_id="a", text="do the thing"),
    message(sender="a", text="alpha one", round_number=1, channel_id="link"),
    message(sender="b", text="beta one", round_number=1, channel_id="link"),
    message(sender="a", text="alpha two", round_number=1, channel_id="link"),
    decision(event_type="round_result_recorded", round_number=1, success=True, reason="stabilized"),
]


def test_two_copies_of_one_log_are_equivalent() -> None:
    """The trivial case, which everything else is measured against."""
    assert describe_difference(BASELINE, list(BASELINE)) == ""


def test_volatile_identifiers_and_clocks_are_ignored() -> None:
    """Ids and timestamps differ between any two runs and mean nothing."""
    other = [dict(e) for e in BASELINE]
    for event in other:
        event["event_id"] = "different"
        event["timestamp"] = "2027-02-02T00:00:00Z"
        if "message" in event:
            nested = dict(event["message"])
            nested["message_id"] = "different"
            nested["timestamp"] = "2027-02-02T00:00:00Z"
            event["message"] = nested

    assert describe_difference(BASELINE, other) == ""


def test_messages_from_different_agents_may_interleave_either_way() -> None:
    """This is the reordering that failed in CI and must not fail here."""
    swapped = [
        BASELINE[0],
        BASELINE[1],
        BASELINE[2],
        BASELINE[4],
        BASELINE[3],
        BASELINE[5],
        BASELINE[6],
    ]

    assert describe_difference(BASELINE, swapped) == ""


def test_a_changed_injection_is_reported() -> None:
    """What an agent was told is the scenario's own output."""
    other = [dict(e) for e in BASELINE]
    other[2] = decision(
        event_type="injection_delivered", round_number=1, agent_id="a", text="do something else"
    )

    difference = describe_difference(BASELINE, other)

    assert "injection_delivered" in difference
    assert "text" in difference


def test_a_changed_verdict_is_reported() -> None:
    """Scoring the round differently is the difference that matters most."""
    other = [dict(e) for e in BASELINE]
    other[6] = decision(
        event_type="round_result_recorded", round_number=1, success=False, reason="collapsed"
    )

    difference = describe_difference(BASELINE, other)

    assert "round_result_recorded" in difference
    assert "success" in difference


def test_a_different_case_is_reported() -> None:
    """Running a different case makes every downstream comparison meaningless."""
    other = [dict(e) for e in BASELINE]
    other[1] = decision(event_type="veyru_case_started", round_number=1, case_number=9)

    assert "veyru_case_started" in describe_difference(BASELINE, other)


def test_a_missing_decision_is_reported() -> None:
    """A phase that never opened is a decision that never happened."""
    other = [e for e in BASELINE if e["event_type"] != "veyru_case_started"]

    assert describe_difference(BASELINE, other) != ""


def test_changed_message_text_is_reported() -> None:
    """Dropping global order must not stop the words being compared."""
    other = [dict(e) for e in BASELINE]
    other[3] = message(sender="a", text="alpha ONE CHANGED", round_number=1, channel_id="link")

    difference = describe_difference(BASELINE, other)

    assert "a message 0 differs" in difference


def test_one_agent_going_silent_is_reported() -> None:
    """An engine that stopped delivering a role's messages would pass otherwise."""
    other = [e for e in BASELINE if not (e.get("message", {}).get("sender_agent_id") == "b")]

    assert "different senders" in describe_difference(BASELINE, other)


def test_reordering_one_agents_own_messages_is_reported() -> None:
    """One agent's messages come from one sequential script and cannot reorder.

    So a difference here is the implementation, not the scheduler, and is the
    reason messages are grouped by sender rather than pooled.
    """
    other = [
        BASELINE[0],
        BASELINE[1],
        BASELINE[2],
        BASELINE[5],
        BASELINE[4],
        BASELINE[3],
        BASELINE[6],
    ]

    assert "a message 0 differs" in describe_difference(BASELINE, other)


def test_a_messages_round_attribution_is_not_compared() -> None:
    """Where the round boundary falls relative to a cycle is scheduling."""
    other = [dict(e) for e in BASELINE]
    other[3] = message(sender="a", text="alpha one", round_number=2, channel_id="link")

    assert describe_difference(BASELINE, other) == ""


def test_the_two_halves_partition_the_log() -> None:
    """Every message is compared as a message and no decision is one."""
    decisions = decision_events(BASELINE)
    messages = messages_by_sender(BASELINE)

    assert all(e["event_type"] != "message_sent" for e in decisions)
    assert sum(len(v) for v in messages.values()) == 3
    assert sorted(messages) == ["a", "b"]
