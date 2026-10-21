"""One change to the shared server, as applied, logged and replayed.

A player's command reaches the server as calls such as "write this file" or "move
that directory", and each call amounts to one or more of these changes. The server
applies them through one path, the event log records them, and replaying them in
order after a fork rebuilds the server.
"""

import base64
from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ServerChangeKind(str, Enum):
    """What a change does.

    ``write`` sets a file's content, creating the file owned by the actor when it is
    missing. ``mkdir`` creates a directory owned by the actor. ``remove`` deletes a
    node and everything below it. ``chmod`` sets a node's mode. ``touch`` sets a
    file's modification time. A renamed node reads as removed and created.
    """

    WRITE = "write"
    MKDIR = "mkdir"
    REMOVE = "remove"
    CHMOD = "chmod"
    TOUCH = "touch"


class ServerChange(BaseModel):
    """One change, with the fields its kind uses and None for the rest.

    A ``write`` carries the file's content as text in ``content``. When the bytes are
    not valid UTF-8, ``content`` holds them decoded with replacement characters, for a
    reader, and ``content_base64`` holds the bytes themselves, which a replay writes.
    """

    kind: ServerChangeKind
    actor: str
    path: str
    content: str | None
    mode: int | None
    modified: datetime | None
    content_base64: str | None = None

    def content_bytes(self) -> bytes | None:
        """The bytes a ``write`` puts in the file, or None for a change carrying none."""
        if self.content_base64 is not None:
            return base64.b64decode(self.content_base64)
        if self.content is None:
            return None
        return self.content.encode("utf-8")


def readable_text(content: bytes) -> str:
    """``content`` as text: UTF-8, with a replacement character for each byte that is not."""
    return content.decode("utf-8", errors="replace")


def lossless_base64(content: bytes) -> str | None:
    """``content`` in base64 when it is not valid UTF-8, so a replay restores it exactly;
    None for UTF-8 text, which ``content`` already holds as is."""
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return base64.b64encode(content).decode("ascii")
    return None
