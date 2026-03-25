"""Pub/sub event bus for real-time simulation event delivery.

Supports fan-out to multiple subscribers. Carries persisted SimulationEvent
payloads (via EventLogger) and transient streaming events such as TokenDelta
and MessagePreview (via AgentRunner). The embedded simulation server reads
from subscriber queues to stream events over SSE to external consumers.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class EventBus:
    """Fan-out event bus backed by per-subscriber asyncio queues.

    Each call to ``subscribe`` creates a new bounded queue. Published events are
    delivered to every active subscriber. If a subscriber's queue is full, the
    oldest event is dropped (acceptable for transient token deltas since the
    complete text arrives in subsequent finalized events).
    """

    def __init__(self, max_queue_size: int) -> None:
        """Create a bus with the given per-subscriber queue capacity."""
        self._subscribers: list[asyncio.Queue[dict[str, object]]] = []
        self._max_queue_size = max_queue_size
        self._event_seq = 0

    def publish(self, event: dict[str, object]) -> None:
        """Send an event to all active subscribers.

        Drops the oldest event from any full queue to prevent backpressure from
        a slow consumer blocking the simulation. Synchronous because it only
        uses non-blocking queue operations.
        """
        for queue in self._subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def create_subscriber_queue(self) -> asyncio.Queue[dict[str, object]]:
        """Create and register a new subscriber queue.

        Returns a bounded queue that receives all future published events.
        The caller is responsible for calling ``remove_subscriber_queue``
        when done.
        """
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(
            maxsize=self._max_queue_size,
        )
        self._subscribers.append(queue)
        return queue

    def remove_subscriber_queue(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        """Unregister a subscriber queue created by ``create_subscriber_queue``."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
            logger.debug("Subscriber removed, %d subscribers remaining", len(self._subscribers))

    def next_event_seq(self) -> int:
        """Return a monotonically increasing sequence number for SSE frame IDs."""
        self._event_seq += 1
        return self._event_seq
