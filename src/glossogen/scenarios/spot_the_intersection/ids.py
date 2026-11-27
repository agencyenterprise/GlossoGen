"""Canonical identifiers for the spot_the_intersection scenario.

Team, channel, template and tool names, and the markers that open tool results
and world notifications. Agent ids are built per seat in :mod:`seats`, since a
team's size is a knob.
"""

from glossogen.scenarios.spot_the_intersection.link_medium import SEND_DRAWING_TOOL

TEAM_SOLO_ID = "solo"
TEAM_A_ID = "team_a"
TEAM_B_ID = "team_b"

LINK_CHANNEL_ID = "link"
LINK_A_CHANNEL_ID = "link_a"
LINK_B_CHANNEL_ID = "link_b"
POSTMORTEM_CHANNEL_ID = "postmortem"
POSTMORTEM_A_CHANNEL_ID = "postmortem_a"
POSTMORTEM_B_CHANNEL_ID = "postmortem_b"

SEND_MESSAGE_TOOL = "send_message"
SUBMIT_OBJECT_TOOL = "submit_object"
TOOLS_VIEWER = (SEND_MESSAGE_TOOL, SUBMIT_OBJECT_TOOL)
TOOLS_CANVAS_VIEWER = (*TOOLS_VIEWER, SEND_DRAWING_TOOL)

VIEWER_SYSTEM_TEMPLATE = "viewer_system.jinja"
VIEWER_INJECTION_TEMPLATE = "viewer_injection.jinja"
POSTMORTEM_INJECTION_TEMPLATE = "postmortem_injection.jinja"
DESCRIPTION_TEMPLATE = "description.jinja"

# The early round-end trigger, once every team is finished.
ALL_TEAMS_DONE_TRIGGER = "all_teams_done"

SUBMISSION_RECORDED_MARKER = "SUBMISSION RECORDED"
ALREADY_SUBMITTED_MARKER = "ALREADY SUBMITTED"
ANSWER_LOCKED_MARKER = "ANSWER LOCKED"
ROUND_WON_MARKER = "ROUND WON"
ROUND_LOST_MARKER = "ROUND LOST"
ROUND_RESULT_MARKER = "ROUND RESULT"
BUDGET_EXCEEDED_MARKER = "COMMUNICATION BUDGET EXCEEDED"
BUDGET_LOW_MARKER = "BUDGET LOW"
