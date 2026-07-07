"""OpenTelemetry span processor that stamps the current simulation round onto
pydantic-ai generation spans.

Langfuse traces are one-per-agent and span every round, and rounds advance on a
wall-clock timer mid-cycle, so round is a per-model-request property rather than
a trace-level one. This processor sets ``round_number`` on each ``chat``
(generation) span as it starts, reading the live round through a process-global
source that the runner points at the active ``SimulationRuntime``. The value
also lands as ``langfuse.observation.metadata.round_number`` so Langfuse
observations are filterable by round.
"""

from collections.abc import Callable

from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

_GENERATION_SPAN_PREFIX = "chat"


class CurrentRoundSource:
    """Process-global holder for the active simulation round.

    Telemetry is initialized before the ``SimulationRuntime`` exists, so the
    span processor reads the round through this indirection; the runner calls
    ``set_provider`` once the runtime is available.
    """

    def __init__(self) -> None:
        self._provider: Callable[[], int] | None = None

    def set_provider(self, provider: Callable[[], int]) -> None:
        """Register a callable returning the live round (e.g. ``runtime.current_round``)."""
        self._provider = provider

    def current_round(self) -> int | None:
        """Return the live round, or ``None`` before a provider is registered."""
        if self._provider is None:
            return None
        return self._provider()


current_round_source = CurrentRoundSource()


class RoundStampingSpanProcessor(SpanProcessor):
    """Stamps ``round_number`` on generation spans at span-start time."""

    def __init__(self, round_source: CurrentRoundSource) -> None:
        self._round_source = round_source

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:  # noqa: ARG002
        """Set the round attribute on ``chat`` spans as they open."""
        if not span.name.startswith(_GENERATION_SPAN_PREFIX):
            return
        round_number = self._round_source.current_round()
        if round_number is None:
            return
        span.set_attribute("round_number", round_number)
        span.set_attribute("langfuse.observation.metadata.round_number", round_number)

    def on_end(self, span: ReadableSpan) -> None:  # noqa: ARG002
        """No-op; the attribute is set at start and exported by other processors."""

    def shutdown(self) -> None:
        """No-op; this processor holds no resources."""

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        """No-op; nothing is buffered. Returns True to satisfy the interface."""
        return True
