"""Canonical identifier constants for the spillway_release scenario.

Centralizes agent IDs, the channel IDs, role display names, template
filenames, tool names, per-role tool lists, the literal markers the world
emits at round end, and the two park-securing action verbs.
"""

DAM_OPERATOR_ID = "dam_operator"
CIVIL_DEFENSE_ID = "civil_defense"
PARK_RANGER_ID = "park_ranger"

OPS_CHANNEL_ID = "ops"
POSTMORTEM_CHANNEL_ID = "postmortem"

DAM_OPERATOR_ROLE = "Dam Operator"
CIVIL_DEFENSE_ROLE = "Civil Defense Coordinator"
PARK_RANGER_ROLE = "Park Ranger"

SEND_MESSAGE_TOOL = "send_message"
READ_GAUGE_TOOL = "read_gauge"
OPEN_GATES_TOOL = "open_gates"
NOTIFY_PARK_TOOL = "notify_park"
EVACUATE_TOOL = "evacuate"

DAM_OPERATOR_SYSTEM_TEMPLATE = "dam_operator_system.jinja"
CIVIL_DEFENSE_SYSTEM_TEMPLATE = "civil_defense_system.jinja"
PARK_RANGER_SYSTEM_TEMPLATE = "park_ranger_system.jinja"
DAM_OPERATOR_INJECTION_TEMPLATE = "dam_operator_injection.jinja"
CIVIL_DEFENSE_INJECTION_TEMPLATE = "civil_defense_injection.jinja"
PARK_RANGER_INJECTION_TEMPLATE = "park_ranger_injection.jinja"

TOOLS_DAM_OPERATOR = [SEND_MESSAGE_TOOL, READ_GAUGE_TOOL, OPEN_GATES_TOOL]
TOOLS_CIVIL_DEFENSE = [SEND_MESSAGE_TOOL, EVACUATE_TOOL]
TOOLS_PARK_RANGER = [SEND_MESSAGE_TOOL, NOTIFY_PARK_TOOL]

# Literal markers emitted in world notifications at round end so the FE and
# any marker-based tooling can detect outcomes deterministically.
BUDGET_EXCEEDED_MARKER = "COMMUNICATION BUDGET EXCEEDED"
ROUND_SUCCESS_MARKER = "ROUND SUCCESS"
ROUND_FAILED_MARKER = "ROUND FAILED"
