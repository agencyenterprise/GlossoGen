"""Index mapping ``message_id`` to the pristine (pre-transform) text of a message.

When a scenario rewrites outgoing messages via ``transform_outgoing_message``
(e.g. veyru's per-character channel noise), the persisted ``MessageSent`` carries
the *transformed* text while the text the agent actually composed survives only
in the ``send_message`` tool-call record. ``SendMessageResult.message_id`` links
the two: this module reads every successful ``send_message`` ``ToolResultReceived``,
parses its ``result`` for the ``message_id``, and maps that id to the pristine
``arguments["text"]``.

Metrics that want the text the agent *intended* to send (rather than what the
channel delivered) resolve each ``MessageSent`` through ``pristine_text_for``,
which falls back to the transmitted text when no pristine record exists — runs
predating the ``message_id`` link, or scenarios with no transform.
"""

import json
import logging

from schmidt.models.event import MessageSent, SimulationEvent, ToolResultReceived

logger = logging.getLogger(__name__)

_SEND_MESSAGE_TOOL = "send_message"
_SENT_STATUS = "sent"


def build_pristine_text_index(events: list[SimulationEvent]) -> dict[str, str]:
    """Map each persisted ``message_id`` to the pristine text the sender composed.

    Only successful sends (``status == "sent"`` with a non-null ``message_id``)
    contribute. Results whose ``result`` is not JSON (e.g. an end-of-sim
    rejection error string) are skipped.
    """
    index: dict[str, str] = {}
    for event in events:
        if not isinstance(event, ToolResultReceived):
            continue
        if event.tool_name != _SEND_MESSAGE_TOOL:
            continue
        try:
            result = json.loads(event.result)
        except (json.JSONDecodeError, TypeError):
            continue
        if result.get("status") != _SENT_STATUS:
            continue
        message_id = result.get("message_id")
        pristine = event.arguments.get("text")
        if not isinstance(message_id, str) or not isinstance(pristine, str):
            continue
        index[message_id] = pristine
    return index


def pristine_text_for(index: dict[str, str], message: MessageSent) -> str:
    """Return the pristine text for ``message`` if indexed, else its transmitted text."""
    return index.get(message.message.message_id, message.message.text)
