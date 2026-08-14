"""What a run reproduces, pinned so a comparison can be built on it.

Replacing a hand-written scenario with a generated one is only safe if the two
can be shown to decide the same things. That comparison is worthless unless the
thing compared is stable for a single implementation first, which is what these
establish.

They also guard `structural_equivalence` itself. Comparing too much makes a
flaky test: an earlier version compared messages as one global sequence, passed
six times locally, and failed in CI where two agents interleaved the other way.
Comparing too little makes a vacuous one, which is the failure that would let a
broken engine through.
"""

from pathlib import Path
from typing import Any

import pytest

from glossogen.testing.scenario_runtime import run_rounds
from tests.testbed.structural_equivalence import (
    decision_events,
    deliveries_by_recipient,
    describe_difference,
    messages_by_sender,
)

pytestmark = pytest.mark.xdist_group("veyru")

ROUNDS = 2


async def play_veyru(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Run veyru at the canonical seed with its debrief open."""
    result = await run_rounds(
        scenario_name="veyru",
        round_count=ROUNDS,
        overrides={"seed": 42, "postmortem_enabled": True},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    return result.events


async def test_two_identical_runs_decide_the_same_things(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same code, same seed, same decisions, down to the field."""
    first = await play_veyru(tmp_path / "first", monkeypatch)
    second = await play_veyru(tmp_path / "second", monkeypatch)

    difference = describe_difference(first, second)

    assert difference == "", difference


async def test_the_comparison_still_looks_at_the_things_that_matter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filtering one type too many leaves a test that passes against anything.

    Each event named here is a decision the engine has to reproduce: which case
    ran, what each agent was told, when the phase opened, what the world
    announced, and how the round was scored.
    """
    events = await play_veyru(tmp_path / "only", monkeypatch)

    kinds = {e.get("event_type") for e in decision_events(events)}

    for required in (
        "round_advanced",
        "round_ended",
        "round_result_recorded",
        "injection_delivered",
        "veyru_case_started",
        "postmortem_started",
        "postmortem_ended",
        "simulation_ended",
    ):
        assert required in kinds, f"{required} was filtered out of the comparison"
    # Compared per recipient rather than in sequence, so it is absent from the
    # decisions and has to be looked for where it now lives.
    assert deliveries_by_recipient(events), "world notifications left the comparison entirely"


async def test_messages_are_compared_even_though_their_order_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping global message order must not drop messages from the comparison.

    Interleaving between agents varies, so messages are grouped by sender. What
    each agent said still has to be compared, or an engine that stopped
    delivering a role's messages entirely would pass.
    """
    events = await play_veyru(tmp_path / "messages", monkeypatch)

    by_sender = messages_by_sender(events)

    assert by_sender, "no messages were captured for comparison"
    assert all(messages for messages in by_sender.values())
    for messages in by_sender.values():
        for message in messages:
            assert "text" in message, "message text is not compared"
            assert "channel_id" in message, "message channel is not compared"
            assert (
                "round_number" not in message
            ), "round attribution depends on scheduling and would flake"
