"""Guard the run every other file in this package scores against.

Every expected value in this package is arithmetic on this transcript. Without
this test, a change in how the runtime paces agents would move messages into
different rounds and each metric test would fail separately, with numbers that
look like metric bugs. This fails first, and says what actually changed.
"""

from tests.metrics.conftest import (
    MESSAGES_TOTAL,
    METRIC_RUN_GROUP,
    ROUND_COUNT,
    ROUNDS_WITH_MESSAGES,
    TOTAL_CHARS,
)
from tests.testbed.metric_harness import MetricRun
from tests.testbed.smoke_scenario import LINK_CHANNEL_ID

pytestmark = METRIC_RUN_GROUP


def test_the_transcript_is_the_one_the_expectations_assume(metric_run: MetricRun) -> None:
    """Message count, total characters, and how they are spread over rounds."""
    messages = metric_run.simulation.messages_on(channel_id=LINK_CHANNEL_ID)
    assert metric_run.simulation.failed_tool_calls() == []
    assert len(messages) == MESSAGES_TOTAL
    assert sum(len(str(m["text"])) for m in messages) == TOTAL_CHARS
    assert len({m["round_number"] for m in messages}) == ROUNDS_WITH_MESSAGES


def test_every_round_was_judged_even_the_silent_one(metric_run: MetricRun) -> None:
    """Round-level metrics count rounds, not rounds that carried traffic.

    Both rounds ran and both recorded a verdict, while only one carried
    messages. That gap is why `round_success` reports two rounds here and
    `mean_chars_per_round` reports one.
    """
    verdicts = metric_run.simulation.of_type(event_type="round_result_recorded")
    assert len(verdicts) == ROUND_COUNT
    assert metric_run.simulation.of_type(event_type="simulation_ended")
