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
which falls back to the transmitted text when no pristine record exists, since runs
predating the ``message_id`` link, or scenarios with no transform.
"""

import logging

from pydantic import ValidationError

from glossogen.models.event import MessageSent, SimulationEvent, ToolResultReceived
from glossogen.models.mcp_responses import SendReceipt, SendStatus
from glossogen.runtime.communication_tools import SEND_MESSAGE_TOOL_NAME

logger = logging.getLogger(__name__)


def build_pristine_text_index(events: list[SimulationEvent]) -> dict[str, str]:
    """Map each persisted ``message_id`` to the pristine text the sender composed.

    Only successful sends (``SendStatus.SENT`` with a non-null ``message_id``)
    contribute. Results that are not a ``SendReceipt`` (e.g. an end-of-sim
    rejection error string) are skipped.
    """
    index: dict[str, str] = {}
    for event in events:
        if not isinstance(event, ToolResultReceived):
            continue
        if event.tool_name != SEND_MESSAGE_TOOL_NAME:
            continue
        try:
            receipt = SendReceipt.model_validate_json(event.result)
        except ValidationError:
            logger.debug("send_message result of call %s is not a receipt", event.call_id)
            continue
        if receipt.status != SendStatus.SENT or receipt.message_id is None:
            continue
        pristine = event.arguments.get("text")
        if not isinstance(pristine, str):
            continue
        index[receipt.message_id] = pristine
    return index


def pristine_text_for(index: dict[str, str], message: MessageSent) -> str:
    """Return the pristine text for ``message`` if indexed, else its transmitted text."""
    return index.get(message.message.message_id, message.message.text)
