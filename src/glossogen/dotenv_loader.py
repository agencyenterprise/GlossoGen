"""Read the `.env` beside the project a command was run from.

``python-dotenv``'s ``load_dotenv()`` locates the file by walking up from the
module that called it, not from the working directory. Inside a checkout those
are the same place, so the repo's own `.env` is found either way. Installed as a
dependency they are not: the walk starts in ``site-packages`` and finds nothing,
so a project's `.env` is silently ignored and its `ANTHROPIC_API_KEY` with it.

Walking up from the working directory instead covers both, and keeps a command
run from a subdirectory reading the project's file.
"""

import logging
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)


def load_env_from_working_directory() -> Path | None:
    """Load the nearest `.env` at or above the working directory.

    Returns the file that was read, or None when there is none. Values already
    in the environment win, which is what lets a variable set on the command
    line override the file for one run.
    """
    located = find_dotenv(usecwd=True)
    if not located:
        return None
    load_dotenv(dotenv_path=located)
    logger.debug("Loaded environment from %s", located)
    return Path(located)
