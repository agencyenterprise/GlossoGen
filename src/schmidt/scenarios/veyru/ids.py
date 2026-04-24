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
STABILIZATION_ENGINEER_ID = "stabilization_engineer"
INTERN_ID = "intern"
OBSERVER_A_ID = "observer_a"
OBSERVER_B_ID = "observer_b"
STABILIZATION_ENGINEER_A_ID = "stabilization_engineer_a"
STABILIZATION_ENGINEER_B_ID = "stabilization_engineer_b"

LINK_CHANNEL_ID = "link"
POSTMORTEM_CHANNEL_ID = "postmortem"
LINK_A_CHANNEL_ID = "link_a"
LINK_B_CHANNEL_ID = "link_b"
POSTMORTEM_A_CHANNEL_ID = "postmortem_a"
POSTMORTEM_B_CHANNEL_ID = "postmortem_b"

FIELD_OBSERVER_ROLE = "Field Observer"
STABILIZATION_ENGINEER_ROLE = "Stabilization Engineer"
INTERN_ROLE = "Intern Observer"
FIELD_OBSERVER_A_ROLE = "Field Observer Alpha"
FIELD_OBSERVER_B_ROLE = "Field Observer Beta"
STABILIZATION_ENGINEER_A_ROLE = "Stabilization Engineer Alpha"
STABILIZATION_ENGINEER_B_ROLE = "Stabilization Engineer Beta"

INTERN_JOIN_REASON = "veyru_intern_join"
INTERN_TAKEOVER_REASON = "veyru_intern_takeover"
OBSERVER_SWAP_REASON = "veyru_observer_swap"

SEND_MESSAGE_TOOL = "send_message"
STABILIZE_VEYRU_TOOL = "stabilize_veyru"

FIELD_OBSERVER_SYSTEM_TEMPLATE = "field_observer_system.jinja"
STABILIZATION_ENGINEER_SYSTEM_TEMPLATE = "stabilization_engineer_system.jinja"
INTERN_SYSTEM_TEMPLATE = "intern_system.jinja"
FIELD_OBSERVER_INJECTION_TEMPLATE = "field_observer_injection.jinja"
STABILIZATION_ENGINEER_INJECTION_TEMPLATE = "stabilization_engineer_injection.jinja"

TOOLS_OBSERVER = [SEND_MESSAGE_TOOL, STABILIZE_VEYRU_TOOL]
TOOLS_STABILIZATION_ENGINEER = [SEND_MESSAGE_TOOL]
TOOLS_INTERN = [SEND_MESSAGE_TOOL, STABILIZE_VEYRU_TOOL]

STABILIZATION_SUCCESS_MARKER = "Stabilization successful"
NEW_SYMPTOMS_MARKER = "new symptoms have appeared"
VEYRU_COLLAPSED_MARKER = "VEYRU HAS COLLAPSED"
VEYRU_STABILIZED_MARKER = "VEYRU STABILIZED"
