"""Matching a ``read_notifications`` handler to the response that issued its call.

The CLI runs a call as soon as its block streams, so the handler cannot see its
own response; the tracker hands it the next recorded wait call instead.
"""

from glossogen.runners.session_harness.response_tracker import ResponseTracker


async def test_a_wait_alone_in_its_response_does_not_share_it() -> None:
    tracker = ResponseTracker()
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)
    tracker.response_completed(message_id="m1")

    assert not await tracker.next_wait_call_shares_its_response()


async def test_a_wait_beside_another_call_shares_its_response() -> None:
    tracker = ResponseTracker()
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="c1", is_wait=True)
    tracker.tool_used(message_id="m1", call_id="c2", is_wait=False)
    tracker.response_completed(message_id="m1")

    assert await tracker.next_wait_call_shares_its_response()


async def test_a_wait_the_sdk_refused_is_skipped_by_the_next_handler() -> None:
    """The SDK checks arguments against the schema, so a refused call never reaches a handler.

    Its result still arrives, and the next handler must not be matched to it:
    here that would read the earlier, shared response and refuse a wait that was
    issued alone.
    """
    tracker = ResponseTracker()
    tracker.response_started(message_id="m1")
    tracker.tool_used(message_id="m1", call_id="refused", is_wait=True)
    tracker.tool_used(message_id="m1", call_id="sibling", is_wait=False)
    tracker.response_completed(message_id="m1")
    tracker.call_finished(call_id="refused")
    tracker.response_started(message_id="m2")
    tracker.tool_used(message_id="m2", call_id="alone", is_wait=True)
    tracker.response_completed(message_id="m2")

    assert not await tracker.next_wait_call_shares_its_response()
