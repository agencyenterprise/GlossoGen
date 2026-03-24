"""Configuration model for shared documents in a simulation.

Scenarios define which documents exist, their initial content, and per-agent
read/write access. The hub uses these configs to initialize the document store
and register the shared document tools.
"""

from pydantic import BaseModel


class SharedDocumentConfig(BaseModel):
    """Specification for a single shared document in the simulation workspace.

    Attributes:
        document_id: Unique identifier used by agents in tool calls.
        title: Human-readable name shown in document listings.
        initial_content: Starting content of the document (empty string if blank).
        reader_agent_ids: Agent IDs permitted to read this document.
        writer_agent_ids: Agent IDs permitted to write to this document.
            Writers implicitly have read access.
    """

    document_id: str
    title: str
    initial_content: str
    reader_agent_ids: list[str]
    writer_agent_ids: list[str]
