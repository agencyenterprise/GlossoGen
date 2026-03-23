"""Built-in shared document tools for collaborative multi-agent artifact editing.

Provides ``list_documents``, ``read_document``, and ``write_document`` tools.
Documents are defined by the scenario via ``get_shared_documents()`` and live
in an in-memory store for the duration of the simulation. Each document has
per-agent read/write access control; writers implicitly have read access.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import NamedTuple

from schmidt.event_logger import EventLogger
from schmidt.models.event import SharedDocumentEdited
from schmidt.models.shared_document_config import SharedDocumentConfig
from schmidt.models.tool_definition import ToolParameter, ToolSpec

logger = logging.getLogger(__name__)


LIST_DOCUMENTS_SPEC = ToolSpec(
    name="list_documents",
    description=(
        "List all shared documents you have access to, showing each "
        "document's ID, title, and your access level (read or read/write)."
    ),
    parameters=[],
)

READ_DOCUMENT_SPEC = ToolSpec(
    name="read_document",
    description=(
        "Read the current content of a shared document. "
        "You must have read access to the document."
    ),
    parameters=[
        ToolParameter(
            name="document_id",
            param_type="string",
            description="The ID of the document to read.",
            required=True,
        ),
    ],
)

WRITE_DOCUMENT_SPEC = ToolSpec(
    name="write_document",
    description=(
        "Replace the content of a shared document with new content. "
        "You must have write access to the document. Other agents with "
        "read access will see your changes on their next read."
    ),
    parameters=[
        ToolParameter(
            name="document_id",
            param_type="string",
            description="The ID of the document to write to.",
            required=True,
        ),
        ToolParameter(
            name="content",
            param_type="string",
            description="The new content to set for the document.",
            required=True,
        ),
    ],
)


class SharedDocumentExecutors(NamedTuple):
    """The three executor callables returned by ``create_shared_document_executors``."""

    list_executor: Callable[..., Awaitable[str]]
    read_executor: Callable[..., Awaitable[str]]
    write_executor: Callable[..., Awaitable[str]]


def create_shared_document_executors(
    configs: list[SharedDocumentConfig],
    event_logger: EventLogger,
    round_number_getter: Callable[[], int],
) -> SharedDocumentExecutors:
    """Return list/read/write executor functions sharing an in-memory document store.

    Initializes each document from its ``SharedDocumentConfig``, populating the store
    with ``initial_content``. Access control is enforced per-call based on the
    agent ID and the document's reader/writer lists.
    """
    store: dict[str, str] = {}
    configs_by_id: dict[str, SharedDocumentConfig] = {}
    for cfg in configs:
        store[cfg.document_id] = cfg.initial_content
        configs_by_id[cfg.document_id] = cfg

    def _can_read(agent_id: str, cfg: SharedDocumentConfig) -> bool:
        return agent_id in cfg.reader_agent_ids or agent_id in cfg.writer_agent_ids

    def _can_write(agent_id: str, cfg: SharedDocumentConfig) -> bool:
        return agent_id in cfg.writer_agent_ids

    async def list_documents(agent_id: str) -> str:
        """List documents the calling agent has access to."""
        lines: list[str] = []
        for doc_id, cfg in configs_by_id.items():
            if not _can_read(agent_id, cfg):
                continue
            if _can_write(agent_id, cfg):
                access = "read/write"
            else:
                access = "read-only"
            lines.append(f"- {doc_id}: {cfg.title} [{access}]")

        if not lines:
            return "You do not have access to any shared documents."
        return "\n".join(lines)

    async def read_document(agent_id: str, document_id: str) -> str:
        """Return the current content of a shared document."""
        cfg = configs_by_id.get(document_id)
        if cfg is None:
            return f"Error: document '{document_id}' does not exist."
        if not _can_read(agent_id, cfg):
            return f"Error: you do not have read access to '{document_id}'."

        content = store[document_id]
        if not content:
            return f"Document '{cfg.title}' is empty."
        return content

    async def write_document(
        agent_id: str,
        document_id: str,
        content: str,
    ) -> str:
        """Replace the content of a shared document."""
        cfg = configs_by_id.get(document_id)
        if cfg is None:
            return f"Error: document '{document_id}' does not exist."
        if not _can_write(agent_id, cfg):
            return f"Error: you do not have write access to '{document_id}'."

        store[document_id] = content
        current_round = round_number_getter()

        await event_logger.log(
            event=SharedDocumentEdited(
                agent_id=agent_id,
                round_number=current_round,
                document_id=document_id,
                content=content,
            )
        )

        logger.debug(
            "Agent %s wrote to document '%s' (round %d)",
            agent_id,
            document_id,
            current_round,
        )
        return f"Document '{cfg.title}' updated successfully."

    return SharedDocumentExecutors(
        list_executor=list_documents,
        read_executor=read_document,
        write_executor=write_document,
    )
