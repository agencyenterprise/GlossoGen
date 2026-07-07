"""Canonical identifier constants for the orbital_anomaly scenario.

Centralizes agent IDs, channel IDs, role names, template filenames, tool
names, and the literal markers the world emits into link-channel
notifications so every module refers to the same literals.
"""

ASTRONAUT_ID = "astronaut"
TELEMETRY_OFFICER_ID = "telemetry_officer"
SYSTEMS_ENGINEER_ID = "systems_engineer"

LINK_CHANNEL_ID = "link"
POSTMORTEM_CHANNEL_ID = "postmortem"

LINK_CHANNEL_DISPLAY_NAME = "comm loop"
POSTMORTEM_CHANNEL_DISPLAY_NAME = "debrief"

ASTRONAUT_ROLE = "Astronaut"
TELEMETRY_OFFICER_ROLE = "Telemetry Officer"
SYSTEMS_ENGINEER_ROLE = "Systems Engineer"

SEND_MESSAGE_TOOL = "send_message"
ACTUATE_PANEL_TOOL = "actuate_panel"

TOOLS_ASTRONAUT = [SEND_MESSAGE_TOOL, ACTUATE_PANEL_TOOL]
TOOLS_TELEMETRY_OFFICER = [SEND_MESSAGE_TOOL]
TOOLS_SYSTEMS_ENGINEER = [SEND_MESSAGE_TOOL]

ASTRONAUT_SYSTEM_TEMPLATE = "astronaut_system.jinja"
TELEMETRY_OFFICER_SYSTEM_TEMPLATE = "telemetry_officer_system.jinja"
SYSTEMS_ENGINEER_SYSTEM_TEMPLATE = "systems_engineer_system.jinja"
ASTRONAUT_INJECTION_TEMPLATE = "astronaut_injection.jinja"
TELEMETRY_OFFICER_INJECTION_TEMPLATE = "telemetry_officer_injection.jinja"
SYSTEMS_ENGINEER_INJECTION_TEMPLATE = "systems_engineer_injection.jinja"

ACTUATION_SUCCESS_MARKER = "Action accepted"
NEW_ANOMALY_MARKER = "a new anomaly has appeared"
VEHICLE_STABILIZED_MARKER = "VEHICLE STABILIZED"
VEHICLE_LOST_MARKER = "LOSS OF SYSTEM"
