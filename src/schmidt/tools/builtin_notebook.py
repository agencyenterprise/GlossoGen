"""Built-in notebook tools that give agents a persistent private scratchpad across rounds.

Provides ``write_notebook`` for appending timestamped entries and ``read_notebook``
for retrieving all entries. Storage is in-memory per simulation run, keyed by agent ID.
Notebook contents are invisible to other agents.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import NamedTuple

from pydantic import BaseModel

from schmidt.event_logger import EventLogger
from schmidt.models.event import NotebookEntryWritten
from schmidt.models.tool_definition import ToolParameter, ToolSpec

logger = logging.getLogger(__name__)


class NotebookEntry(BaseModel):
    """A single timestamped entry in an agent's private notebook."""

    round_number: int
    timestamp: datetime
    text: str


WRITE_NOTEBOOK_SPEC = ToolSpec(
    name="write_notebook",
    description=(
        "Write a private note to your personal notebook. "
        "Only you can read your notebook. Use it to track observations, "
        "commitments, discrepancies, or plans across rounds."
    ),
    parameters=[
        ToolParameter(
            name="entry",
            param_type="string",
            description="The text to record in your notebook.",
            required=True,
        ),
    ],
)

READ_NOTEBOOK_SPEC = ToolSpec(
    name="read_notebook",
    description=(
        "Read all entries from your private notebook in chronological order. "
        "Returns everything you have previously written."
    ),
    parameters=[],
)


class NotebookExecutors(NamedTuple):
    """The write and read executor callables returned by ``create_notebook_executors``."""

    write_executor: Callable[..., Awaitable[str]]
    read_executor: Callable[..., Awaitable[str]]


def create_notebook_executors(
    event_logger: EventLogger,
    round_number_getter: Callable[[], int],
) -> NotebookExecutors:
    """Return write and read executor functions sharing an in-memory notebook store.

    The ``round_number_getter`` callable is invoked each time ``write_notebook`` is
    called to stamp entries with the current round number.
    """
    store: dict[str, list[NotebookEntry]] = {}

    async def write_notebook(agent_id: str, entry: str) -> str:
        """Append a timestamped entry to the agent's private notebook."""
        current_round = round_number_getter()
        notebook_entry = NotebookEntry(
            round_number=current_round,
            timestamp=datetime.now(tz=UTC),
            text=entry,
        )

        if agent_id not in store:
            store[agent_id] = []
        store[agent_id].append(notebook_entry)

        await event_logger.log(
            event=NotebookEntryWritten(
                agent_id=agent_id,
                round_number=current_round,
                entry_text=entry,
            )
        )

        logger.debug("Agent %s wrote notebook entry (round %d)", agent_id, current_round)
        return "Entry recorded in your notebook."

    async def read_notebook(agent_id: str) -> str:
        """Return all notebook entries for the agent in chronological order."""
        entries = store.get(agent_id, [])
        if not entries:
            return "Your notebook is empty."

        lines: list[str] = []
        for e in entries:
            lines.append(f"[Round {e.round_number}] {e.text}")
        return "\n".join(lines)

    return NotebookExecutors(
        write_executor=write_notebook,
        read_executor=read_notebook,
    )
