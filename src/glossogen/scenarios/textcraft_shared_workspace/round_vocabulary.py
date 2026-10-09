"""The closed value sets a workspace round records: delivery carriers and terminal triggers.

A leaf module, so ``events.py`` and the scenario name the same values without
``events.py`` importing the scenario.
"""

from typing import Literal

DeliveryCarrier = Literal["act", "send", "observe", "wake"]
"""The tool result that carried public message bodies into an agent's context."""

WorkspaceTrigger = Literal[
    "budget_exhausted",
    "all_targets_satisfied",
    "actions_exhausted",
    "team_tokens_exhausted",
]
"""The terminal condition the world reports once a round can no longer continue."""
