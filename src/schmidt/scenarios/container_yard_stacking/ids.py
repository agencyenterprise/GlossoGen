"""Canonical identifier constants for the container_yard_stacking scenario.

Centralizes agent IDs, channel IDs, role names, template filenames, tool
names, and the literal markers the round-success metric matches against in
tool result strings and world notifications.
"""

YARD_OPERATOR_ID = "yard_operator"
LOGISTICS_PLANNER_ID = "logistics_planner"
CRANE_OPERATOR_ID = "crane_operator"

LINK_CHANNEL_ID = "link"
POSTMORTEM_CHANNEL_ID = "postmortem"

YARD_OPERATOR_ROLE = "Yard Operator"
LOGISTICS_PLANNER_ROLE = "Logistics Planner"
CRANE_OPERATOR_ROLE = "Crane Operator"

SEND_MESSAGE_TOOL = "send_message"
MOVE_TRUCK_TOOL = "move_truck"
PLACE_ON_STACK_TOOL = "place_on_stack"
LIFT_FROM_STACK_TOOL = "lift_from_stack"

YARD_OPERATOR_SYSTEM_TEMPLATE = "yard_operator_system.jinja"
LOGISTICS_PLANNER_SYSTEM_TEMPLATE = "logistics_planner_system.jinja"
CRANE_OPERATOR_SYSTEM_TEMPLATE = "crane_operator_system.jinja"
YARD_OPERATOR_INJECTION_TEMPLATE = "yard_operator_injection.jinja"
LOGISTICS_PLANNER_INJECTION_TEMPLATE = "logistics_planner_injection.jinja"
CRANE_OPERATOR_INJECTION_TEMPLATE = "crane_operator_injection.jinja"

TOOLS_YARD_OPERATOR = [SEND_MESSAGE_TOOL, MOVE_TRUCK_TOOL]
TOOLS_LOGISTICS_PLANNER = [SEND_MESSAGE_TOOL]
TOOLS_CRANE_OPERATOR = [SEND_MESSAGE_TOOL, PLACE_ON_STACK_TOOL, LIFT_FROM_STACK_TOOL]

TRUCK_ARRIVED_MARKER = "TRUCK ARRIVED AT CORRECT SPOT"
TRUCK_WRONG_SPOT_MARKER = "TRUCK ARRIVED AT WRONG SPOT"
MOVE_SUCCESS_MARKER = "CRANE MOVE ACCEPTED"
MOVE_REJECTED_MARKER = "CRANE MOVE REJECTED"
CONTAINER_PLACED_MARKER = "INCOMING CONTAINER PLACED"
BUDGET_EXCEEDED_MARKER = "COMMUNICATION BUDGET EXCEEDED"
ROUND_SUCCESS_MARKER = "ROUND SUCCESS"
ROUND_FAILED_MARKER = "ROUND FAILED"

STACK_COUNT = 4
STACK_HEIGHT = 3
PADS_PER_STATION = 2

INBOUND_TRUCK_ROLE = "inbound"
OUTBOUND_TRUCK_ROLE = "outbound"
