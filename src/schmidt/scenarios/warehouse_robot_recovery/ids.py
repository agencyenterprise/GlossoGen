"""Canonical identifier constants for the warehouse robot recovery scenario.

Centralizes agent IDs, channel IDs, role names, event reasons, template
filenames, and tool name lists so every module — the scenario, the world,
evaluators, and server readers — refers to the same literals.
"""

FLOOR_ASSOCIATE_ID = "floor_associate"
ROBOTICS_ENGINEER_ID = "robotics_engineer"
FLEET_SAFETY_COORDINATOR_ID = "fleet_safety_coordinator"

RADIO_CHANNEL_ID = "radio"
POSTMORTEM_CHANNEL_ID = "postmortem"

FLOOR_ASSOCIATE_ROLE = "Floor Associate"
ROBOTICS_ENGINEER_ROLE = "Robotics Engineer"
FLEET_SAFETY_COORDINATOR_ROLE = "Fleet Safety Coordinator"

SEND_MESSAGE_TOOL = "send_message"
PERFORM_RECOVERY_TOOL = "perform_recovery"

FLOOR_ASSOCIATE_SYSTEM_TEMPLATE = "floor_associate_system.jinja"
ROBOTICS_ENGINEER_SYSTEM_TEMPLATE = "robotics_engineer_system.jinja"
FLEET_SAFETY_COORDINATOR_SYSTEM_TEMPLATE = "fleet_safety_coordinator_system.jinja"
FLOOR_ASSOCIATE_INJECTION_TEMPLATE = "floor_associate_injection.jinja"
ROBOTICS_ENGINEER_INJECTION_TEMPLATE = "robotics_engineer_injection.jinja"
FLEET_SAFETY_COORDINATOR_INJECTION_TEMPLATE = "fleet_safety_coordinator_injection.jinja"

TOOLS_FLOOR_ASSOCIATE = [SEND_MESSAGE_TOOL, PERFORM_RECOVERY_TOOL]
TOOLS_ROBOTICS_ENGINEER = [SEND_MESSAGE_TOOL]
TOOLS_FLEET_SAFETY_COORDINATOR = [SEND_MESSAGE_TOOL]

RECOVERY_SUCCESS_MARKER = "Recovery successful"
RECOVERY_FAILURE_MARKER = "Recovery failed"
ROBOT_RECOVERED_MARKER = "ROBOT RECOVERED"
ROBOT_NOT_RECOVERED_MARKER = "ROBOT NOT RECOVERED"
BUDGET_EXCEEDED_MARKER = "COMMUNICATION BUDGET EXCEEDED"
