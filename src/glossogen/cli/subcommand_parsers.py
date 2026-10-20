"""``SubcommandParsers``, the part of argparse's subparsers object a command module uses."""

import argparse
from typing import Protocol


class SubcommandParsers(Protocol):
    """What ``ArgumentParser.add_subparsers()`` returns, as far as adding a command goes.

    Spelled as a protocol because argparse's own type for it is private.
    """

    def add_parser(self, name: str, *, help: str) -> argparse.ArgumentParser:
        """Add one subcommand and return the parser its flags go on."""
        ...
