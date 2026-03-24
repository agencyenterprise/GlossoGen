"""Transient event types for real-time token streaming.

These events are pushed via the in-process EventBus and SSE but are NOT persisted
to the JSONL event log. The complete text is captured by the standard
LLMResponseReceived and MessageSent events.
"""

from typing import Literal

from pydantic import BaseModel


class TokenDelta(BaseModel):
    """A partial text chunk from an in-progress LLM response.

    Emitted token-by-token as the Claude streaming API produces output. The
    ``is_final`` flag signals that the LLM response is complete and the partial
    text accumulator should be cleared.
    """

    event_type: Literal["token_delta"] = "token_delta"
    agent_id: str
    text: str
    is_final: bool


class MessagePreview(BaseModel):
    """A partial text preview of an in-progress send_message tool call.

    Emitted as the LLM streams the text argument of send_message. The
    ``channel_id`` identifies where the message will be posted. Replaced
    by the final MessageSent event when the tool call completes.
    """

    event_type: Literal["message_preview"] = "message_preview"
    agent_id: str
    channel_id: str
    text: str
    is_final: bool
