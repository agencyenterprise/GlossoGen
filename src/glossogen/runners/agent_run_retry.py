"""The retry policy for an agent's model calls.

A failed call is retried with exponential backoff, and each failure is logged
with its error before the pause. The runner's game cycles and its closing prompt
share this one policy.
"""

import logging

from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

AGENT_RUN_RETRY_ATTEMPTS = 3
AGENT_RUN_RETRY_BACKOFF_S = 1.0
"""The pause before the second attempt; each later pause doubles."""
AGENT_RUN_RETRY_MAX_BACKOFF_S = 30.0


def _log_agent_run_retry(retry_state: RetryCallState) -> None:
    """Log a failed attempt, with its error, before tenacity pauses and retries."""
    outcome = retry_state.outcome
    if outcome is None or not outcome.failed:
        return
    exc = outcome.exception()
    pause_s = 0.0
    if retry_state.next_action is not None:
        pause_s = retry_state.next_action.sleep
    logger.warning(
        "Model request attempt %d/%d failed with %s: %s; retrying in %.1fs",
        retry_state.attempt_number,
        AGENT_RUN_RETRY_ATTEMPTS,
        type(exc).__name__,
        exc,
        pause_s,
    )


agent_run_retry = retry(
    stop=stop_after_attempt(AGENT_RUN_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=AGENT_RUN_RETRY_BACKOFF_S, max=AGENT_RUN_RETRY_MAX_BACKOFF_S),
    reraise=True,
    before_sleep=_log_agent_run_retry,
)
"""Decorate an async model call with the policy above; the last failure is re-raised."""
