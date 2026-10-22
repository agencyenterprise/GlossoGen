"""A text the plaintext judge reads: what a player put on the server or ran on it, and where."""

from typing import NamedTuple

from glossogen.scenarios.signal_game_server.ids import WrittenTextKind


class WrittenText(NamedTuple):
    """One text a player put on the server or ran on it, of one of the ``WrittenTextKind`` kinds.

    ``path`` is the node's path, or for a command line which of the player's calls in the
    round it was, such as ``run_command 3``.
    """

    kind: WrittenTextKind
    path: str
    author: str
    text: str
