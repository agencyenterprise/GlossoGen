"""glossogen turns off pydantic-ai's first-run banner.

The banner says observability is off and suggests Logfire, and readers of a run's
stdout log take it for glossogen's Langfuse tracing. pydantic-ai already skips it
under pytest and in CI, so the test clears those signals and asks pydantic-ai's
own check, which fails if a pydantic-ai upgrade moves the switch.
"""

import pydantic_ai
import pytest
from pydantic_ai import _display

from glossogen.runners.pydantic_ai_banner import turn_off_pydantic_ai_banner


def test_the_banner_is_suppressed_once_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside pytest and CI the banner shows unless glossogen turns it off."""
    for name in ("PYDANTIC_AI_NO_BANNER", "CI", "PYTEST_VERSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(pydantic_ai, "BANNER_ENABLED", True)
    assert _display.banner_pending()

    turn_off_pydantic_ai_banner()

    assert not _display.banner_pending()
