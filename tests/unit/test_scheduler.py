"""Round-boundary intervention dispatch and crash recovery."""

from typing import Any

import pytest

from glossogen.runtime.scheduled_events import InjectCase, ScheduledEvent, SetPostmortem
from glossogen.runtime.scheduler import RoundBoundaryScheduler


class RecordingOps:
    """Record scheduler calls and optionally fail while handling one payload."""

    def __init__(self, failing_payload: dict[str, Any] | None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.failing_payload = failing_payload

    async def perform_agent_swap(self, spec: object) -> None:
        self.calls.append(("swap", spec))

    async def set_postmortem_enabled(self, round_number: int, enabled: bool) -> None:
        self.calls.append(("postmortem", (round_number, enabled)))

    async def inject_case_payload(self, round_number: int, payload: dict[str, Any]) -> None:
        self.calls.append(("inject", (round_number, payload)))
        if payload == self.failing_payload:
            raise RuntimeError("injection failed")


@pytest.mark.asyncio
async def test_resume_continues_after_completed_event_in_same_round() -> None:
    """A completed first event must not suppress later events in its round."""
    events: list[ScheduledEvent] = [
        SetPostmortem(at_round=3, enabled=False),
        InjectCase(at_round=3, payload={"case": "replacement"}),
    ]
    scheduler = RoundBoundaryScheduler(
        events=events,
        completed_event_count_by_round={3: 1},
    )
    ops = RecordingOps(failing_payload=None)

    await scheduler.dispatch(round_number=3, ops=ops)
    await scheduler.dispatch(round_number=3, ops=ops)

    assert ops.calls == [("inject", (3, {"case": "replacement"}))]


@pytest.mark.asyncio
async def test_failed_event_is_retried_without_repeating_prior_event() -> None:
    """Only handlers that returned successfully advance the completion count."""
    failing_payload = {"case": "replacement"}
    events: list[ScheduledEvent] = [
        SetPostmortem(at_round=3, enabled=False),
        InjectCase(at_round=3, payload=failing_payload),
    ]
    scheduler = RoundBoundaryScheduler(events=events, completed_event_count_by_round={})
    first_ops = RecordingOps(failing_payload=failing_payload)

    with pytest.raises(RuntimeError, match="injection failed"):
        await scheduler.dispatch(round_number=3, ops=first_ops)

    resumed_ops = RecordingOps(failing_payload=None)
    await scheduler.dispatch(round_number=3, ops=resumed_ops)

    assert first_ops.calls == [
        ("postmortem", (3, False)),
        ("inject", (3, failing_payload)),
    ]
    assert resumed_ops.calls == [("inject", (3, failing_payload))]
