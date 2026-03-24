"""In-memory storage for agent private notebooks.

Provides ``NotebookEntry`` as the data model for individual entries and
``NotebookStore`` for managing per-agent notebook collections, supporting
both normal append operations during simulation and bulk restore on resume.
"""

import logging
from datetime import datetime

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class NotebookEntry(BaseModel):
    """A single timestamped entry in an agent's private notebook."""

    round_number: int
    timestamp: datetime
    text: str


class NotebookStore:
    """Per-agent private notebook storage.

    Each agent has a list of ``NotebookEntry`` objects. Entries are appended
    during the simulation and can be bulk-restored from a checkpoint.
    """

    def __init__(self) -> None:
        self._entries: dict[str, list[NotebookEntry]] = {}

    def append(self, agent_id: str, entry: NotebookEntry) -> None:
        """Append an entry to the given agent's notebook."""
        if agent_id not in self._entries:
            self._entries[agent_id] = []
        self._entries[agent_id].append(entry)

    def get_entries(self, agent_id: str) -> list[NotebookEntry]:
        """Return all entries for the given agent, or an empty list."""
        return self._entries.get(agent_id, [])

    def restore(self, entries_by_agent: dict[str, list[NotebookEntry]]) -> None:
        """Bulk-restore notebook entries from a checkpoint.

        Replaces any existing entries for the given agents.
        """
        total = 0
        for agent_id, entries in entries_by_agent.items():
            self._entries[agent_id] = list(entries)
            total += len(entries)
        logger.info("Restored %d notebook entries for %d agents", total, len(entries_by_agent))
