"""Langfuse + pydantic-ai OpenTelemetry bootstrap for the simulation run path.

Initializes the Langfuse OpenTelemetry exporter and enables pydantic-ai agent
instrumentation once per ``glossogen run`` process. Every simulation agent's LLM
calls (prompts, completions, tool calls, token usage) are then exported as
OpenTelemetry spans to the configured Langfuse instance. Bootstrapping only in
the run path keeps the separate ``glossogen evaluate`` process untraced.

Telemetry never blocks a simulation: absent keys, an unreachable Langfuse
instance, or any initialization error degrades to an untraced run.
"""

import atexit
import logging
from dataclasses import dataclass

from langfuse import Langfuse, get_client
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from pydantic_ai import Agent, InstrumentationSettings

from glossogen.telemetry_round_processor import RoundStampingSpanProcessor, current_round_source
from glossogen.telemetry_settings import TelemetrySettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LangfuseHandle:
    """Live Langfuse client for a run, used to flush spans before process exit."""

    client: Langfuse


def init_langfuse_telemetry(settings: TelemetrySettings) -> LangfuseHandle | None:
    """Initialize Langfuse OTEL export and enable pydantic-ai instrumentation.

    Returns a handle when telemetry is active, or ``None`` when it is disabled
    (keys absent) or could not be initialized (auth failure, unreachable host,
    unexpected error). ``get_client()`` installs a global OpenTelemetry tracer
    provider that ``Agent.instrument_all`` then feeds. Full message content is
    exported so agent transcripts are inspectable in Langfuse.
    """
    if not settings.enabled:
        logger.info("Langfuse telemetry disabled (LANGFUSE_PUBLIC_KEY/SECRET_KEY not set)")
        return None
    try:
        client = get_client()
    except Exception:
        logger.exception("Failed to initialize Langfuse client; running untraced")
        return None

    # An unreachable Langfuse (stack not started) is an expected local-dev state,
    # not a bug — report it as a clean warning without a stacktrace. auth_check
    # returns False for bad-but-reachable keys and raises for connection errors.
    try:
        authenticated = client.auth_check()
    except Exception as exc:
        logger.warning(
            "Langfuse unreachable (host=%s): %s; running untraced. "
            "Start the local stack with `make langfuse-up`.",
            settings.host,
            type(exc).__name__,
        )
        return None
    if not authenticated:
        logger.warning(
            "Langfuse auth_check failed (host=%s); running untraced. "
            "Check LANGFUSE_PUBLIC_KEY/SECRET_KEY against the running instance.",
            settings.host,
        )
        return None

    try:
        Agent.instrument_all(
            InstrumentationSettings(include_content=True, include_binary_content=False)
        )
        _register_round_span_processor()
    except Exception:
        logger.exception("Failed to enable pydantic-ai instrumentation; running untraced")
        return None
    atexit.register(client.flush)
    logger.info("Langfuse telemetry enabled (host=%s)", settings.host)
    return LangfuseHandle(client=client)


def _register_round_span_processor() -> None:
    """Attach the round-stamping processor to the global tracer provider.

    ``get_client()`` installs an SDK ``TracerProvider`` as the global provider;
    the round processor is added alongside Langfuse's own exporting processor so
    every generation span is stamped with the live round before it is exported.
    """
    provider = otel_trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(RoundStampingSpanProcessor(round_source=current_round_source))
    else:
        logger.warning(
            "Global tracer provider is %s, not an SDK TracerProvider; " "round stamping disabled",
            type(provider).__name__,
        )


def flush_telemetry(handle: LangfuseHandle) -> None:
    """Flush all buffered spans to Langfuse; call before the run process exits."""
    try:
        handle.client.flush()
    except Exception:
        logger.exception("Failed to flush Langfuse telemetry")
