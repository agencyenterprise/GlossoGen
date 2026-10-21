"""One change to the shared server, as applied, logged and replayed.

A player's command reaches the server as calls such as "write this file" or "move
that directory", and each call amounts to one or more of these changes. The server
applies them through one path, the event log records them, and replaying them in
order after a fork rebuilds the server.
"""

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
    """One change, with the fields its kind uses and None for the rest."""

    kind: ServerChangeKind
    actor: str
    path: str
    content: str | None
    mode: int | None
    modified: datetime | None
