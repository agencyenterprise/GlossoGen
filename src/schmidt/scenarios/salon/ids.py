"""Canonical identifier constants for the Salon covert broadcast scenario.

Centralizes agent IDs, channel IDs, role names, template filenames, and
tool name lists so every module — the scenario, the world, and evaluators —
refers to the same literals.
"""

ENVOY_ID = "envoy"
CONFIDANT_ID = "confidant"
INQUISITOR_ID = "inquisitor"

SALON_CHANNEL_ID = "salon"
POSTMORTEM_CHANNEL_ID = "salon_postmortem"

ENVOY_ROLE = "Envoy"
CONFIDANT_ROLE = "Confidant"
INQUISITOR_ROLE = "Inquisitor"

ENVOY_SYSTEM_TEMPLATE = "envoy_system.jinja"
CONFIDANT_SYSTEM_TEMPLATE = "confidant_system.jinja"
INQUISITOR_SYSTEM_TEMPLATE = "inquisitor_system.jinja"

ENVOY_INJECTION_TEMPLATE = "envoy_injection.jinja"
CONFIDANT_INJECTION_TEMPLATE = "confidant_injection.jinja"
INQUISITOR_INJECTION_TEMPLATE = "inquisitor_injection.jinja"
POSTMORTEM_INJECTION_TEMPLATE = "postmortem_injection.jinja"
DESCRIPTION_TEMPLATE = "description.jinja"

SEND_MESSAGE_TOOL = "send_message"
SUBMIT_DECODE_TOOL = "submit_decode"
SUBMIT_INTERCEPT_TOOL = "submit_intercept"

TOOLS_ENVOY = [SEND_MESSAGE_TOOL]
TOOLS_CONFIDANT = [SEND_MESSAGE_TOOL, SUBMIT_DECODE_TOOL]
TOOLS_INQUISITOR = [SEND_MESSAGE_TOOL, SUBMIT_INTERCEPT_TOOL]

DECODE_RECORDED_MARKER = "Decode recorded"
INTERCEPT_RECORDED_MARKER = "Intercept recorded"
INTERCEPT_LIMIT_MARKER = "Intercept guess limit reached for this round"
INVALID_DIRECTIVE_MARKER = "Unknown directive id"
