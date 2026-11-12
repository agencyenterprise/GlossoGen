"""Turning off pydantic-ai's first-run banner in glossogen's own processes.

pydantic-ai prints a banner on a process's first agent run saying observability
is off and suggesting Logfire. Readers of a run's stdout log take it for
glossogen's Langfuse tracing. pydantic-ai skips it for runs an installed package
starts, but an editable checkout of glossogen does not count as one.
"""

import pydantic_ai


def turn_off_pydantic_ai_banner() -> None:
    """Stop pydantic-ai from printing its banner in this process."""
    pydantic_ai.BANNER_ENABLED = False
