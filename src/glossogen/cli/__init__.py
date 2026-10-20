"""The ``glossogen`` command line.

``cli_entry`` builds the parser and dispatches to a subcommand. Each other module
holds one subcommand, or a family of them, with its flags beside its handler.

``main`` is re-exported because ``glossogen.cli:main`` is the console script's
entry point, and a script installed before the package existed still imports it
from here.
"""

from glossogen.cli.cli_entry import main

__all__ = ["main"]
