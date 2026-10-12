"""What the ``external_cli`` runner needs to know about one agent CLI.

An ``AgentCli`` says how to start the CLI for one turn, pointed at the seat's
tool endpoint, and how to read the turn's outcome from what the process wrote.
The runner owns the process and the endpoint; the CLI definition owns the
command line, the environment and the output format.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple, Protocol

from glossogen.models.event_base import TokenUsage


class CliSeat(NamedTuple):
    """One seat as a CLI is started for it.

    ``state_dir`` is the seat's private directory, where the CLI keeps its
    configuration and session; ``workspace`` is the directory it runs in.
    ``tool_url`` and ``tool_token`` reach the seat's tools over MCP.
    """

    agent_id: str
    model: str
    system_prompt: str
    max_output_tokens: int
    state_dir: Path
    workspace: Path
    tool_url: str
    tool_token: str


class CliTurn(NamedTuple):
    """One turn to run: the prompt, and the session to continue when there is one."""

    prompt: str
    resume_session_id: str | None


class CliTurnResult(NamedTuple):
    """What a turn's process reported: its session, its usage, and whether it failed."""

    session_id: str | None
    usage: TokenUsage
    reported_cost_usd: float | None
    is_error: bool
    error_text: str


NO_USAGE = TokenUsage(
    input_tokens=0,
    output_tokens=0,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
)


class AgentCli(Protocol):
    """One agent CLI, as the runner starts it and reads it."""

    def prepare(self, seat: CliSeat) -> None:
        """Write whatever the CLI needs on disk before its first turn."""
        ...

    def command(self, seat: CliSeat, turn: CliTurn) -> list[str]:
        """The command line that runs ``turn`` for ``seat``."""
        ...

    def environment(self, seat: CliSeat) -> Mapping[str, str]:
        """The environment the process is started with."""
        ...

    def parse_output(self, stdout: str) -> CliTurnResult:
        """The turn's outcome, read from what the process wrote to stdout."""
        ...

    def transcripts_dir(self, seat: CliSeat) -> Path:
        """Where the CLI writes its session transcripts for ``seat``, under its state directory."""
        ...
