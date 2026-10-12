"""Where a session seat's runner waits on time, gathered so a test can replace it.

There are two waits: the pause before the cycle that follows a failed one, and
the limit on how long a ``read_notifications`` call waits for the response that
issued it to complete. The shipped harnesses run on :data:`LIVE_SEAT_CLOCK`; a
test passes a clock whose waits it controls, so no test waits on the wall clock.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import NamedTuple

FAILURE_PAUSE_BASE_SECONDS = 30.0
"""The pause after the first failed cycle in a row; each later failure doubles it.
The seat stops at ``MAX_CONSECUTIVE_SESSION_FAILURES``, which bounds the longest."""

RESPONSE_COMPLETION_LIMIT_SECONDS = 30.0
"""How long a ``read_notifications`` call waits for its response to complete
before it parks without knowing the response's other calls.

In the harness smoke runs every response completed within 0.2 s of its
``read_notifications`` call. A response that never completes comes from a
dropped stream: Codex reports the drop only after the request's pending calls
have returned, so without a limit a wait issued in that request would hold the
seat until the run ended."""

FailurePause = Callable[[int], Awaitable[None]]
"""Waits before the cycle after a failed one, given how many have failed in a row."""

CompletionLimit = Callable[[], Awaitable[None]]
"""Returns once a response has had as long as it gets to complete."""


class SeatClock(NamedTuple):
    """The waits a session seat's runner takes on time."""

    pause_after_failure: FailurePause
    response_completion_limit: CompletionLimit


def failure_pause_seconds(consecutive_failures: int) -> float:
    """How long to wait after ``consecutive_failures`` failed cycles in a row."""
    return FAILURE_PAUSE_BASE_SECONDS * 2 ** (consecutive_failures - 1)


async def pause_after_failures(consecutive_failures: int) -> None:
    """Wait longer after each failure in a row, so an outage the CLI's own retries
    outlast has time to clear before the seat gives up."""
    await asyncio.sleep(failure_pause_seconds(consecutive_failures=consecutive_failures))


async def wait_out_response_completion_limit() -> None:
    """Return once ``RESPONSE_COMPLETION_LIMIT_SECONDS`` have passed."""
    await asyncio.sleep(RESPONSE_COMPLETION_LIMIT_SECONDS)


LIVE_SEAT_CLOCK = SeatClock(
    pause_after_failure=pause_after_failures,
    response_completion_limit=wait_out_response_completion_limit,
)
