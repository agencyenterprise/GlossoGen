"""Canonical identifier constants for the drive_module_repair scenario.

Centralizes agent IDs, the channel IDs, role display names, tool names,
per-role tool lists, template filenames, and the literal markers the world
emits so outcomes are detectable from tool results and notifications.
"""

FIELD_TECHNICIAN_ID = "field_technician"
DIAGNOSTICS_ENGINEER_ID = "diagnostics_engineer"
SPEC_ENGINEER_ID = "spec_engineer"

BAY_CHANNEL_ID = "bay"
POSTMORTEM_CHANNEL_ID = "postmortem"

FIELD_TECHNICIAN_ROLE = "Field Technician"
DIAGNOSTICS_ENGINEER_ROLE = "Diagnostics Engineer"
SPEC_ENGINEER_ROLE = "Spec Engineer"

SEND_MESSAGE_TOOL = "send_message"
SERVICE_COMPONENT_TOOL = "service_component"

FIELD_TECHNICIAN_SYSTEM_TEMPLATE = "field_technician_system.jinja"
DIAGNOSTICS_ENGINEER_SYSTEM_TEMPLATE = "diagnostics_engineer_system.jinja"
SPEC_ENGINEER_SYSTEM_TEMPLATE = "spec_engineer_system.jinja"
FIELD_TECHNICIAN_INJECTION_TEMPLATE = "field_technician_injection.jinja"
DIAGNOSTICS_ENGINEER_INJECTION_TEMPLATE = "diagnostics_engineer_injection.jinja"
SPEC_ENGINEER_INJECTION_TEMPLATE = "spec_engineer_injection.jinja"

TOOLS_FIELD_TECHNICIAN = [SEND_MESSAGE_TOOL, SERVICE_COMPONENT_TOOL]
TOOLS_DIAGNOSTICS_ENGINEER = [SEND_MESSAGE_TOOL]
TOOLS_SPEC_ENGINEER = [SEND_MESSAGE_TOOL]

# Literal markers emitted in tool results / world notifications so the FE and
# any marker-based tooling can detect outcomes deterministically.
REPLACEMENT_ACCEPTED_MARKER = "REPLACEMENT ACCEPTED"
REPLACEMENT_INEFFECTIVE_MARKER = "REPLACEMENT INEFFECTIVE"
DEVICE_REPAIRED_MARKER = "DEVICE REPAIRED"
DEVICE_FAILED_MARKER = "DEVICE NOT REPAIRED"
BUDGET_EXCEEDED_MARKER = "COMMUNICATION BUDGET EXCEEDED"
