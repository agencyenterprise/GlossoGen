"""Canonical identifier constants for the satellite contact window scenario.

Centralizes agent IDs, channel IDs, role names, template filenames, and
tool name lists so every module — the scenario, the world, evaluators, and
server readers — refers to the same literals.
"""

TELEMETRY_OPERATOR_ID = "telemetry_operator"
SUBSYSTEM_ENGINEER_ID = "subsystem_engineer"
FLIGHT_DIRECTOR_ID = "flight_director"

LINK_CHANNEL_ID = "link"
POSTMORTEM_CHANNEL_ID = "postmortem"

TELEMETRY_OPERATOR_ROLE = "Telemetry Operator"
SUBSYSTEM_ENGINEER_ROLE = "Subsystem Engineer"
FLIGHT_DIRECTOR_ROLE = "Flight Director"

SEND_MESSAGE_TOOL = "send_message"
SEND_COMMAND_SEQUENCE_TOOL = "send_command_sequence"

TELEMETRY_OPERATOR_SYSTEM_TEMPLATE = "telemetry_operator_system.jinja"
SUBSYSTEM_ENGINEER_SYSTEM_TEMPLATE = "subsystem_engineer_system.jinja"
FLIGHT_DIRECTOR_SYSTEM_TEMPLATE = "flight_director_system.jinja"
TELEMETRY_OPERATOR_INJECTION_TEMPLATE = "telemetry_operator_injection.jinja"
SUBSYSTEM_ENGINEER_INJECTION_TEMPLATE = "subsystem_engineer_injection.jinja"
FLIGHT_DIRECTOR_INJECTION_TEMPLATE = "flight_director_injection.jinja"

TOOLS_TELEMETRY_OPERATOR = [SEND_MESSAGE_TOOL, SEND_COMMAND_SEQUENCE_TOOL]
TOOLS_SUBSYSTEM_ENGINEER = [SEND_MESSAGE_TOOL]
TOOLS_FLIGHT_DIRECTOR = [SEND_MESSAGE_TOOL]

COMMAND_ACCEPTED_MARKER = "COMMAND SEQUENCE ACCEPTED"
COMMAND_REJECTED_MARKER = "COMMAND SEQUENCE REJECTED"
CONTACT_WINDOW_CRITICAL_MARKER = "CONTACT WINDOW 75% ELAPSED"
CONTACT_WINDOW_CLOSED_MARKER = "CONTACT WINDOW CLOSED"
SATELLITE_RECOVERED_MARKER = "SATELLITE RECOVERED"
SATELLITE_NOT_RECOVERED_MARKER = "SATELLITE NOT RECOVERED"
