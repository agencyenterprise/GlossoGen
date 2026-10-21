"""A text the plaintext judge reads: what a player put on the server, and where."""

from typing import NamedTuple

from glossogen.scenarios.signal_game.ids import WrittenTextKind


class WrittenText(NamedTuple):
    """One text a player put on the server, of one of the ``WrittenTextKind`` kinds."""

    kind: WrittenTextKind
    path: str
    author: str
    text: str
