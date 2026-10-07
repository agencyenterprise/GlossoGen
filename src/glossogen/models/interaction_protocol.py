"""How an agent's runner drives it, recorded in configs and registration events.

``communication`` is the platform's default: agents block on
``read_notifications`` and read their channels. ``workspace_action`` is for
scenarios whose agents act on a shared workspace: channel messages arrive inside
tool results, ``send`` replaces ``send_message``, and the runner suspends the
agent on ``wait_for_message`` or ``finish`` instead of executing them.
"""

from typing import Literal

InteractionProtocol = Literal["communication", "workspace_action"]

WaitKind = Literal["message", "finish"]
"""What a parked ``workspace_action`` agent waits for.

``message`` (``wait_for_message``) resumes on a new channel message, a lifecycle
event or a timeout; ``finish`` (``finish``, or a turn that ended in text) resumes
only on a lifecycle event.
"""


def is_workspace_action_protocol(value: InteractionProtocol) -> bool:
    """Return whether the runner uses the workspace-action lifecycle."""
    return value == "workspace_action"


def is_legacy_protocol(value: InteractionProtocol) -> bool:
    """Keep registration JSON unchanged for agents on the default protocol."""
    return value == "communication"
