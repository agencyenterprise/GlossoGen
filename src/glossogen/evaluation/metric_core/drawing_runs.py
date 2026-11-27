"""Detects runs whose agents sent canvas drawings, which the text metrics cannot read.

A drawing is recorded as a message with empty text and a ``drawing``. A metric
that scores the words agents wrote has nothing to read in it, so it returns no
measurement for such a run instead of scoring the empty texts.
"""

import logging

from glossogen.models.event import MessageSent, SimulationEvent

logger = logging.getLogger(__name__)


def run_sends_drawings(events: list[SimulationEvent]) -> bool:
    """Whether any message in the run is a canvas drawing."""
    return any(
        isinstance(event, MessageSent) and event.message.drawing is not None for event in events
    )


def text_metric_skips_drawings(metric_name: str, events: list[SimulationEvent]) -> bool:
    """Whether ``metric_name``, a metric that reads message text, skips a run that sent drawings.

    Logs the reason when it skips.
    """
    if not run_sends_drawings(events=events):
        return False
    logger.info(
        "%s: skipping — the run's agents sent drawings, and this metric reads text", metric_name
    )
    return True
