"""What the session runner needs from an agent CLI's session, in glossogen's own types.

The runner talks to a ``SeatSession`` and never imports a CLI's SDK, so each
CLI is needed only when a seat actually runs under its harness, and a test
drives the runner with a scripted session. The adapters are
:mod:`glossogen.runners.claude_agent_sdk.claude_sdk_seat_session` and
:mod:`glossogen.runners.codex_app_server.codex_seat_session`.

A session streams one ``SessionItem`` per thing the CLI reports, in order, and
ends each cycle with ``CycleEnded``. A response's content arrives block by block,
and a tool may run, and its result arrive, before the rest of its response has
streamed; ``ResponseCompleted`` closes a response with its stop reason and usage.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, NamedTuple, Protocol

from glossogen.models.event_base import TokenUsage
from glossogen.runners.agent_tools import ToolOutcome

SeatToolHandler = Callable[[dict[str, Any]], Awaitable[ToolOutcome]]


class SeatTool(NamedTuple):
    """One tool served to the seat: its schema, and the handler that runs a call to it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: SeatToolHandler


class SeatOptions(NamedTuple):
    """How a seat's session is started.

    ``seat_dir`` holds the CLI's working directory and its configuration
    directory, so the session transcript stays with the run. It may be
    relative; a session resolves it before handing paths to a CLI, which runs
    in its own working directory. ``resume_session_id``
    continues an earlier session of this seat after its process failed, or is
    None for a fresh one.
    """

    model: str
    system_prompt: str
    tools: tuple[SeatTool, ...]
    max_output_tokens: int
    seat_dir: Path
    resume_session_id: str | None


class ResponseAbandoned(NamedTuple):
    """A response the CLI gave up on before it completed, as when a stream drops and is retried.

    It never reports its usage; the request that replaces it opens a response of
    its own.
    """

    message_id: str


class SessionStarted(NamedTuple):
    """The CLI opened or resumed the session ``session_id``, before any response."""

    session_id: str


class ResponseStarted(NamedTuple):
    """The model began a response."""

    message_id: str


class TextChunk(NamedTuple):
    """A text block of a response."""

    message_id: str
    text: str


class ThinkingChunk(NamedTuple):
    """A thinking block of a response, with what its provider needs to accept it back.

    ``signature`` is None when the provider sends none.
    """

    message_id: str
    thinking: str
    signature: str | None
    provider_name: str


class ToolUseChunk(NamedTuple):
    """A tool call in a response. ``tool_name`` is the seat tool's own name.

    ``answered_by_cli`` is True for a call the CLI answers itself without
    running a seat tool, such as one whose arguments it could not parse; no
    handler runs for it, so it is never matched to one.
    """

    message_id: str
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    answered_by_cli: bool


class ResponseCompleted(NamedTuple):
    """A response finished: why it stopped, and the tokens it used."""

    message_id: str
    stop_reason: str
    usage: TokenUsage


class ToolResultChunk(NamedTuple):
    """The result a tool call returned to the model."""

    call_id: str
    content: str


class CompactionBoundary(NamedTuple):
    """The CLI compacted the seat's context. ``details`` is what it reported, verbatim."""

    details: dict[str, Any]


class CycleEnded(NamedTuple):
    """The CLI finished answering one prompt.

    ``error_text`` is empty unless ``is_error``. ``reported_cost_usd`` is the
    CLI's own figure, which also counts calls it made beyond the seat's
    responses; the platform prices the responses itself.
    """

    session_id: str
    is_error: bool
    error_text: str
    reported_cost_usd: float | None


SessionItem = (
    SessionStarted
    | ResponseStarted
    | TextChunk
    | ThinkingChunk
    | ToolUseChunk
    | ResponseCompleted
    | ResponseAbandoned
    | ToolResultChunk
    | CompactionBoundary
    | CycleEnded
)


class SeatSession(Protocol):
    """One seat's conversation with the model, held open across cycles."""

    async def connect(self, options: SeatOptions) -> None:
        """Start the session."""
        ...

    async def send(self, prompt: str) -> None:
        """Send the next user turn."""
        ...

    def items(self) -> AsyncIterator[SessionItem]:
        """Everything the CLI reports for the turn just sent, ending with ``CycleEnded``."""
        ...

    async def interrupt(self) -> None:
        """Stop the turn in progress; the session still ends it with ``CycleEnded``."""
        ...

    async def close(self) -> None:
        """End the session and its process."""
        ...


SeatSessionFactory = Callable[[], SeatSession]
