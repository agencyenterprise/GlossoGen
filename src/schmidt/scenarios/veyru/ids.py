"""Canonical identifier constants for the Veyru scenario.

Centralizes agent IDs, channel IDs, team IDs, role names, event reasons,
template filenames, and tool name lists so every module — the scenario,
the world, evaluators, and server readers — refers to the same literals.
"""

from typing import Literal

TeamId = Literal["solo", "a", "b"]

TEAM_SOLO_ID: TeamId = "solo"
TEAM_A_ID: TeamId = "a"
TEAM_B_ID: TeamId = "b"

FIELD_OBSERVER_ID = "field_observer"
SPECIALIST_ID = "specialist"
INTERN_ID = "intern"
OBSERVER_A_ID = "observer_a"
OBSERVER_B_ID = "observer_b"
SPECIALIST_A_ID = "specialist_a"
SPECIALIST_B_ID = "specialist_b"

LINK_CHANNEL_ID = "link"
POSTMORTEM_CHANNEL_ID = "postmortem"
LINK_A_CHANNEL_ID = "link_a"
LINK_B_CHANNEL_ID = "link_b"
POSTMORTEM_A_CHANNEL_ID = "postmortem_a"
POSTMORTEM_B_CHANNEL_ID = "postmortem_b"

FIELD_OBSERVER_ROLE = "Field Observer"
SPECIALIST_ROLE = "Specialist"
INTERN_ROLE = "Intern Observer"
FIELD_OBSERVER_A_ROLE = "Field Observer Alpha"
FIELD_OBSERVER_B_ROLE = "Field Observer Beta"
SPECIALIST_A_ROLE = "Specialist Alpha"
SPECIALIST_B_ROLE = "Specialist Beta"

INTERN_JOIN_REASON = "veyru_intern_join"
INTERN_TAKEOVER_REASON = "veyru_intern_takeover"
OBSERVER_SWAP_REASON = "veyru_observer_swap"

SEND_MESSAGE_TOOL = "send_message"
STABILIZE_VEYRU_TOOL = "stabilize_veyru"

FIELD_OBSERVER_SYSTEM_TEMPLATE = "field_observer_system.jinja"
SPECIALIST_SYSTEM_TEMPLATE = "specialist_system.jinja"
INTERN_SYSTEM_TEMPLATE = "intern_system.jinja"
FIELD_OBSERVER_INJECTION_TEMPLATE = "field_observer_injection.jinja"
SPECIALIST_INJECTION_TEMPLATE = "specialist_injection.jinja"

TOOLS_OBSERVER = [SEND_MESSAGE_TOOL, STABILIZE_VEYRU_TOOL]
TOOLS_SPECIALIST = [SEND_MESSAGE_TOOL]
TOOLS_INTERN = [SEND_MESSAGE_TOOL, STABILIZE_VEYRU_TOOL]

STABILIZATION_SUCCESS_MARKER = "Stabilization successful"
NEW_SYMPTOMS_MARKER = "new symptoms have appeared"
VEYRU_COLLAPSED_MARKER = "VEYRU HAS COLLAPSED"
VEYRU_STABILIZED_MARKER = "VEYRU STABILIZED"
