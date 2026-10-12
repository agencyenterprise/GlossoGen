"""Matching a ``read_notifications`` handler to the response that issued its call.

The CLI runs a call as soon as its block streams, so the handler cannot see its
own response; the tracker finds it by the call's id when the handler has one,
and hands it the next recorded wait call otherwise.
"""

import asyncio

from glossogen.runners.session_harness.response_tracker import ResponseTracker, WaitCallVerdict
from glossogen.testing import SCRIPTED_SEAT_CLOCK


async def test_a_wait_alone_in_its_response_does_not_share_it() -> None:
    tracker = ResponseTracker(completion_limit=SCRIPTED_SEAT_CLOCK.response_completion_limit)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)
    tracker.response_completed(message_id="m1")

    assert await tracker.next_wait_call_verdict(call_id=None) is WaitCallVerdict.PARK


async def test_a_wait_beside_another_call_shares_its_response() -> None:
    tracker = ResponseTracker(completion_limit=SCRIPTED_SEAT_CLOCK.response_completion_limit)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)
    tracker.tool_used(message_id="m1", call_id="c2", is_wait=False)
    tracker.response_completed(message_id="m1")

    assert await tracker.next_wait_call_verdict(call_id=None) is WaitCallVerdict.SHARES_RESPONSE


async def test_a_wait_the_sdk_refused_is_skipped_by_the_next_handler() -> None:
    """The SDK checks arguments against the schema, so a refused call never reaches a handler.

    Its result still arrives, and the next handler must not be matched to it:
    here that would read the earlier, shared response and refuse a wait that was
    issued alone.
    """
    tracker = ResponseTracker(completion_limit=SCRIPTED_SEAT_CLOCK.response_completion_limit)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="refused", is_wait=True)
    tracker.tool_used(message_id="m1", call_id="sibling", is_wait=False)
    tracker.response_completed(message_id="m1")
    tracker.call_finished(call_id="refused")
    tracker.response_started(message_id="m2")
    tracker.tool_used(message_id="m2", call_id="alone", is_wait=True)
    tracker.response_completed(message_id="m2")

    assert await tracker.next_wait_call_verdict(call_id=None) is WaitCallVerdict.PARK


async def test_a_wait_whose_response_was_abandoned_is_released_without_parking() -> None:
    """A stream that ended before its response completed must not hold the handler."""
    tracker = ResponseTracker(completion_limit=SCRIPTED_SEAT_CLOCK.response_completion_limit)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)

    tracker.response_abandoned(message_id="m1")

    assert await tracker.next_wait_call_verdict(call_id=None) is WaitCallVerdict.RESPONSE_ABANDONED


async def test_a_response_that_settles_while_its_handler_waits_decides_the_verdict() -> None:
    tracker = ResponseTracker(completion_limit=SCRIPTED_SEAT_CLOCK.response_completion_limit)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)

    verdict = asyncio.ensure_future(tracker.next_wait_call_verdict(call_id=None))
    await asyncio.sleep(0)
    assert not verdict.done(), "the handler decided before its response settled"
    tracker.tool_used(message_id="m1", call_id="c2", is_wait=False)
    tracker.response_completed(message_id="m1")

    assert await verdict is WaitCallVerdict.SHARES_RESPONSE


async def test_a_wait_whose_response_never_settles_parks_once_the_limit_is_reached() -> None:
    """Codex reports a dropped stream only after the wait returns, so its response never settles."""

    async def limit_reached_at_once() -> None:
        return None

    tracker = ResponseTracker(completion_limit=limit_reached_at_once)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)

    assert await tracker.next_wait_call_verdict(call_id=None) is WaitCallVerdict.PARK


async def test_a_response_that_settled_is_read_even_when_the_limit_is_reached_at_once() -> None:
    async def limit_reached_at_once() -> None:
        return None

    tracker = ResponseTracker(completion_limit=limit_reached_at_once)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)
    tracker.tool_used(message_id="m1", call_id="c2", is_wait=False)
    tracker.response_completed(message_id="m1")

    assert await tracker.next_wait_call_verdict(call_id=None) is WaitCallVerdict.SHARES_RESPONSE


async def test_a_handler_that_knows_its_call_id_reads_its_own_response() -> None:
    """A handler with an id is not matched to an earlier wait call the runner has not settled."""
    tracker = ResponseTracker(completion_limit=SCRIPTED_SEAT_CLOCK.response_completion_limit)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="refused", is_wait=True)
    tracker.tool_used(message_id="m1", call_id="sibling", is_wait=False)
    tracker.response_completed(message_id="m1")
    tracker.response_started(message_id="m2")
    tracker.tool_used(message_id="m2", call_id="alone", is_wait=True)
    tracker.response_completed(message_id="m2")

    assert await tracker.next_wait_call_verdict(call_id="alone") is WaitCallVerdict.PARK


async def test_a_handler_with_an_id_waits_until_the_runner_records_its_call() -> None:
    tracker = ResponseTracker(completion_limit=SCRIPTED_SEAT_CLOCK.response_completion_limit)

    verdict = asyncio.ensure_future(tracker.next_wait_call_verdict(call_id="c1"))
    await asyncio.sleep(0)
    assert not verdict.done(), "the handler decided before its call was recorded"
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)
    tracker.tool_used(message_id="m1", call_id="c2", is_wait=False)
    tracker.response_completed(message_id="m1")

    assert await verdict is WaitCallVerdict.SHARES_RESPONSE


async def test_a_call_taken_by_its_id_is_not_handed_to_a_handler_without_one() -> None:
    tracker = ResponseTracker(completion_limit=SCRIPTED_SEAT_CLOCK.response_completion_limit)
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)
    tracker.tool_used(message_id="m1", call_id="c2", is_wait=False)
    tracker.response_completed(message_id="m1")
    tracker.response_started(message_id="m2")
    tracker.tool_used(message_id="m2", call_id="c3", is_wait=True)
    tracker.response_completed(message_id="m2")
    assert await tracker.next_wait_call_verdict(call_id="c1") is WaitCallVerdict.SHARES_RESPONSE

    assert await tracker.next_wait_call_verdict(call_id=None) is WaitCallVerdict.PARK
