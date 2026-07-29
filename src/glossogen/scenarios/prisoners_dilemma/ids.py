"""Canonical identifier constants for the Prisoner's Dilemma scenario.

Centralizes agent IDs, channel IDs, tool names, and the decision type so
every module — the scenario, the world, the tool, and the prompts —
refers to the same literals.
"""

from typing import Literal

PLAYER_A_ID = "player_a"
PLAYER_B_ID = "player_b"

PLAYER_A_ROLE = "Player A"
PLAYER_B_ROLE = "Player B"

LINK_CHANNEL_ID = "link"

SEND_MESSAGE_TOOL = "send_message"
SUBMIT_DECISION_TOOL = "submit_decision"

TOOLS_PLAYER = [SEND_MESSAGE_TOOL, SUBMIT_DECISION_TOOL]

PLAYER_SYSTEM_TEMPLATE = "player_system.jinja"
PLAYER_INJECTION_TEMPLATE = "player_injection.jinja"

# The two moves available each round. A player may only submit one of these
# via the `submit_decision` tool; there is no free-text decision.
Decision = Literal["cooperate", "defect"]

ROUND_RESOLVED_TRIGGER = "pd_round_resolved"
