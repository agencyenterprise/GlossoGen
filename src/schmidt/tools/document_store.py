"""In-memory storage for shared documents.

Provides a ``DocumentStore`` that manages document contents and access control,
supporting both normal read/write operations and bulk restore on resume.
"""

import logging

from schmidt.models.shared_document_config import SharedDocumentConfig

logger = logging.getLogger(__name__)


class DocumentStore:
    """Shared document storage with per-agent access control.

    Initializes documents from ``SharedDocumentConfig`` definitions. Provides
    read/write operations with access checks and bulk restore from checkpoints.
    """

    def __init__(self, configs: list[SharedDocumentConfig]) -> None:
        self._contents: dict[str, str] = {}
        self._configs: dict[str, SharedDocumentConfig] = {}
        for cfg in configs:
            self._contents[cfg.document_id] = cfg.initial_content
            self._configs[cfg.document_id] = cfg

    def get_config(self, document_id: str) -> SharedDocumentConfig | None:
        """Return the config for a document, or None if not found."""
        return self._configs.get(document_id)

    def get_all_configs(self) -> dict[str, SharedDocumentConfig]:
        """Return all document configs keyed by document ID."""
        return dict(self._configs)

    def read(self, document_id: str) -> str | None:
        """Return the content of a document, or None if not found."""
        return self._contents.get(document_id)

    def write(self, document_id: str, content: str) -> None:
        """Replace the content of a document."""
        self._contents[document_id] = content

    def can_read(self, agent_id: str, document_id: str) -> bool:
        """Check if an agent has read access to a document."""
        cfg = self._configs.get(document_id)
        if cfg is None:
            return False
        return agent_id in cfg.reader_agent_ids or agent_id in cfg.writer_agent_ids

    def can_write(self, agent_id: str, document_id: str) -> bool:
        """Check if an agent has write access to a document."""
        cfg = self._configs.get(document_id)
        if cfg is None:
            return False
        return agent_id in cfg.writer_agent_ids

    def restore(self, contents: dict[str, str]) -> None:
        """Bulk-restore document contents from a checkpoint."""
        for doc_id, content in contents.items():
            self._contents[doc_id] = content
        logger.info("Restored %d shared document(s)", len(contents))
