"""Canonical identifier constants for the spot_the_difference scenario.

Centralizes agent IDs, channel IDs, team IDs, role names, template
filenames, tool names, the difference taxonomy enum, and the literal markers
that tool result strings and world notifications use.

Each team has two symmetric viewers: the *left* viewer sees scene A, the
*right* viewer sees scene B. Neither sees the other scene nor the planted
differences. Both viewers can submit; the first submission locks the team's
answer for the round.
"""

from enum import Enum

VIEWER_LEFT_ID = "viewer_left"
VIEWER_RIGHT_ID = "viewer_right"

VIEWER_LEFT_A_ID = "viewer_left_a"
VIEWER_RIGHT_A_ID = "viewer_right_a"
VIEWER_LEFT_B_ID = "viewer_left_b"
VIEWER_RIGHT_B_ID = "viewer_right_b"

LINK_CHANNEL_ID = "link"
POSTMORTEM_CHANNEL_ID = "postmortem"
LINK_A_CHANNEL_ID = "link_a"
LINK_B_CHANNEL_ID = "link_b"
POSTMORTEM_A_CHANNEL_ID = "postmortem_a"
POSTMORTEM_B_CHANNEL_ID = "postmortem_b"

TEAM_SOLO_ID = "solo"
TEAM_A_ID = "team_a"
TEAM_B_ID = "team_b"

VIEWER_LEFT_ROLE = "Scene Viewer L"
VIEWER_RIGHT_ROLE = "Scene Viewer R"
VIEWER_LEFT_A_ROLE = "Scene Viewer L (Team A)"
VIEWER_RIGHT_A_ROLE = "Scene Viewer R (Team A)"
VIEWER_LEFT_B_ROLE = "Scene Viewer L (Team B)"
VIEWER_RIGHT_B_ROLE = "Scene Viewer R (Team B)"

# Scene sides: the left viewer holds scene A, the right viewer holds scene B.
SCENE_SIDE_LEFT = "left"
SCENE_SIDE_RIGHT = "right"

SEND_MESSAGE_TOOL = "send_message"
SUBMIT_DIFFERENCES_TOOL = "submit_differences"

VIEWER_LEFT_SYSTEM_TEMPLATE = "viewer_left_system.jinja"
VIEWER_RIGHT_SYSTEM_TEMPLATE = "viewer_right_system.jinja"
VIEWER_LEFT_INJECTION_TEMPLATE = "viewer_left_injection.jinja"
VIEWER_RIGHT_INJECTION_TEMPLATE = "viewer_right_injection.jinja"

TOOLS_VIEWER = [SEND_MESSAGE_TOOL, SUBMIT_DIFFERENCES_TOOL]

SUBMISSION_RECORDED_MARKER = "SUBMISSION RECORDED"
ALREADY_SUBMITTED_MARKER = "ALREADY SUBMITTED"
ROUND_WON_MARKER = "ROUND WON"
ROUND_LOST_MARKER = "ROUND LOST"
ROUND_RESULT_MARKER = "ROUND RESULT"


class DifferenceKind(str, Enum):
    """The four planted-difference types between scene A and scene B."""

    ATTRIBUTE_CHANGED = "attribute_changed"
    OBJECT_MOVED = "object_moved"
    OBJECT_ADDED = "object_added"
    OBJECT_REMOVED = "object_removed"
